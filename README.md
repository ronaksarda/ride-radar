# Ride Radar

> Instant transit incident intelligence and route risk scoring for cabs and autos in Hyderabad.

Ride Radar is a mobile web app designed to help women evaluate transit risk before boarding an auto or cab. A rider taps once to get a Green, Amber, or Red rating for their location and the current hour, accompanied by a concise explanation and links to local news reports. 

The system also scores entire driving routes, provides SMS fallbacks for phones without data connections, includes a hold-to-record SOS mode with duress protection, and powers an authority dashboard for municipal monitoring.

> **Note on Safety:** A Green rating means *"No reported incidents nearby"*. The app intentionally avoids ever labeling an area or route as "safe".

---

## Features

- **One-Tap Risk Assessment (`/`)**: Calculates nearby incident density within 1 km for the target hour. Green, Amber, or Red rating with links to news articles.
- **24-Hour Timeline & Alternative Spot Finder**: Displays an hourly risk strip, the next lower-risk hour within 12 hours, and the closest covered area within 5 km that currently has a lower rating.
- **Route Risk Scoring (`/route`)**: Queries road geometry via OSRM, evaluates risk at 500-meter intervals, adjusts for elapsed travel time, and displays color-coded route segments.
- **Offline & SMS Fallback (`/sms`, `/sim-sms`)**: Service worker caching for the web interface and an SMS parser that delivers replies under 160 characters without requiring mobile data.
- **Live Trip Sharing (`/trip/{token}`)**: Generates a temporary 3-hour tracking link that updates location every 10 seconds.
- **SOS with Duress Handling (`/sos`)**: Hold-to-stream video and GPS. Includes a standard cancel PIN and a hidden duress PIN (hashed client-side via PBKDF2-SHA256). The backend enforces a 30-second disconnect timeout to dispatch alerts even if the device is lost or disabled.
- **Authority Dashboard (`/dashboard`)**: Aggregates incident hotspots, tracks unresolved durations, shows peak 3-hour windows, and allows officials to log interventions (patrols, lighting, CCTV).

---

## How the Risk Score Works

The score evaluates all incidents within a 1 km radius for coordinate $L$ at hour $h \in [0, 23]$:

$$\text{Risk Score}(L, h) = \sum_{i \in \text{Incidents within 1 km}} w_i$$

Each incident weight $w_i$ is determined by source reliability, recency, and hour alignment:

$$w_i = S_i \times R_i \times H_i$$

- **Source ($S_i$):** Verified news reports count as $1.0$; direct user reports count as $0.6$.
- **Recency Decay ($R_i$):** Weights decay exponentially with a 180-day half-life:
  $$R_i = (0.5)^{\frac{\Delta t_i}{180}}$$
  where $\Delta t_i$ is the number of days elapsed since the incident.
- **Hour Match ($H_i$):** Accounts for cyclical midnight wrapping ($\Delta h_i = \min(|h - h_i|, 24 - |h - h_i|)$):
  - $H_i = 1.0$ if $\Delta h_i \le 2$ hours
  - $H_i = 0.4$ if $\Delta h_i > 2$ hours

### Risk Thresholds

- **Green:** Score $< 2.0$
- **Amber:** Score $2.0 \le \text{Score} \le 5.0$
- **Red:** Score $> 5.0$

*Coordinates farther than 5 km from any covered area return `"Not covered yet"` without assigning a score.*

---

## Quickstart

### Local Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Seed database (creates ride_radar.db with real and sample data)
python scripts/seed.py

# 3. Start development server
uvicorn app.main:app --reload

# 4. Run automated tests
python -m pytest
```

### Docker

```bash
docker build -t ride-radar .
docker run -p 8000:8000 ride-radar
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Application Endpoints

| Endpoint | Description |
|---|---|
| `/` | One-tap location risk assessment |
| `/route` | Turn-by-turn route risk evaluator |
| `/heatmap` | City-wide incident density map |
| `/dashboard` | Municipal authority dashboard |
| `/sos` | Emergency hold-to-stream recorder with duress PIN |
| `/sos-console` | Authority console for active SOS alerts |
| `/sim-sms` | Virtual SMS simulator for offline feature testing |
| `/docs` | Interactive Swagger API documentation |

---

## Configuration

Copy `.env.example` to `.env` to configure optional integrations:

```bash
cp .env.example .env
```

| Key | Description | Default |
|---|---|---|
| `GROQ_API_KEY` | Optional API key for automated incident extraction and SOS audio transcription | `None` |
| `GROQ_MODEL` | LLM model used for text structuring | `openai/gpt-oss-120b` |
| `ADMIN_TOKEN` | Bearer token for accessing `/dashboard` and `/sos-console` | `dev-admin` |
| `ROUTING_URL` | OSRM routing server URL | Public OSRM demo |
| `GEOCODE_URL` | Photon geocoding server URL | `https://photon.komoot.io` |

---

## Incident Extraction Pipeline

To ingest a new news report into the database:

```bash
python scripts/extract_incident.py article.txt --url https://example.com/news-report --insert
```

When `GROQ_API_KEY` is set, the extraction pipeline validates and formats the article text into a structured JSON schema via Groq. If no key is set or the request fails, it falls back to an offline gazetteer and keyword parser.

---

## Data Notice

The project database combines:
- **30 Verified Incidents** (`data/incidents.json`): Sourced directly from published Hyderabad news reports with archived URLs.
- **Sample Incidents** (`data/sample_incidents.json`): Synthetic reference records (`is_sample: true`) to illustrate amber and red risk thresholds during demonstration.

Whenever a synthetic record influences a rating, route segment, heatmap cell, or SMS reply, the UI displays an explicit **`SAMPLE DATA`** badge. To run exclusively against verified news records:

```bash
python scripts/seed.py --replace --no-sample
```

---

## Project Structure

```
├── app/
│   ├── config.py         # Application settings and threshold configurations
│   ├── db.py             # SQLite schemas, tables, and seeding logic
│   ├── main.py           # FastAPI application and route endpoints
│   ├── risk.py           # Pure scoring formulas and decay mathematics
│   ├── route.py          # OSRM route sampling and risk interpolation
│   ├── service.py        # Database queries and scoring aggregation
│   ├── sms.py            # TwiML parsing and 160-char formatting
│   └── sos.py            # Media ingestion and emergency alert handling
├── data/
│   ├── areas.json        # Covered neighborhood coordinates
│   ├── incidents.json    # Verified news incident records
│   └── sample_incidents.json # Synthetic demonstration records
├── scripts/
│   ├── extract_incident.py # Article parsing and LLM structuring
│   └── seed.py           # Database initialisation script
├── static/               # HTML, CSS, client JavaScript, Leaflet maps, and Service Worker
└── tests/                # Automated pytest test suites
```
