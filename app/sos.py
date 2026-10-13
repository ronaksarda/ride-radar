"""SOS: hold to record, release to lock, countdown, then alert contacts and authorities.

Lifecycle of one alert:
    recording  -> video chunks upload while the rider holds the button
    countdown  -> rider let go; sends at the deadline unless the PIN cancels it
    sent       -> contacts notified, video hashed, AI brief written
    cancelled  -> correct PIN entered; the video is deleted at once

The server owns the deadline, so an alert still goes out if the phone is snatched,
the app is closed, or the battery dies mid-recording.
"""
import hashlib
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from app import clock, config, db, groq_client, notify, service
from app.web import base_url, key_hash, limit, require_admin, require_owner

log = logging.getLogger("ride_radar.sos")
router = APIRouter()
PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
EXTENSIONS = {"video/webm": ".webm", "video/mp4": ".mp4", "audio/webm": ".webm", "audio/mp4": ".m4a"}


# ---------- models ----------

class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    phone: str

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v):
        v = re.sub(r"[\s()-]", "", v)
        if not PHONE_RE.match(v):
            raise ValueError("use the full number with country code, e.g. +919812345678")
        return v


class SosStart(BaseModel):
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    contacts: List[Contact] = Field(default_factory=list, max_length=config.SOS_MAX_CONTACTS)


class SosSend(BaseModel):
    duress: bool = False


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


# ---------- helpers ----------

def _now():
    return clock.utc_now()


def _parse(ts):
    return datetime.fromisoformat(ts) if ts else None


