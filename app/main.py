"""Ride Radar API and static page server."""
import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import clock, config, db, geocode, risk, route, service, sms, sos
from app.web import base_url, client_id, key_hash, limit, require_admin, require_owner

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ride_radar")

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",  # Leaflet sets inline styles on map tiles
    "img-src 'self' data: https://unpkg.com https://*.tile.openstreetmap.org",
    "connect-src 'self'",
    "font-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


@asynccontextmanager
async def lifespan(_app):
    conn = db.connect()
    try:
        db.init_schema(conn)
        empty = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0
        if empty and config.AUTO_SEED:
            loaded, skipped = db.seed(conn, db.default_incident_files(config.SEED_SAMPLE))
            log.info("seeded empty database: %d incidents, %d skipped", loaded, len(skipped))
        else:
            db.upsert_areas(conn, db.load_json("areas.json"))
        purged = conn.execute("DELETE FROM trip_shares WHERE expires_at < ?", (clock.iso(clock.utc_now()),)).rowcount
        conn.commit()
        if purged:
            log.info("purged %d expired trip shares", purged)
    finally:
        conn.close()
    if not config.ADMIN_TOKEN:
        log.warning("ADMIN_TOKEN is not set: anyone can mark dashboard areas addressed (fine for a demo only)")
    if not config.TWILIO_AUTH_TOKEN:
        log.warning("TWILIO_AUTH_TOKEN is not set: /sms accepts unsigned requests")
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(sos_sweeper())
    yield
    task.cancel()


async def sos_sweeper():
    """Sends SOS alerts whose deadline passed, even if the rider's phone went silent."""
    while True:
        try:
            await run_in_threadpool(sos.sweep)
        except Exception:
            log.exception("SOS sweep failed")
        await asyncio.sleep(config.SOS_SWEEP_SECONDS)


