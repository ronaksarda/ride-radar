# Ride Radar: PRD + Claude Code Implementation Prompt

Hackathon project, 12-hour build. Part 1 is the PRD. Part 2 is the prompt to paste into Claude Code (put this whole file in the repo root as `PRD.md` and tell Claude Code to read it).

---

# PART 1: PRD

## 1. Overview
**Ride Radar** is a mobile web app. With one tap, a woman about to take an auto or cab gets a green, amber, or red risk rating for her current spot and time of day. The rating is built from geotagged news-reported incidents and, if time allows, other women's reports. The same data feeds a public heatmap and an authority dashboard.

## 2. Problem
Women face harassment inside autos and cabs, and there is no quick way to judge risk before boarding. Existing safety apps depend on user reports, so they are empty at launch. Incident data exists in news coverage, but it is scattered and never turned into something usable in 10 seconds.

## 3. Goals and non-goals
**Goals**
- Risk answer in under 10 seconds, with a one-line reason.
- Works with zero users on day one, using news data.
- Works on any smartphone and bad networks, including an SMS path.
- Makes patterns visible to the public and to authorities.

**Non-goals (v1)**
- Real-time in-ride monitoring.
- Vehicle or driver verification (roadmap).
- Naming people or specific vehicles, ever.
- Claiming authorities will act.

## 4. Users
- **Primary:** women who commute daily by auto or cab, mostly students.
- **Secondary:** parents and friends who receive trip shares.
- **Tertiary:** police and transport officials using the dashboard.

## 5. User stories
1. As a rider, I tap once and see how risky my area and time are, so I can decide whether to board.
2. As a rider with no data signal, I send an SMS and get the rating back.
3. As a rider on a red result, I share my trip with trusted contacts in one tap.
4. As a citizen, I open a public heatmap to see hotspots by area and hour.
5. As an official, I see areas ranked by incident count and how long they have gone unaddressed.

## 6. Functional requirements

**P0 (must ship)**
- One-tap check using browser geolocation and the current hour.
- Risk engine returning green/amber/red, a one-line reason, and incident count.
- Seeded database of geotagged incidents for ONE city, each with a source URL and a short snippet (never full copied articles).
- Public heatmap with an hour-of-day filter.
- Authority dashboard: ranked table of areas with incident counts and a "weeks unresolved" counter.

**P1 (should ship)**
- Amber/red recommendations (wait for a busier stop, or change the time).
- Trip share: link with a live-location page for trusted contacts.
- SMS flow: text an area name, get the rating back (simulated for the demo).
- Live demo of extracting one fresh news article into a structured incident.
- Service worker caching the app shell and the last result.

**P2 (cut first)**
- Women's reports (`POST /report`).

## 7. Risk score logic
For each incident within 1 km of the user:

```
weight = source_weight * recency_decay * hour_match
```

- `source_weight`: news = 1.0, woman's report = 0.6.
- `recency_decay`: `0.5 ** (age_in_days / 180)` (halves about every 6 months).
- `hour_match`: 1.0 if the incident hour is within +/-2 hours of the current hour (wrap around midnight), otherwise 0.4.

Sum the weights: **< 2 green, 2 to 5 amber, > 5 red.** Thresholds go in one config file so they can be tuned until the seeded data produces all three colours at different demo spots and times.

**Wording rule:** green means "No reported incidents nearby." The app NEVER says "safe."

## 8. Data model (SQLite)
- `areas`: id, name, lat, lng
- `incidents`: id, source_type (`news` | `report`), source_url, snippet, area_id, lat, lng, incident_hour (0-23), date, category
- `trip_shares`: token, created_at, expires_at, last_lat, last_lng, last_updated (latest point only, deleted at expiry)
- `authority_flags`: area_id, first_flagged_date, resolved_at (nullable)

## 9. API
- `POST /check` body: lat, lng, hour (optional, defaults to now). Returns level, reason, count, nearby sources. Stores nothing.
- `GET /areas` list of areas (for the dropdown fallback).
- `GET /heatmap?hour=` points for the map.
- `GET /dashboard` ranked areas with count, last incident date, weeks unresolved.
- `POST /dashboard/resolve/{area_id}` marks an area addressed (no auth, demo only).
- `POST /share` creates a token. `POST /trip/{token}/update` updates location. `GET /trip/{token}` serves the viewer page. `GET /trip/{token}/data` returns the latest point.
- `POST /sms` webhook (Twilio form-encoded `Body`), returns TwiML. `GET /sim-sms` is a simulated phone screen for the demo.
- `POST /report` (P2).

## 10. Non-functional requirements
- `/check` responds in under 2 seconds on a slow connection.
- Each page under about 200 KB, no frameworks.
- No location history stored.
- Every incident shows its source link.
- English first. Hindi (or another regional language) UI labels as a stretch goal.

## 11. Edge cases
- Quiet area: reads "no reported incidents", because news only covers serious cases.
- Vague news locations: score by area, not exact point, and say so in the UI.
- Defamation: show only area, time, and category. Never names or vehicle numbers.
- GPS denied: area dropdown fallback.
- Outside the seeded city (no area within 5 km of any seeded area): show "not covered yet", no fake score.
- SMS: real rollout needs telecom registration. State that plainly.
- Authorities may ignore the dashboard: the app works without them.

