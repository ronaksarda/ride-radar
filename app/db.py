"""SQLite connection, schema, and the few queries the app needs."""
import json
import math
import sqlite3
from datetime import date

from app import clock, config

SCHEMA = """
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    lat REAL NOT NULL,
    lng REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN ('news', 'report')),
    source_url TEXT NOT NULL,
    snippet TEXT NOT NULL,
    area_id INTEGER NOT NULL REFERENCES areas(id),
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    incident_hour INTEGER NOT NULL CHECK (incident_hour BETWEEN 0 AND 23),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    is_sample INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trip_shares (
    token TEXT PRIMARY KEY,
    owner_key_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_lat REAL,
    last_lng REAL,
    last_updated TEXT
);
CREATE TABLE IF NOT EXISTS authority_flags (
    area_id INTEGER PRIMARY KEY REFERENCES areas(id),
    first_flagged_date TEXT NOT NULL,
    resolved_at TEXT,
    resolution_action TEXT,
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_incidents_lat_lng ON incidents (lat, lng);
CREATE TABLE IF NOT EXISTS sos_alerts (
    id TEXT PRIMARY KEY,                 -- also the secret in the alert link
    owner_key_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('recording', 'countdown', 'cancelled', 'sent')),
    created_at TEXT NOT NULL,
    deadline TEXT,                       -- send automatically after this unless cancelled
    sent_at TEXT,
    duress INTEGER NOT NULL DEFAULT 0,
    lat REAL,
    lng REAL,
    location_updated TEXT,
    contacts_json TEXT NOT NULL DEFAULT '[]',  -- cleared once the alert is sent
    video_path TEXT,
    video_mime TEXT,
    video_bytes INTEGER NOT NULL DEFAULT 0,
    chunks INTEGER NOT NULL DEFAULT 0,
    video_sha256 TEXT,
    whatsapp_status TEXT,
    summary TEXT,
    transcript TEXT,
    severity TEXT,
    ai_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_sos_state_deadline ON sos_alerts (state, deadline);
"""

# Columns added after the first release, applied to older databases at startup.
MIGRATIONS = [
    ("trip_shares", "owner_key_hash", "ALTER TABLE trip_shares ADD COLUMN owner_key_hash TEXT NOT NULL DEFAULT ''"),
    ("authority_flags", "resolution_action", "ALTER TABLE authority_flags ADD COLUMN resolution_action TEXT"),
    ("authority_flags", "resolution_note", "ALTER TABLE authority_flags ADD COLUMN resolution_note TEXT"),
]


