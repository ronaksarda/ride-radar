"""All tunable settings in one place. Change the city or thresholds here."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / ".env"):
    """Read KEY=value lines from .env into os.environ. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


load_dotenv()

# Deployment settings come from the environment (or .env). See .env.example.
DB_PATH = Path(os.environ.get("RIDE_RADAR_DB", ROOT / "ride_radar.db"))
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")  # e.g. https://radar.example.org
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")            # empty = dashboard actions open (demo only)
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")  # set it to verify X-Twilio-Signature
AUTO_SEED = os.environ.get("AUTO_SEED", "1") != "0"         # seed an empty database at startup
SEED_SAMPLE = os.environ.get("SEED_SAMPLE", "1") != "0"     # include data/sample_incidents.json
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# City. To swap cities, change these and replace data/areas.json + data/incidents.json.
CITY = "Hyderabad"
CITY_CENTER = (17.3850, 78.4867)
TZ_OFFSET_MINUTES = 330  # IST, UTC+5:30, no daylight saving. The hour of day is always city time.

# Shown on amber and red results. Numbers verified 2026-10-11; check before each deployment.
HELPLINES = [
    {"label": "Emergency", "number": "112", "href": "tel:112"},
    {"label": "Women helpline", "number": "181", "href": "tel:181"},
    {"label": "SHE Teams Hyderabad (WhatsApp)", "number": "9490616555", "href": "https://wa.me/919490616555"},
    {"label": "SHE Teams Cyberabad (WhatsApp)", "number": "9490617444", "href": "https://wa.me/919490617444"},
]

# Scoring
RADIUS_KM = 1.0          # incidents counted within this distance of the rider
COVERAGE_KM = 5.0        # no seeded area within this distance -> "not covered yet"
# Route check. OSRM server for road routes; empty string = straight line only.
# The public demo server is fine for a hackathon. It receives pickup and drop
# coordinates, so self-host OSRM for production.
ROUTING_URL = os.environ.get("ROUTING_URL", "https://router.project-osrm.org")
# Address search on the route page (Photon, OpenStreetMap). Empty = areas only.
# The public server receives what the rider types, so self-host for production.
GEOCODE_URL = os.environ.get("GEOCODE_URL", "https://photon.komoot.io")
# Submit-time fallback when type-ahead finds nothing (single searches only, per its policy).
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
GEOCODE_USER_AGENT = os.environ.get("GEOCODE_USER_AGENT", "ride-radar/1.1 (hackathon demo)")
ROUTE_STEP_KM = 0.5         # score a point every 500 m along the route
FALLBACK_SPEED_KMH = 20.0   # straight-line fallback: city traffic speed for ETA
BETTER_SPOT_KM = 5.0      # amber/red: suggest the nearest lower-level area within this distance
SOURCE_WEIGHTS = {"news": 1.0, "report": 0.6}
HALF_LIFE_DAYS = 180     # recency weight halves every ~6 months
HOUR_WINDOW = 2          # +/- hours counted as "around this hour"
OFF_HOUR_FACTOR = 0.4    # weight for incidents outside the hour window
AMBER_MIN = 2            # total weight >= AMBER_MIN -> amber
RED_MIN = 5              # total weight > RED_MIN -> red

# Dashboard: only incidents this recent open an authority flag
FLAG_WINDOW_DAYS = 365

# Trip share
TRIP_TTL_HOURS = 3

# SOS: hold-to-record alert
MEDIA_DIR = Path(os.environ.get("RIDE_RADAR_MEDIA", ROOT / "media"))
SOS_COUNTDOWN_SECONDS = 10       # after release, the alert sends unless the PIN cancels it
SOS_GRACE_SECONDS = 5           # server waits this much longer than the phone's countdown
SOS_SILENCE_SECONDS = 30         # recording with no new video for this long sends (phone taken / app killed)
SOS_SWEEP_SECONDS = 2            # how often the server checks for alerts that are due
SOS_MAX_VIDEO_BYTES = 100 * 1024 * 1024
SOS_CHUNK_MAX_BYTES = 8 * 1024 * 1024
SOS_RETENTION_DAYS = 30          # sent videos are deleted after this; cancelled ones immediately
SOS_MAX_CONTACTS = 5

# Groq (free tier): AI brief for SOS alerts and the news extraction script
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_WHISPER_MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

# WhatsApp Cloud API (Meta). All three must be set for automatic sending; otherwise the
# phone opens prefilled WhatsApp messages and the rider taps send.
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TEMPLATE = os.environ.get("WHATSAPP_TEMPLATE", "")  # approved template: {{1}} name, {{2}} alert link
WHATSAPP_TEMPLATE_LANG = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
WHATSAPP_API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v21.0")

# Rider reports are stored on a grid this coarse (3 decimals ~ 110 m), never the exact spot
REPORT_GRID_DECIMALS = 3

# Per-client limits: name -> (requests, window in seconds)
RATE_LIMITS = {
    "check": (30, 60),
    "route": (20, 60),
    "geocode": (60, 60),
    "share": (5, 3600),
    "trip_update": (40, 60),
    "report": (3, 3600),
    "sms": (20, 60),
    "admin": (30, 60),
    "sos": (6, 3600),
    "sos_chunk": (600, 60),
}

# What an officer did when marking an area addressed.
RESOLUTION_ACTIONS = {
    "patrol": "Added patrols at peak hours",
    "lighting": "Fixed or added street lighting",
    "cctv": "Installed or repaired CCTV",
    "auto_stand": "Set up a supervised auto/cab stand",
    "driver_checks": "Ran driver verification checks",
    "awareness": "Ran an awareness drive",
    "other": "Other action",
}

CATEGORIES = {"harassment", "stalking", "fare_dispute_threat", "assault", "other"}
