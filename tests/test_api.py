"""HTTP-level tests: the public API is the seam."""
import base64
import hashlib
import hmac
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import clock, config, ratelimit

SECUNDERABAD = {"lat": 17.4337, "lng": 78.5016}
BEGUMPET = {"lat": 17.4447, "lng": 78.4664}
DELHI = {"lat": 28.61, "lng": 77.20}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    ratelimit.reset()
    from app.main import app
    with TestClient(app) as c:  # runs startup: schema + auto-seed
        yield c


def counts():
    conn = sqlite3.connect(config.DB_PATH)
    return [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("incidents", "trip_shares", "authority_flags")]


def test_startup_seeds_an_empty_database(client):
    assert counts()[0] > 0
    assert client.get("/healthz").json()["status"] == "ok"


def test_check_scores_without_storing_anything(client):
    before = counts()
    r = client.post("/check", json={**SECUNDERABAD, "hour": 22})
    assert r.status_code == 200
    assert r.json()["level"] in {"green", "amber", "red"}
    assert counts() == before


def test_check_outside_city_is_not_covered(client):
    assert client.post("/check", json=DELHI).json()["level"] == "not_covered"


def test_check_rejects_bad_input_with_json_error(client):
    r = client.post("/check", json={"lat": "x", "lng": 1})
    assert r.status_code == 422
    assert "lat" in r.json()["error"]


def test_default_hour_is_city_local_time_not_server_time(client, monkeypatch):
    ist = clock.CITY_TZ
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 11, 22, 15, tzinfo=ist))
    assert client.post("/check", json=SECUNDERABAD).json()["hour"] == 22


def test_response_carries_helplines_on_risky_results(client):
    body = client.post("/check", json={**SECUNDERABAD, "hour": 22}).json()
    assert body["level"] == "red"
    assert any(h["number"] == "112" for h in body["helplines"])


def test_security_headers(client):
    r = client.get("/")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "camera=(self)" in r.headers["permissions-policy"]  # SOS recording needs it


# ---------- trip share ----------

def test_only_the_rider_can_update_or_stop_a_trip(client):
    share = client.post("/share").json()
    token, key = share["token"], share["owner_key"]
    point = {"lat": 17.43, "lng": 78.50}

    assert client.post(f"/trip/{token}/update", json=point).status_code == 403
    assert client.post(f"/trip/{token}/update", json=point, headers={"X-Owner-Key": "wrong"}).status_code == 403
    assert client.post(f"/trip/{token}/update", json=point, headers={"X-Owner-Key": key}).status_code == 200

    data = client.get(f"/trip/{token}/data").json()
    assert (data["lat"], data["lng"]) == (17.43, 78.50)
    assert "owner_key" not in data

    assert client.delete(f"/trip/{token}").status_code == 403
    assert client.delete(f"/trip/{token}", headers={"X-Owner-Key": key}).status_code == 200
    assert client.get(f"/trip/{token}/data").status_code == 404


def test_expired_trip_is_deleted_on_access(client):
    token = client.post("/share").json()["token"]
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE trip_shares SET expires_at = '2000-01-01T00:00:00+00:00'")
    conn.commit()
    assert client.get(f"/trip/{token}/data").status_code == 404
    assert counts()[1] == 0