## 12. Success criteria
- A tap returns a rating in under 10 seconds.
- All three colours appear in the demo at different spots and times.
- SMS flow works live, with a recorded backup.
- Judges can click through to the source of any incident.

## 13. Timeline (12 hours)
- Hr 0-2: backend and database seeding.
- Hr 2-5: news data collection and extraction.
- Hr 5-7: risk engine and one-tap screen.
- Hr 7-9: heatmap and dashboard.
- Hr 9-10: SMS flow and trip share.
- Hr 10-12: rehearsal, README, pitch. Freeze code for the last 30 minutes.

## 14. Risks
- News pipeline eats time: pre-collect articles, demo only one live extraction.
- Score looks arbitrary: keep the formula explainable in one sentence.
- SMS fails live: keep a screen recording ready.
- Thin data: one city with 40-60 incidents is enough if demo spots are chosen well.

---

# PART 2: IMPLEMENTATION PROMPT FOR CLAUDE CODE

> Paste everything below this line into Claude Code.

You are building **Ride Radar**, a hackathon project that must be demo-ready in about 12 hours. Read `PRD.md` (Part 1 of this file) first and treat it as the spec. Build a working end-to-end product, not a scaffold.

## Hard constraints
- **Backend:** Python 3.11+, FastAPI, SQLite via the standard `sqlite3` module (or SQLAlchemy only if it saves time). No Docker needed.
- **Frontend:** plain HTML, CSS, and vanilla JavaScript served as static files by FastAPI. **No TypeScript, no React, no build step, no npm.**
- **Map:** Leaflet and the leaflet.heat plugin loaded from a CDN (cdnjs or unpkg).
- Mobile-first. Large tap targets. Each page under about 200 KB. Must work on low-end phones.
- Never display the word "safe" as a result label. Green means "No reported incidents nearby."
- Never store location history. `/check` must not write location to the database.
- Never store or display names of people or vehicle numbers.
- Keep dependencies minimal: `fastapi`, `uvicorn`, `python-multipart`, and optionally `anthropic` for the extraction script only.

## Project structure
```
ride-radar/
  PRD.md
  README.md
  requirements.txt
  app/
    main.py            # FastAPI app, routes, static mounting
    db.py              # sqlite connection, schema creation, seed loader
    risk.py            # scoring logic (pure functions, easy to test)
    config.py          # thresholds, weights, radius, city center, coverage radius
    sms.py             # SMS parsing + reply text
  data/
    areas.json         # areas for the chosen city
    incidents.json     # seed incidents (see data rules below)
  scripts/
    extract_incident.py  # takes article text, outputs structured incident JSON
    seed.py              # loads areas.json and incidents.json into SQLite
  static/
    index.html         # one-tap check screen
    heatmap.html
    dashboard.html
    trip.html          # trip viewer page
    sim-sms.html       # simulated phone for the SMS demo
    app.js, style.css
    sw.js, manifest.json   # P1: offline shell caching
  tests/
    test_risk.py
```

## Data rules (important)
- Put the city in `config.py` as a single setting, plus a center lat/lng, so it can be swapped.
- Create `data/areas.json` with 10 to 15 real neighbourhoods or landmarks of that city with approximate coordinates.
- **Do not invent real news.** Create `data/incidents.json` with 40 to 60 entries that are clearly marked `"is_sample": true` and have `"source_url": "TODO"`. Use realistic structure (area, lat/lng near the area, hour, date within the last 12 months, category, short generic snippet). Add a loud note at the top of the README and a `SAMPLE DATA` badge in the UI whenever a sample incident is used.
- I will replace the sample entries with real, sourced incidents before the demo. Make that easy: the seed script should accept the same JSON schema and a `--replace` flag. If `is_sample` is false and `source_url` is a real URL, show a clickable source link in the UI.
- Distribute sample incidents so that **different areas and hours produce green, amber, and red**. Include a small script or test that prints the level for 6 demo (area, hour) pairs so thresholds can be tuned.
- Allowed categories: `harassment`, `stalking`, `fare_dispute_threat`, `assault`, `other`. Snippets are one short sentence, never copied article text.

## Build order (do each step fully, run it, then move on)

### Step 1: Backend core
1. `config.py` with: `RADIUS_KM = 1.0`, `COVERAGE_KM = 5.0`, source weights (news 1.0, report 0.6), `HALF_LIFE_DAYS = 180`, `HOUR_WINDOW = 2`, `OFF_HOUR_FACTOR = 0.4`, `AMBER_MIN = 2`, `RED_MIN = 5`.
2. `db.py` creating the four tables from the PRD data model, and `seed.py` loading the JSON.
3. `risk.py` with pure functions: `haversine_km`, `hour_matches(h1, h2)` with midnight wraparound, `incident_weight(incident, now, hour)`, `score(lat, lng, hour, incidents)` returning `{level, total, count, reason, sources}`. The `reason` is one line, for example "3 reported incidents within 1 km, 2 of them around this hour."
4. `tests/test_risk.py` covering: midnight wraparound, decay, boundary thresholds, empty area, outside coverage.