app = FastAPI(title="Ride Radar", version="1.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=800)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.include_router(sos.router)


@app.middleware("http")
async def headers_and_logging(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    h = response.headers
    h["Content-Security-Policy"] = CSP
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "no-referrer"  # trip links carry a secret token in the path
    h["X-Frame-Options"] = "DENY"
    h["Permissions-Policy"] = "geolocation=(self), camera=(self), microphone=(self)"
    if config.PUBLIC_BASE_URL.startswith("https://"):
        h["Strict-Transport-Security"] = "max-age=31536000"
    # /heatmap and /dashboard serve a page or JSON depending on Accept, so caches must key on it
    h["Vary"] = "Accept, Accept-Encoding"
    if request.url.path.startswith("/static/"):
        h.setdefault("Cache-Control", "no-cache")  # revalidate with ETag so new deploys show at once
    elif h.get("content-type", "").startswith("application/json"):
        h["Cache-Control"] = "no-store"
    path = request.url.path
    if path.startswith("/trip/"):
        path = "/trip/{token}" + path[path.find("/", 6):] if path.count("/") > 2 else "/trip/{token}"
    log.info("%s %s %d %.0fms", request.method, path, response.status_code, (time.perf_counter() - start) * 1000)
    return response


def get_conn():
    return db.connect()


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p != "body")
    return JSONResponse(status_code=422, content={"error": f"{field}: {first['msg']}"})


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Something went wrong on our side. Please try again."})


# ---------- pages ----------

def page(name):
    return FileResponse(config.STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


def wants_html(request):
    """Browsers navigating to /heatmap or /dashboard get the page; fetch() calls get JSON."""
    return "text/html" in request.headers.get("accept", "")


@app.get("/", include_in_schema=False)
def index_page():
    return page("index.html")


@app.get("/sim-sms", include_in_schema=False)
def sim_sms_page():
    return page("sim-sms.html")


@app.get("/privacy", include_in_schema=False)
def privacy_page():
    return page("privacy.html")


@app.get("/sos", include_in_schema=False)
def sos_page():
    return page("sos.html")


@app.get("/sos-console", include_in_schema=False)
def sos_console_page():
    return page("sos-console.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # served from the root so its scope covers the whole app
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/manifest.json", include_in_schema=False)
def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/healthz")
def healthz():
    conn = get_conn()
    try:
        incidents = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    finally:
        conn.close()
    return {"status": "ok", "city": config.CITY, "incidents": incidents, "time": clock.iso(clock.now())}


# ---------- risk check ----------

class CheckIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    hour: Optional[int] = Field(default=None, ge=0, le=23)


@app.post("/check", dependencies=[limit("check")])
def check(body: CheckIn):
    """Score a spot. Reads only: the location is never written to the database or the logs."""
    conn = get_conn()
    try:
        result = service.check_spot(conn, body.lat, body.lng, body.hour)
    finally:
        conn.close()
    result["city"] = config.CITY
    return result


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RouteIn(BaseModel):
    start: Point
    end: Point
    hour: Optional[int] = Field(default=None, ge=0, le=23)


@app.get("/route", include_in_schema=False)
def route_page():
    return page("route.html")


@app.post("/route", dependencies=[limit("route")])
async def check_route(body: RouteIn):
    """Score every stretch of a ride. Reads only: pickup and drop are never stored."""
    def run():
        conn = get_conn()
        try:
            return route.check_route(conn, (body.start.lat, body.start.lng),
                                     (body.end.lat, body.end.lng), body.hour)
        finally:
            conn.close()
    return await run_in_threadpool(run)


@app.get("/geocode", dependencies=[limit("geocode")])
async def geocode_search(q: str = Query(min_length=3, max_length=100), final: bool = False):
    """Address suggestions near the covered city. The query is not stored or logged."""
    conn = get_conn()
    try:
        box = geocode.bbox(db.all_areas(conn))
    finally:
        conn.close()
    results = await run_in_threadpool(geocode.search, q, box, final)
    return {"results": results}


@app.get("/areas")
def areas():
    conn = get_conn()
    try:
        return {
            "city": config.CITY, "center": config.CITY_CENTER, "areas": db.all_areas(conn),
            "categories": sorted(config.CATEGORIES), "helplines": config.HELPLINES,
        }
    finally:
        conn.close()


@app.get("/heatmap")
def heatmap(request: Request, hour: Optional[int] = None, include_sample: bool = True):
    if wants_html(request):
        return page("heatmap.html")
    if hour is not None and not 0 <= hour <= 23:
        raise HTTPException(422, "hour must be 0-23")
    conn = get_conn()
    try:
        incidents = db.all_incidents(conn, include_sample=include_sample)
    finally:
        conn.close()
    now = clock.now()
    points = []
    for inc in incidents:
        if hour is not None and not risk.hour_matches(inc["incident_hour"], hour):
            continue
        points.append({
            "lat": inc["lat"], "lng": inc["lng"],
            "weight": round(risk.incident_weight(inc, now, inc["incident_hour"]), 3),
            "area": inc["area_name"], "category": inc["category"], "date": inc["date"],
            "hour": inc["incident_hour"], "snippet": inc["snippet"], "source_type": inc["source_type"],
            "source_url": inc["source_url"], "is_sample": bool(inc["is_sample"]),
        })
    return {"city": config.CITY, "center": config.CITY_CENTER, "hour": hour, "points": points}


# ---------- dashboard ----------

@app.get("/dashboard")
def dashboard(request: Request):
    if wants_html(request):
        return page("dashboard.html")
    conn = get_conn()
    try:
        return {
            "city": config.CITY, "today": clock.now().date().isoformat(),
            "auth_required": bool(config.ADMIN_TOKEN), "areas": service.dashboard_rows(conn),
        }
    finally:
        conn.close()


@app.get("/dashboard/area/{area_id}")
def dashboard_area(area_id: int):
    conn = get_conn()
    try:
        detail = service.area_detail(conn, area_id)
    finally:
        conn.close()
    if detail is None:
        raise HTTPException(404, f"no area with id {area_id}")
    return detail


class ResolveIn(BaseModel):
    action: str = Field(max_length=32)
    note: str = Field(default="", max_length=280)


@app.post("/dashboard/resolve/{area_id}", dependencies=[Depends(require_admin)])
def resolve_area(area_id: int, body: Optional[ResolveIn] = None):
    if body and body.action not in config.RESOLUTION_ACTIONS:
        raise HTTPException(422, "unknown action")
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE authority_flags SET resolved_at = ?, resolution_action = ?, resolution_note = ? WHERE area_id = ?",
            (clock.iso(clock.now()), body.action if body else None, body.note.strip() if body else None, area_id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, f"no flagged area with id {area_id}")
        log.info("area %d marked addressed", area_id)
        return {"ok": True, "area_id": area_id}
    finally:
        conn.close()


# ---------- rider reports (P2) ----------

CATEGORY_TEXT = {
    "harassment": "harassment",
    "stalking": "being followed",
    "fare_dispute_threat": "a threat over the fare",
    "assault": "an assault",
    "other": "an unsafe ride",
}


class ReportIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    category: Literal["harassment", "stalking", "fare_dispute_threat", "assault", "other"]


@app.post("/report", status_code=201, dependencies=[limit("report")])
def report(body: ReportIn):
    """A rider's report. No free text, so it cannot name anyone; stored on a ~100 m grid."""
    conn = get_conn()
    try:
        area, km = service.nearest_area(body.lat, body.lng, db.all_areas(conn))
        if area is None or km > config.COVERAGE_KM:
            raise HTTPException(422, f"Reports are only accepted inside {config.CITY}.")
        now = clock.now()
        incident = {
            "is_sample": False,
            "source_type": "report",
            "source_url": "",
            "snippet": f"Rider report (unverified): {CATEGORY_TEXT[body.category]} near {area['name']}.",
            "area": area["name"],
            "lat": round(body.lat, config.REPORT_GRID_DECIMALS),
            "lng": round(body.lng, config.REPORT_GRID_DECIMALS),
            "incident_hour": now.hour if body.hour is None else body.hour,
            "date": now.date().isoformat(),
            "category": body.category,
        }
        new_id = db.insert_incident(conn, incident)
    finally:
        conn.close()
    log.info("rider report %d stored for %s", new_id, area["name"])
    return {"ok": True, "id": new_id, "area": area["name"]}


# ---------- trip share ----------

class TripPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


def _live_share(conn, token):
    """Return the share row, deleting expired shares on access."""
    conn.execute("DELETE FROM trip_shares WHERE expires_at < ?", (clock.iso(clock.utc_now()),))
    conn.commit()
    row = conn.execute("SELECT * FROM trip_shares WHERE token = ?", (token,)).fetchone()
    if not row:
        raise HTTPException(404, "This trip link has ended or does not exist.")
    return row


@app.post("/share", dependencies=[limit("share")])
def create_share(request: Request):
    token = secrets.token_urlsafe(12)
    owner_key = secrets.token_urlsafe(24)  # only the rider's browser holds this
    now = clock.utc_now()
    expires = now + timedelta(hours=config.TRIP_TTL_HOURS)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO trip_shares (token, owner_key_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, key_hash(owner_key), clock.iso(now), clock.iso(expires)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"token": token, "owner_key": owner_key, "url": f"{base_url(request)}/trip/{token}",
            "expires_at": clock.iso(expires)}


@app.post("/trip/{token}/update", dependencies=[limit("trip_update")])
def update_trip(token: str, point: TripPoint, request: Request):
    conn = get_conn()
    try:
        require_owner(_live_share(conn, token), request)
        # only the latest point is kept; each update overwrites the previous one
        conn.execute(
            "UPDATE trip_shares SET last_lat = ?, last_lng = ?, last_updated = ? WHERE token = ?",
            (point.lat, point.lng, clock.iso(clock.utc_now()), token),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/trip/{token}")
def stop_trip(token: str, request: Request):
    conn = get_conn()
    try:
        require_owner(_live_share(conn, token), request)
        conn.execute("DELETE FROM trip_shares WHERE token = ?", (token,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/trip/{token}", include_in_schema=False)
def trip_page(token: str):
    return page("trip.html")


@app.get("/trip/{token}/data")
def trip_data(token: str):
    conn = get_conn()
    try:
        row = _live_share(conn, token)
    finally:
        conn.close()
    seconds_ago = None
    if row["last_updated"]:
        updated = datetime.fromisoformat(row["last_updated"])
        if updated.tzinfo is None:  # rows written before timestamps carried a zone were UTC
            updated = updated.replace(tzinfo=timezone.utc)
        seconds_ago = max(0, int((clock.utc_now() - updated).total_seconds()))
    return {
        "lat": row["last_lat"], "lng": row["last_lng"], "last_updated": row["last_updated"],
        "seconds_ago": seconds_ago, "expires_at": row["expires_at"],
    }


# ---------- SMS ----------

def twilio_signature_ok(url, params, signature):
    payload = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(
        hmac.new(config.TWILIO_AUTH_TOKEN.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature or "")


def sms_reply(body):
    keyword = sms.keyword_reply(body)
    if keyword:
        return keyword
    conn = get_conn()
    try:
        names = [a["name"] for a in db.all_areas(conn)]
        area_name, hour = sms.parse(body, names)
        if not area_name:
            return sms.HELP
        area = db.area_by_name(conn, area_name)
        result = service.check_spot(conn, area["lat"], area["lng"], hour)
        return sms.reply_text(area_name, result["hour"], result)
    finally:
        conn.close()


@app.post("/sms", dependencies=[limit("sms")])
async def sms_webhook(request: Request):
    """Twilio webhook: form-encoded Body in, TwiML out."""
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if config.TWILIO_AUTH_TOKEN:
        url = (config.PUBLIC_BASE_URL + request.url.path) if config.PUBLIC_BASE_URL else str(request.url)
        if not twilio_signature_ok(url, params, request.headers.get("x-twilio-signature")):
            raise HTTPException(403, "Invalid Twilio signature.")
    text = await run_in_threadpool(sms_reply, params.get("Body", ""))
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")


class SimulatedSms(BaseModel):
    body: str = Field(max_length=320)


@app.post("/sms/simulate", dependencies=[limit("sms")])
def sms_simulate(msg: SimulatedSms):
    """Same reply as /sms, for the on-screen phone. No Twilio signature, so it never sends anything."""
    return {"reply": sms_reply(msg.body)}