def test_share_url_uses_public_base_url(client, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://radar.example.org")
    assert client.post("/share").json()["url"].startswith("https://radar.example.org/trip/")


# ---------- dashboard ----------

def test_resolve_needs_admin_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    area_id = client.get("/dashboard").json()["areas"][0]["area_id"]
    assert client.post(f"/dashboard/resolve/{area_id}").status_code == 401
    ok = client.post(f"/dashboard/resolve/{area_id}", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    row = next(a for a in client.get("/dashboard").json()["areas"] if a["area_id"] == area_id)
    assert row["weeks_unresolved"] == 0


# ---------- heatmap ----------

def test_heatmap_can_hide_sample_data(client):
    everything = client.get("/heatmap").json()["points"]
    real_only = client.get("/heatmap?include_sample=false").json()["points"]
    assert any(p["is_sample"] for p in everything)
    assert real_only and not any(p["is_sample"] for p in real_only)


# ---------- rider reports ----------

def test_report_is_stored_coarsely_and_counts_as_report(client):
    before = counts()[0]
    r = client.post("/report", json={"lat": 17.44473, "lng": 78.46641, "hour": 21, "category": "harassment"})
    assert r.status_code == 201
    assert counts()[0] == before + 1
    conn = sqlite3.connect(config.DB_PATH)
    lat, lng, source, snippet = conn.execute(
        "SELECT lat, lng, source_type, snippet FROM incidents ORDER BY id DESC LIMIT 1").fetchone()
    assert (lat, lng) == (17.445, 78.466)  # ~100 m grid, never the exact spot
    assert source == "report"
    assert "Begumpet" in snippet


def test_report_outside_city_or_bad_category_is_rejected(client):
    assert client.post("/report", json={**DELHI, "hour": 21, "category": "harassment"}).status_code == 422
    assert client.post("/report", json={**BEGUMPET, "hour": 21, "category": "gossip"}).status_code == 422


def test_reports_are_rate_limited(client):
    statuses = [client.post("/report", json={**BEGUMPET, "hour": 21, "category": "stalking"}).status_code
                for _ in range(config.RATE_LIMITS["report"][0] + 1)]
    assert statuses[-1] == 429
    assert statuses[0] == 201


# ---------- SMS ----------

def twilio_signature(token, url, params):
    payload = url + "".join(k + v for k, v in sorted(params.items()))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def test_sms_returns_twiml(client):
    r = client.post("/sms", data={"Body": "RADAR Secunderabad 10PM"})
    assert r.headers["content-type"].startswith("application/xml")
    assert "<Message>RED:" in r.text


def test_sms_help_keyword_lists_emergency_number(client):
    assert "112" in client.post("/sms", data={"Body": "HELP"}).text


def test_sms_checks_twilio_signature_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "tw-token")
    params = {"Body": "RADAR Begumpet"}
    assert client.post("/sms", data=params).status_code == 403
    sig = twilio_signature("tw-token", "http://testserver/sms", params)
    assert client.post("/sms", data=params, headers={"X-Twilio-Signature": sig}).status_code == 200


def test_simulator_works_even_when_twilio_signatures_are_enforced(client, monkeypatch):
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "tw-token")
    r = client.post("/sms/simulate", json={"body": "RADAR Begumpet 9PM"})
    assert r.status_code == 200
    assert r.json()["reply"].startswith("GREEN: Begumpet")


def test_check_returns_hour_strip_and_options(client):
    r = client.post("/check", json={**SECUNDERABAD, "hour": 22}).json()
    assert len(r["hours"]) == 24
    assert r["level"] == "red"
    assert r["better_time"]["level"] in ("green", "amber")
    assert r["better_spot"] is None or r["better_spot"]["km"] <= config.BETTER_SPOT_KM


def test_not_covered_has_no_hour_strip(client):
    assert "hours" not in client.post("/check", json=DELHI).json()


GACHIBOWLI = {"lat": 17.4401, "lng": 78.3489}


def test_route_scores_every_stretch_offline(client, monkeypatch):
    monkeypatch.setattr(config, "ROUTING_URL", "")  # straight line, no network
    before = counts()
    r = client.post("/route", json={"start": GACHIBOWLI, "end": SECUNDERABAD, "hour": 22}).json()
    assert r["routing"] == "straight"
    assert r["level"] == "red"
    assert r["hotspots"][-1]["area"] == "Secunderabad Railway Station"
    assert {s["level"] for s in r["segments"]} >= {"green", "red"}
    assert counts() == before  # nothing stored


def test_route_outside_city_is_not_covered(client, monkeypatch):
    monkeypatch.setattr(config, "ROUTING_URL", "")
    r = client.post("/route", json={"start": GACHIBOWLI, "end": DELHI}).json()
    assert r["level"] == "not_covered"


def test_geocode_off_returns_empty_and_validates(client, monkeypatch):
    monkeypatch.setattr(config, "GEOCODE_URL", "")
    assert client.get("/geocode?q=inorbit").json() == {"results": []}
    assert client.get("/geocode?q=ab").status_code == 422


def test_area_detail_and_resolve_with_action(client):
    rows = client.get("/dashboard", headers={"Accept": "application/json"}).json()["areas"]
    flagged = next(a for a in rows if a["flagged"] and a["weeks_unresolved"] > 0)
    d = client.get(f"/dashboard/area/{flagged['area_id']}").json()
    assert d["count"] == flagged["incidents"] and sum(d["by_hour"]) == d["count"]
    assert d["peak"]["count"] >= 1 and d["directions"]["google"].startswith("https://www.google.com/maps/")
    assert client.post(f"/dashboard/resolve/{flagged['area_id']}", json={"action": "nonsense"}).status_code == 422
    ok = client.post(f"/dashboard/resolve/{flagged['area_id']}", json={"action": "patrol", "note": "Night patrol 21-24"})
    assert ok.status_code == 200
    flag = client.get(f"/dashboard/area/{flagged['area_id']}").json()["flag"]
    assert flag["resolution_label"] == "Added patrols at peak hours" and flag["resolution_note"] == "Night patrol 21-24"
    assert client.get("/dashboard/area/99999").status_code == 404