### Step 2: API
Implement `POST /check`, `GET /areas`, `GET /heatmap`, `GET /dashboard`, `POST /dashboard/resolve/{area_id}`. `/check` returns a `not_covered` level if no area is within `COVERAGE_KM`. Validate inputs. Return clear JSON errors.

### Step 3: One-tap screen (`index.html`)
- A single huge "Check this ride" button.
- On tap: request geolocation, call `/check`, show a full-screen result in green/amber/red with the one-line reason, the incident count, and links to sources.
- If geolocation is denied or fails: show an area dropdown from `/areas` and check by that area's coordinates.
- Amber shows: "Consider waiting for a busier stop or a different time."
- Red shows the amber text plus a "Share my trip" button.
- Show a "Not covered yet" state outside the city.
- Show the `SAMPLE DATA` badge when applicable.

### Step 4: Heatmap and dashboard
- `heatmap.html`: Leaflet map centered on the city, heat layer, and an hour-of-day slider (0-23) that re-queries `/heatmap?hour=`. Clicking a point shows area, category, and a source link.
- `dashboard.html`: ranked table of areas by weighted incident count with columns: area, incidents, last incident date, **weeks unresolved**, and a "Mark addressed" button. Weeks unresolved = weeks since `first_flagged_date`, reset when resolved. Style it like an official dashboard.

### Step 5: Trip share
- `POST /share` returns a token and a shareable URL (expires after 3 hours).
- The rider's page posts the browser location to `/trip/{token}/update` every 15 seconds while open.
- `trip.html` polls `/trip/{token}/data` every 10 seconds and shows the latest position on a Leaflet map plus "last updated N seconds ago". Store only the latest point. Delete expired shares on access.

### Step 6: SMS flow
- `sms.py` parses a message like `RADAR Koramangala` or `RADAR Koramangala 9PM` (case-insensitive, fuzzy match against area names, default hour = now) and returns a short reply (under 160 characters): level, count, and one-line reason.
- `POST /sms` accepts Twilio form data (`Body`) and returns TwiML XML.
- `sim-sms.html` is a fake phone UI where I type the text and see the reply bubble, calling `/sms` under the hood. This is the demo path. Document in the README how to wire a real Twilio number later.

### Step 7: Extraction script (live demo piece)
- `scripts/extract_incident.py` reads article text from stdin or a file and prints one JSON incident in the `incidents.json` schema (area, approximate lat/lng looked up from `areas.json`, hour if mentioned, date, category, one-sentence snippet, source_url from a CLI flag).
- Use the Anthropic API if `ANTHROPIC_API_KEY` is set (ask for strict JSON only, then validate it). If not set, fall back to a simple keyword and gazetteer matcher against `areas.json`. The script must never copy more than one sentence of the article.
- Add an `--insert` flag that adds the result to the database so the heatmap updates live.

### Step 8: Polish (P1)
- `manifest.json` and `sw.js` caching the static shell and the last `/check` result so the app opens offline.
- A simple language toggle (English and Hindi) for the main button, result labels, and amber/red messages. Keep strings in one object in `app.js`.
- A footer note on every result: "Based on reported incidents only. No reports does not guarantee safety."

### Step 9: README
Include: what it is, how to run (`pip install -r requirements.txt`, `python scripts/seed.py`, `uvicorn app.main:app --reload`), how to swap the city, how to replace sample data with real sourced incidents, how the risk score works in one paragraph, honest limitations (news bias, vague locations, SMS needs telecom registration in production, authorities may not act), and a 90-second demo script.

## Acceptance checklist (verify before saying you're done)
- [ ] `uvicorn` starts with no errors and `tests/test_risk.py` passes.
- [ ] Three demo (area, hour) pairs return green, amber, and red respectively.
- [ ] The one-tap flow works on a phone-sized viewport, including the GPS-denied dropdown.
- [ ] Heatmap hour slider changes the visible points.
- [ ] Dashboard ranks areas and "Mark addressed" resets weeks unresolved.
- [ ] Trip share link opens on a second device and updates the location.
- [ ] SMS simulator returns a reply under 160 characters.
- [ ] The extraction script produces valid JSON and `--insert` updates the heatmap.
- [ ] No page ever shows the word "safe" as a result, and no location is stored by `/check`.
- [ ] `SAMPLE DATA` badge appears whenever sample incidents are involved.

## How to work
- Work step by step. After each step, run the code, fix errors, and give me a 2-line status before moving on.
- If a decision is ambiguous, choose the simplest option that works and note it in the README. Do not ask me questions unless something blocks the build.
- Do not add features that are not in the PRD. If time is short, cut P2 first, then the language toggle, then the service worker.
- At the end, list exactly what I must do manually: choose the city, replace sample incidents with real sourced ones, tune thresholds, and set up Twilio (optional).