def _alert(conn, alert_id):
    row = conn.execute("SELECT * FROM sos_alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        raise HTTPException(404, "No such alert.")
    return row


def _video_path(alert_id, mime):
    return config.MEDIA_DIR / f"{alert_id}{EXTENSIONS.get(mime.split(';')[0].strip(), '.webm')}"


def _area_name(conn, lat, lng):
    if lat is None:
        return None
    area, km = service.nearest_area(lat, lng, db.all_areas(conn))
    return area["name"] if area and km <= config.COVERAGE_KM else None


def _delete_video(row):
    if row["video_path"]:
        try:
            Path(row["video_path"]).unlink(missing_ok=True)
        except OSError as e:
            log.error("could not delete video for %s: %s", row["id"], e)


def _template_summary(row, area, duress):
    when = _parse(row["created_at"]).astimezone(clock.CITY_TZ)
    place = f"near {area}" if area else "at the location shown"
    loc = f" Last location {row['lat']:.5f}, {row['lng']:.5f}." if row["lat"] is not None else " No location received."
    video = (f" Video {row['video_bytes'] // 1024} KB, SHA-256 {row['video_sha256'][:16]}…."
             if row["video_bytes"] else " No video received.")
    pressure = " The rider entered the duress PIN: they may be with the person threatening them." if duress else ""
    return (f"SOS from a Ride Radar user {place} at {when:%H:%M} on {when:%d %b %Y} (IST).{loc}{video}{pressure}")


# ---------- dispatch ----------

def dispatch(conn, alert_id, duress=False, request_base=None):
    """Send an alert once. Safe to call again: later calls return the stored status."""
    row = _alert(conn, alert_id)
    if row["state"] == "sent":
        return {"state": "sent", "whatsapp": row["whatsapp_status"], "whatsapp_links": []}
    if row["state"] == "cancelled":
        raise HTTPException(409, "This alert was cancelled.")
    digest = None
    if row["video_path"]:
        h = hashlib.sha256()
        with open(row["video_path"], "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        digest = h.hexdigest()
    now = clock.iso(_now())
    conn.execute(
        "UPDATE sos_alerts SET state = 'sent', sent_at = ?, deadline = NULL, duress = ?, video_sha256 = ? "
        "WHERE id = ? AND state IN ('recording', 'countdown')",
        (now, 1 if duress else row["duress"], digest, alert_id),
    )
    conn.commit()
    row = _alert(conn, alert_id)
    area = _area_name(conn, row["lat"], row["lng"])
    url = f"{request_base or config.PUBLIC_BASE_URL or ''}/alert/{alert_id}"
    status, links = notify.notify_contacts(json.loads(row["contacts_json"]), url)
    summary = _template_summary(row, area, bool(row["duress"]))
    ai_status = "pending" if groq_client.enabled() and row["video_path"] else "skipped"
    # contacts' numbers are only needed to notify them; drop them now
    conn.execute(
        "UPDATE sos_alerts SET whatsapp_status = ?, summary = ?, ai_status = ?, contacts_json = '[]' WHERE id = ?",
        (status, summary, ai_status, alert_id),
    )
    conn.commit()
    log.warning("SOS %s sent (area=%s, duress=%s, whatsapp=%s)", alert_id[:6], area, bool(row["duress"]), status)
    if ai_status == "pending":
        threading.Thread(target=enrich_with_ai, args=(alert_id,), daemon=True).start()
    return {"state": "sent", "whatsapp": status, "whatsapp_links": links}


BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "brief": {"type": "string", "description": "3 short factual sentences for police"},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["brief", "severity"],
    "additionalProperties": False,
}


def enrich_with_ai(alert_id):
    """Transcribe the video's audio with Whisper on Groq and write a short brief for responders."""
    conn = db.connect()
    try:
        row = _alert(conn, alert_id)
        transcript = ""
        if row["video_path"] and row["video_bytes"] <= 24 * 1024 * 1024:  # Groq upload limit is 25 MB
            transcript = groq_client.transcribe(row["video_path"], row["video_mime"] or "video/webm")
        area = _area_name(conn, row["lat"], row["lng"])
        facts = {
            "time_ist": _parse(row["created_at"]).astimezone(clock.CITY_TZ).strftime("%H:%M %d %b %Y"),
            "area": area, "lat": row["lat"], "lng": row["lng"], "duress_pin_used": bool(row["duress"]),
            "audio_transcript": transcript or "(no speech detected)",
        }
        result = groq_client.chat_json(
            "You write a short factual brief for police about an SOS sent by a woman during an auto or cab ride. "
            "Use only the facts and transcript given. Say what can be heard, quoting at most a few words. "
            "Mark anything uncertain as uncertain. Never guess names, faces or vehicle numbers. "
            "Severity is high if the transcript suggests threats, violence or being held; low if it is unclear.",
            json.dumps(facts, ensure_ascii=False), BRIEF_SCHEMA, name="sos_brief",
        )
        summary = f"{row['summary']} AI brief: {result['brief']}"
        conn.execute("UPDATE sos_alerts SET summary = ?, transcript = ?, severity = ?, ai_status = 'done' WHERE id = ?",
                     (summary, transcript, result["severity"], alert_id))
        conn.commit()
    except Exception as e:  # the alert is already out; a failed brief must never break anything
        log.error("AI brief failed for %s: %s", alert_id[:6], e)
        conn.execute("UPDATE sos_alerts SET ai_status = 'failed' WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()


def sweep(now=None):
    """Send every alert whose deadline passed, and delete old videos. Returns the ids sent."""
    now = now or _now()
    conn = db.connect()
    sent = []
    try:
        due = conn.execute(
            "SELECT id FROM sos_alerts WHERE state IN ('recording', 'countdown') AND deadline < ?",
            (clock.iso(now),)).fetchall()
        for row in due:
            dispatch(conn, row["id"])
            sent.append(row["id"])
        cutoff = clock.iso(now - timedelta(days=config.SOS_RETENTION_DAYS))
        for row in conn.execute("SELECT * FROM sos_alerts WHERE state = 'sent' AND sent_at < ? AND video_path IS NOT NULL",
                                (cutoff,)).fetchall():
            _delete_video(row)
            conn.execute("UPDATE sos_alerts SET video_path = NULL WHERE id = ?", (row["id"],))
        conn.execute("DELETE FROM sos_alerts WHERE state = 'cancelled' AND created_at < ?",
                     (clock.iso(now - timedelta(days=1)),))
        conn.commit()
    finally:
        conn.close()
    return sent


# ---------- rider endpoints ----------

@router.post("/sos", status_code=201, dependencies=[limit("sos")])
def start(body: SosStart, request: Request):
    alert_id = secrets.token_urlsafe(12)
    owner_key = secrets.token_urlsafe(24)
    now = _now()
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO sos_alerts (id, owner_key_hash, state, created_at, deadline, lat, lng, location_updated, "
            "contacts_json) VALUES (?, ?, 'recording', ?, ?, ?, ?, ?, ?)",
            (alert_id, key_hash(owner_key), clock.iso(now),
             clock.iso(now + timedelta(seconds=config.SOS_SILENCE_SECONDS)),
             body.lat, body.lng, clock.iso(now) if body.lat is not None else None,
             json.dumps([c.model_dump() for c in body.contacts])),
        )
        conn.commit()
    finally:
        conn.close()
    log.warning("SOS %s started", alert_id[:6])
    return {"id": alert_id, "owner_key": owner_key, "alert_url": f"{base_url(request)}/alert/{alert_id}",
            "countdown_seconds": config.SOS_COUNTDOWN_SECONDS, "silence_seconds": config.SOS_SILENCE_SECONDS}


@router.post("/sos/{alert_id}/chunk", dependencies=[limit("sos_chunk")])
async def chunk(alert_id: str, request: Request):
    data = await request.body()
    if len(data) > config.SOS_CHUNK_MAX_BYTES:
        raise HTTPException(413, "Chunk too large.")
    conn = db.connect()
    try:
        row = _alert(conn, alert_id)
        require_owner(row, request)
        if row["state"] != "recording":
            raise HTTPException(409, f"Alert is {row['state']}.")
        try:
            index = int(request.headers.get("x-chunk-index", ""))
        except ValueError:
            raise HTTPException(422, "X-Chunk-Index header required.") from None
        if index != row["chunks"]:
            return JSONResponse(status_code=409, content={"error": "Chunk out of order.", "expected": row["chunks"]})
        if row["video_bytes"] + len(data) > config.SOS_MAX_VIDEO_BYTES:
            raise HTTPException(413, "Video limit reached.")
        mime = row["video_mime"] or request.headers.get("content-type", "video/webm").split(";")[0].strip()
        path = row["video_path"] or str(_video_path(alert_id, mime))
        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as f:
            f.write(data)
        now = _now()
        conn.execute(
            "UPDATE sos_alerts SET chunks = chunks + 1, video_bytes = video_bytes + ?, video_path = ?, video_mime = ?, "
            "deadline = ? WHERE id = ?",
            (len(data), path, mime, clock.iso(now + timedelta(seconds=config.SOS_SILENCE_SECONDS)), alert_id),
        )
        conn.commit()
        return {"ok": True, "next": index + 1}
    finally:
        conn.close()


@router.post("/sos/{alert_id}/location")
def location(alert_id: str, point: Point, request: Request):
    conn = db.connect()
    try:
        row = _alert(conn, alert_id)
        require_owner(row, request)
        if row["state"] == "cancelled":
            raise HTTPException(409, "Alert was cancelled.")
        if row["sent_at"] and _now() - _parse(row["sent_at"]) > timedelta(hours=config.TRIP_TTL_HOURS):
            raise HTTPException(410, "Live location for this alert has ended.")
        conn.execute("UPDATE sos_alerts SET lat = ?, lng = ?, location_updated = ? WHERE id = ?",
                     (point.lat, point.lng, clock.iso(_now()), alert_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/sos/{alert_id}/release")
def release(alert_id: str, request: Request):
    """Finger lifted: recording is locked and the countdown starts."""
    conn = db.connect()
    try:
        row = _alert(conn, alert_id)
        require_owner(row, request)
        if row["state"] != "recording":
            return {"state": row["state"]}
        # a few seconds of grace so the phone's own countdown normally finishes first
        deadline = _now() + timedelta(seconds=config.SOS_COUNTDOWN_SECONDS + config.SOS_GRACE_SECONDS)
        conn.execute("UPDATE sos_alerts SET state = 'countdown', deadline = ? WHERE id = ?",
                     (clock.iso(deadline), alert_id))
        conn.commit()
        return {"state": "countdown", "deadline": clock.iso(deadline)}
    finally:
        conn.close()


@router.post("/sos/{alert_id}/send")
def send(alert_id: str, request: Request, body: SosSend = SosSend()):
    conn = db.connect()
    try:
        require_owner(_alert(conn, alert_id), request)
        return dispatch(conn, alert_id, duress=body.duress, request_base=base_url(request))
    finally:
        conn.close()


@router.post("/sos/{alert_id}/cancel")
def cancel(alert_id: str, request: Request):
    """Correct PIN entered: false alarm. The video is deleted immediately."""
    conn = db.connect()
    try:
        row = _alert(conn, alert_id)
        require_owner(row, request)
        if row["state"] == "sent":
            raise HTTPException(409, "This alert was already sent.")
        _delete_video(row)
        conn.execute("UPDATE sos_alerts SET state = 'cancelled', deadline = NULL, video_path = NULL, "
                     "contacts_json = '[]' WHERE id = ?", (alert_id,))
        conn.commit()
        log.info("SOS %s cancelled by PIN", alert_id[:6])
        return {"state": "cancelled"}
    finally:
        conn.close()


# ---------- viewers: contacts (by secret link) and authorities ----------

def public_view(conn, row):
    if row["state"] == "cancelled":
        return {"state": "cancelled"}
    sent = row["state"] == "sent"
    return {
        "id": row["id"], "state": row["state"], "created_at": row["created_at"], "sent_at": row["sent_at"],
        "lat": row["lat"], "lng": row["lng"], "location_updated": row["location_updated"],
        "area": _area_name(conn, row["lat"], row["lng"]), "duress": bool(row["duress"]),
        "summary": row["summary"], "transcript": row["transcript"], "severity": row["severity"],
        "ai_status": row["ai_status"], "video_sha256": row["video_sha256"], "video_bytes": row["video_bytes"],
        "video_url": f"/alert/{row['id']}/video" if sent and row["video_path"] else None,
        "helplines": config.HELPLINES,
    }


@router.get("/alert/{alert_id}", include_in_schema=False)
def alert_page(alert_id: str):
    return FileResponse(config.STATIC_DIR / "alert.html", headers={"Cache-Control": "no-cache"})


@router.get("/alert/{alert_id}/data")
def alert_data(alert_id: str):
    conn = db.connect()
    try:
        return public_view(conn, _alert(conn, alert_id))
    finally:
        conn.close()


@router.get("/alert/{alert_id}/video")
def alert_video(alert_id: str):
    conn = db.connect()
    try:
        row = _alert(conn, alert_id)
    finally:
        conn.close()
    if row["state"] != "sent" or not row["video_path"]:
        raise HTTPException(404, "No video for this alert.")
    return FileResponse(row["video_path"], media_type=row["video_mime"] or "video/webm",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/sos/alerts", dependencies=[Depends(require_admin)])
def console_alerts():
    conn = db.connect()
    try:
        since = clock.iso(_now() - timedelta(days=7))
        rows = conn.execute("SELECT * FROM sos_alerts WHERE state = 'sent' AND sent_at > ? ORDER BY sent_at DESC",
                            (since,)).fetchall()
        return {"alerts": [public_view(conn, r) for r in rows]}
    finally:
        conn.close()