def connect(path=None):
    conn = sqlite3.connect(path or config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(conn):
    conn.execute("PRAGMA journal_mode = WAL")  # readers do not block the writer
    conn.executescript(SCHEMA)
    for table, column, sql in MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(sql)
    conn.commit()


def load_json(name):
    with open(config.DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def default_incident_files(include_sample=True):
    files = [config.DATA_DIR / "incidents.json"]
    sample = config.DATA_DIR / "sample_incidents.json"
    if include_sample and sample.exists():
        files.append(sample)
    return files


def seed(conn, incident_files):
    """Load areas.json and the given incident files. Returns (loaded, skipped messages)."""
    upsert_areas(conn, load_json("areas.json"))
    incidents = []
    for path in incident_files:
        with open(path, encoding="utf-8") as f:
            incidents.extend(json.load(f))
    loaded, skipped = 0, []
    for i, inc in enumerate(incidents):
        try:
            insert_incident(conn, inc, commit=False)
            loaded += 1
        except ValueError as e:
            skipped.append(f"entry {i}: {e}")
    conn.commit()
    return loaded, skipped


def upsert_areas(conn, areas):
    for a in areas:
        conn.execute(
            "INSERT INTO areas (id, name, lat, lng) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, lat=excluded.lat, lng=excluded.lng",
            (a["id"], a["name"], a["lat"], a["lng"]),
        )
    conn.commit()


def area_by_name(conn, name):
    row = conn.execute("SELECT * FROM areas WHERE lower(name) = lower(?)", (name,)).fetchone()
    return dict(row) if row else None


def validate_incident(inc):
    """Raise ValueError if an incident dict breaks the data rules."""
    for key in ("source_type", "snippet", "area", "lat", "lng", "incident_hour", "date", "category"):
        if key not in inc or inc[key] in (None, ""):
            raise ValueError(f"missing field: {key}")
    if inc["source_type"] not in config.SOURCE_WEIGHTS:
        raise ValueError(f"bad source_type: {inc['source_type']}")
    if inc["source_type"] == "news" and not inc.get("source_url"):
        raise ValueError("news incidents need a source_url")
    if inc["category"] not in config.CATEGORIES:
        raise ValueError(f"bad category: {inc['category']}")
    if not (-90 <= float(inc["lat"]) <= 90 and -180 <= float(inc["lng"]) <= 180):
        raise ValueError("lat/lng out of range")
    if not 0 <= int(inc["incident_hour"]) <= 23:
        raise ValueError("incident_hour must be 0-23")
    date.fromisoformat(inc["date"])
    if len(inc["snippet"]) > 240:
        raise ValueError("snippet must be one short sentence")


def insert_incident(conn, inc, commit=True):
    validate_incident(inc)
    area = area_by_name(conn, inc["area"])
    if not area:
        raise ValueError(f"unknown area: {inc['area']} (add it to data/areas.json)")
    cur = conn.execute(
        "INSERT INTO incidents (source_type, source_url, snippet, area_id, lat, lng, incident_hour, date, category, is_sample) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (inc["source_type"], inc.get("source_url") or "", inc["snippet"], area["id"], inc["lat"], inc["lng"],
         int(inc["incident_hour"]), inc["date"], inc["category"], 1 if inc.get("is_sample") else 0),
    )
    flag_area(conn, area["id"], inc["date"])
    if commit:
        conn.commit()
    return cur.lastrowid


def flag_area(conn, area_id, incident_date):
    """Open a flag for the area, or re-open it if an incident arrives after it was resolved.

    Incidents older than FLAG_WINDOW_DAYS never open a flag, so a 2017 report
    does not show up as "400 weeks unresolved".
    """
    if (clock.now().date() - date.fromisoformat(incident_date)).days > config.FLAG_WINDOW_DAYS:
        return
    row = conn.execute("SELECT * FROM authority_flags WHERE area_id = ?", (area_id,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO authority_flags (area_id, first_flagged_date) VALUES (?, ?)", (area_id, incident_date))
    elif row["resolved_at"] is None:
        if incident_date < row["first_flagged_date"]:
            conn.execute("UPDATE authority_flags SET first_flagged_date = ? WHERE area_id = ?", (incident_date, area_id))
    elif incident_date > row["resolved_at"][:10]:
        conn.execute(
            "UPDATE authority_flags SET first_flagged_date = ?, resolved_at = NULL WHERE area_id = ?",
            (incident_date, area_id),
        )


def all_incidents(conn, include_sample=True):
    sql = "SELECT i.*, a.name AS area_name FROM incidents i JOIN areas a ON a.id = i.area_id"
    if not include_sample:
        sql += " WHERE i.is_sample = 0"
    return [dict(r) for r in conn.execute(sql)]


def incidents_near(conn, lat, lng, km):
    """Incidents inside a bounding box around the point. The caller does the exact distance check."""
    dlat = km / 111.0
    dlng = km / (111.0 * max(0.01, math.cos(math.radians(lat))))
    rows = conn.execute(
        "SELECT i.*, a.name AS area_name FROM incidents i JOIN areas a ON a.id = i.area_id "
        "WHERE i.lat BETWEEN ? AND ? AND i.lng BETWEEN ? AND ?",
        (lat - dlat, lat + dlat, lng - dlng, lng + dlng),
    )
    return [dict(r) for r in rows]


def all_areas(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM areas ORDER BY name")]
