"""SOS flow through the HTTP API: record -> release -> countdown -> send or cancel."""
import hashlib
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock, config, notify, ratelimit, sos

CONTACTS = [{"name": "Amma", "phone": "+919800000001"}, {"name": "Priya", "phone": "+919800000002"}]
SPOT = {"lat": 17.4337, "lng": 78.5016}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "WHATSAPP_TOKEN", "")
    ratelimit.reset()
    from app.main import app
    with TestClient(app) as c:
        yield c


def start(client):
    r = client.post("/sos", json={**SPOT, "contacts": CONTACTS})
    assert r.status_code == 201
    body = r.json()
    return body["id"], {"X-Owner-Key": body["owner_key"]}, body


def upload(client, alert_id, key, chunks):
    for i, data in enumerate(chunks):
        r = client.post(f"/sos/{alert_id}/chunk", content=data,
                        headers={**key, "X-Chunk-Index": str(i), "Content-Type": "video/webm"})
        assert r.status_code == 200, r.text


def state(client, alert_id):
    return client.get(f"/alert/{alert_id}/data").json()


def test_send_stores_hashed_video_and_gives_whatsapp_links_when_not_configured(client):
    alert_id, key, created = start(client)
    assert created["alert_url"].endswith(f"/alert/{alert_id}")
    chunks = [b"header-and-frames-1", b"frames-2", b"frames-3"]
    upload(client, alert_id, key, chunks)
    assert client.post(f"/sos/{alert_id}/release", headers=key).json()["state"] == "countdown"

    sent = client.post(f"/sos/{alert_id}/send", headers=key, json={}).json()
    assert sent["state"] == "sent"
    assert sent["whatsapp"] == "manual"
    links = sent["whatsapp_links"]
    assert len(links) == 2 and links[0]["href"].startswith("https://wa.me/919800000001?text=")

    data = state(client, alert_id)
    assert data["state"] == "sent"
    assert data["video_sha256"] == hashlib.sha256(b"".join(chunks)).hexdigest()
    assert data["summary"]  # template brief even without an AI key
    video = client.get(f"/alert/{alert_id}/video")
    assert video.status_code == 200 and video.content == b"".join(chunks)


def test_correct_pin_cancel_deletes_the_video(client):
    alert_id, key, _ = start(client)
    upload(client, alert_id, key, [b"abc"])
    client.post(f"/sos/{alert_id}/release", headers=key)
    assert client.post(f"/sos/{alert_id}/cancel", headers=key).json()["state"] == "cancelled"
    assert state(client, alert_id)["state"] == "cancelled"
    assert client.get(f"/alert/{alert_id}/video").status_code == 404
    assert not any(config.MEDIA_DIR.glob(f"{alert_id}*"))


def test_duress_send_is_recorded_and_still_notifies(client, monkeypatch):
    sent_to = []
    monkeypatch.setattr(config, "WHATSAPP_TOKEN", "wa-token")
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(config, "WHATSAPP_TEMPLATE", "ride_radar_sos")
    monkeypatch.setattr(notify, "send_whatsapp", lambda phone, name, url: sent_to.append(phone) or True)
    alert_id, key, _ = start(client)
    upload(client, alert_id, key, [b"abc"])
    r = client.post(f"/sos/{alert_id}/send", headers=key, json={"duress": True}).json()
    assert r["whatsapp"] == "sent"
    assert sent_to == ["+919800000001", "+919800000002"]
    conn = sqlite3.connect(config.DB_PATH)
    assert conn.execute("SELECT duress FROM sos_alerts WHERE id = ?", (alert_id,)).fetchone()[0] == 1


def test_countdown_auto_sends_when_nobody_cancels(client):
    alert_id, key, _ = start(client)
    upload(client, alert_id, key, [b"abc"])
    client.post(f"/sos/{alert_id}/release", headers=key)
    later = clock.utc_now() + timedelta(seconds=config.SOS_COUNTDOWN_SECONDS + config.SOS_GRACE_SECONDS + 1)
    assert sos.sweep(now=later) == [alert_id]
    assert state(client, alert_id)["state"] == "sent"


def test_recording_that_goes_silent_auto_sends(client):
    """Phone snatched or app killed mid-recording: the server sends anyway."""
    alert_id, key, _ = start(client)
    upload(client, alert_id, key, [b"abc"])
    later = clock.utc_now() + timedelta(seconds=config.SOS_SILENCE_SECONDS + 1)
    assert sos.sweep(now=later) == [alert_id]
    assert state(client, alert_id)["state"] == "sent"


def test_only_the_owner_can_control_an_alert(client):
    alert_id, key, _ = start(client)
    bad = {"X-Owner-Key": "nope"}
    assert client.post(f"/sos/{alert_id}/chunk", content=b"x", headers={**bad, "X-Chunk-Index": "0"}).status_code == 403
    assert client.post(f"/sos/{alert_id}/cancel", headers=bad).status_code == 403
    assert client.post(f"/sos/{alert_id}/send", headers=bad, json={}).status_code == 403


def test_chunks_must_arrive_in_order(client):
    alert_id, key, _ = start(client)
    r = client.post(f"/sos/{alert_id}/chunk", content=b"x", headers={**key, "X-Chunk-Index": "1"})
    assert r.status_code == 409
    assert r.json()["expected"] == 0


def test_video_size_is_capped(client, monkeypatch):
    monkeypatch.setattr(config, "SOS_MAX_VIDEO_BYTES", 10)
    alert_id, key, _ = start(client)
    upload(client, alert_id, key, [b"12345678"])
    r = client.post(f"/sos/{alert_id}/chunk", content=b"12345", headers={**key, "X-Chunk-Index": "1"})
    assert r.status_code == 413


def test_location_updates_reach_the_alert_page(client):
    alert_id, key, _ = start(client)
    client.post(f"/sos/{alert_id}/location", json={"lat": 17.44, "lng": 78.50}, headers=key)
    data = state(client, alert_id)
    assert (data["lat"], data["lng"]) == (17.44, 78.50)
    assert data["area"] == "Secunderabad Railway Station"


def test_console_lists_sent_alerts_and_needs_token_when_set(client, monkeypatch):
    alert_id, key, _ = start(client)
    upload(client, alert_id, key, [b"abc"])
    client.post(f"/sos/{alert_id}/send", headers=key, json={})
    rows = client.get("/sos/alerts").json()["alerts"]
    assert [a["id"] for a in rows] == [alert_id]
    assert "phone" not in str(rows)  # contacts' numbers are not shown to the console
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    assert client.get("/sos/alerts").status_code == 401
    assert client.get("/sos/alerts", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_contacts_are_validated(client):
    r = client.post("/sos", json={**SPOT, "contacts": [{"name": "X", "phone": "12"}]})
    assert r.status_code == 422
