# Ride Radar
ons").

Ride Radar is a mobile web app for a woman who is about to take an auto or cab in **Hyderabad**. She taps once and gets a green, amber or red rating for where she is and the time of day, with a one-line reason and links to the news reports behind it. The same data feeds a public heatmap, an authority dashboard and an SMS path for phones with no data connection.

Green means "No reported incidents nearby". The app never says "safe".

## Run it

```bash
pip install -r requirements.txt
python scripts/seed.py            # creates ride_radar.db: real + sample incidents
uvicorn app.main:app --reload     # add --host 0.0.0.0 to open it from a phone on the same Wi-Fi
python -m pytest                  # 15 tests: risk engine + SMS parser
python scripts/demo_levels.py     # prints the level for 6 demo (area, hour) pairs
```

| Page | URL |
|---|---|
| One-tap check | http://localhost:8000/ |
| Heatmap | http://localhost:8000/heatmap |
| Authority dashboard | http://localhost:8000/dashboard |
| Simulated SMS phone | http://localhost:8000/sim-sms |
| Trip viewer | http://localhost:8000/trip/{token} (created by "Share my trip") |
| API docs | http://localhost:8000/docs |

Phones only allow geolocation on `https://` or `localhost`. To test GPS on a real phone, put the server behind an HTTPS tunnel (for example `cloudflared tunnel --url http://localhost:8000` or ngrok). Without HTTPS the app falls back to the area dropdown.

## How the risk score works

The app counts every reported incident within 1 km of you. Each incident gets a weight of `source × recency × hour match`. News counts 1.0 and a woman's report counts 0.6. The weight halves every 180 days. An incident within ±2 hours of now (wrapping around midnight) counts fully; at other hours it counts 0.4. The weights are added up: **under 2 is green, 2 to 5 is amber, over 5 is red**. If no seeded area is within 5 km, the app shows "Not covered yet" and gives no score. All of these numbers are in `app/config.py`.

Every covered result also shows a 24-cell strip: the same spot scored at each hour of the day. Tap a cell to check that hour. On amber or red, the result names the next hour (within 12 h) with a lower level, and the nearest seeded area within `BETTER_SPOT_KM` (5 km) that is lower at this hour, with a "Check there" button.

## Route check (`/route`)

Type an address in **From** and **To** (suggestions come from areas and from a Photon/OpenStreetMap address search limited to the city), use "My location" for GPS, or tap the map to drop a pin. Pick the hour you leave. The server gets the road route from OSRM, scores a point every 500 m with the same formula, and moves the hour forward with the trip time. The map draws each stretch in green, amber or red. The result lists the named hotspots in order, with the km mark and the hour you reach them, and the first start hour in the next 12 h that gives a lower level.

- `ROUTING_URL` in `app/config.py` defaults to the public OSRM demo server. That server receives the pickup and drop coordinates, so self-host OSRM for production. Set `ROUTING_URL=` (empty) to never call it.
- `GEOCODE_URL` defaults to the public Photon server (photon.komoot.io), which receives what the rider types. Set it empty to suggest seeded areas only. The server never logs the query.
- If OSRM is off or fails, the route is a straight line at 20 km/h and the page says so.
- Ride Radar stores neither point.

## Authority dashboard review

Click any area (or **Review**) to open its review panel: a map of every incident within 1 km, an hour-of-day chart with the busiest 3-hour window highlighted, what was reported by category, the last 90 days against the 90 before, the source mix, every incident with its source link, and **Directions in Google Maps**. **Mark addressed** sits in the panel and needs the action taken (patrols, lighting, CCTV, supervised stand, driver checks, awareness drive, other) plus an optional note. Both are stored and shown on the panel afterwards. A newer incident reopens the area.

## Swap the city

1. In `app/config.py`, set `CITY` and `CITY_CENTER`.
2. Replace `data/areas.json` with 10 to 25 neighbourhoods (`id`, `name`, `lat`, `lng`).
3. Replace `data/incidents.json` (real) and `data/sample_incidents.json` (placeholders, or delete it).
4. Update `ALIASES` in `scripts/extract_incident.py` with local place names.
5. Run `python scripts/seed.py --replace`, then `python scripts/demo_levels.py`, and edit `DEMO_PAIRS` there.

## Add or replace incidents

Every incident uses this schema:

```json
{
  "is_sample": false,
  "source_type": "news",
  "source_url": "https://real.article/url",
  "snippet": "One short sentence in your own words. No names, no vehicle numbers.",
  "area": "Gachibowli",
  "lat": 17.4401, "lng": 78.3489,
  "incident_hour": 22,
  "date": "2026-09-23",
  "category": "harassment"
}
```

- `area` must match a name in `data/areas.json`.
- `category` must be one of `harassment`, `stalking`, `fare_dispute_threat`, `assault`, `other`.
- Optional fields `hour_estimated`, `location_vague` and `publisher` are kept in the JSON for your own review. The app ignores them.

To add one article, use the extraction script:

```bash
python scripts/extract_incident.py article.txt --url https://... --insert    # adds it to the DB; reload /heatmap
```

The script uses **Groq** (free tier) when `GROQ_API_KEY` is set. Get a key at https://console.groq.com/keys and paste it into `.env` as `GROQ_API_KEY=gsk_...`. The `.env` file sits in the project root, is gitignored, and is read automatically. `.env.example` shows the format, and a real environment variable overrides `.env`. It calls Groq's OpenAI-compatible endpoint with Python's built-in `urllib`, so there is nothing extra to install. The default model is `openai/gpt-oss-120b` with a strict JSON schema, and the result is validated with pydantic. Set `GROQ_MODEL` to use another model. If no key is set, or the call fails, it uses a keyword and gazetteer matcher. Either way it keeps only one sentence, and that sentence is a paraphrase. `scripts/practice_article.txt` is a **fictional** text for rehearsing the demo.

To load a whole file: `python scripts/seed.py --replace --file my_incidents.json --no-sample`.

## Real incident data (Hyderabad)

The 30 real incidents were collected on 2026-10-11 by searching news sites and opening every source. Two were spot-checked again by hand. Please review them before the demo:

- **The dates span 2013 to 2026.** Only 15 are from 2023 or later. Older reports carry almost no weight because of the 180-day half-life.
- **Most times are estimates.** 22 of the 30 have `hour_estimated: true`. Where the article gave no clue, the hour is 21.
- **Locations are approximate.** 10 have `location_vague: true`. Three of those only said "Hyderabad", so they sit on Ameerpet as a central point.
- **Some cases are borderline.** You may want to drop these:
  - a man posing as a bike-taxi rider near Charminar;
  - a security guard (not the driver) at a cab pickup in Gachibowli;
  - co-passengers in a shared auto from Madhapur;
  - a Telugu news round-up with no incident date (it uses the publication date);
  - a fare threat against a 17-year-old.
- **New areas were added** for incidents far from the original 17 areas: Alwal, Neredmet, Chandrayangutta, Mailardevpally, Rajendranagar, Pahadi Shareef, Hayathnagar and Shamshabad Town.

## Decisions made without asking

- **City:** Hyderabad, changed from the PRD's Bengaluru example at your request.
- **`/heatmap` and `/dashboard`:** each URL serves the page to a browser and JSON to `fetch()`, chosen by the `Accept` header. Responses send `Vary: Accept` so caches keep the two apart.
- **`incidents.is_sample`:** a column added to the PRD schema so the badge can work.
- **Green label:** reads "No reported incidents nearby" only when the count is 0. A green result with a few old or off-hour incidents reads "Few reported incidents nearby", because the first label would be false.
- **"Weeks unresolved":** counts from the first incident in the last 365 days (`FLAG_WINDOW_DAYS`). Without that limit, a 2017 report shows as 400+ weeks. Marking an area addressed sets the count to 0. A newer incident opens the flag again.
- **Offline:** the service worker caches the app shell and the last `/check` response. When the phone is offline, the result shows "Showing the last result from HH:MM".
- **Language toggle:** English and Hindi. It covers the button, labels and advice text. The one-line reason from the server stays in English.
- **SMS replies:** never over 160 characters. Only the reason line is shortened, so the level, the advice and the `[SAMPLE DATA]` tag always remain.

## Honest limitations

- **News bias.** News covers serious cases in some areas. "No reported incidents" is not the same as no incidents, and every result says so.
- **The real data is thin.** 30 incidents over 13 years and a whole city gives green everywhere under the PRD formula. Amber and red in the demo come from sample data until more real reports, or women's reports (P2), are added.
- **Vague locations.** Many reports name only a neighbourhood. These are scored by area, not by the exact spot, and the UI says so.
- **SMS needs telecom registration.** In India, a real number needs a registered sender and DLT registration. The demo uses a simulated phone.
- **Authorities may not act.** The dashboard makes the patterns visible. The app works without it.
- **The Groq extraction path was not run with a real key in this build.** A test request reached Groq and was rejected only for the fake key, and the gazetteer fallback was tested. Run it once with your free key before the demo.

## SOS (hold to record)

Open `/sos`. First run: add up to 5 WhatsApp contacts, a **cancel PIN** and a different **duress PIN**. Both PINs are stored on the phone only, as a salted PBKDF2-SHA256 hash.

1. **Hold** the red button. Video (camera and microphone) and GPS stream to the server in 1-second chunks, so little is lost if the phone is taken.
2. **Let go.** The recording locks and a 10-second countdown starts.
   - **Cancel PIN:** false alarm. The video is deleted at once.
   - **Duress PIN:** the screen looks cancelled, but the alert sends silently and is marked "duress".
   - **No input, or Send now:** the alert sends.
3. **The server owns the deadline.** If the app is closed, the phone dies, or video stops arriving for 30 s, the server sends the alert anyway.
4. **On send:**
   - The video gets a SHA-256 hash, so anyone can check it was not changed.
   - Contacts get a WhatsApp message through the Meta Cloud API when it is configured. Otherwise the phone shows one-tap prefilled WhatsApp links.
   - The alert page `/alert/{id}` shows live location, the video and a summary.
   - With `GROQ_API_KEY` set, Groq Whisper transcribes the audio and writes a short AI brief with a severity.
5. **Authorities:** the authority console at `/sos-console` (behind `ADMIN_TOKEN`) lists sent alerts from the last 7 days.

What it cannot do, honestly:
- **No automatic 112 call.** Browsers cannot place calls on their own, and calling APIs block emergency numbers. The app shows one-tap **Call 112** buttons.
- **No direct feed to Telangana Police.** No public API exists for that. The console and alert links are the hand-off, and police have to adopt the console for it to reach them.
- **WhatsApp auto-send needs Meta setup:** WhatsApp Business verification plus an approved message template.
- **Video recording needs HTTPS on a real phone.**

## Wire a real Twilio number (optional)

1. Buy a Twilio number with SMS. For India, complete DLT sender registration first.
2. Make the server public over HTTPS (for example with a tunnel).
3. In Twilio, go to Phone Number, then Messaging, then "A message comes in". Set it to Webhook, `POST https://your-host/sms`.
4. Text `RADAR Gachibowli 9PM` to the number. `/sms` reads the form field `Body` and replies with TwiML.

## 90-second demo script

1. **(0:00) Problem.** "Women judge an auto by gut feeling. Incident data exists in the news, but nobody can use it in 10 seconds."
2. **(0:10) One tap.** Open `/` on a phone and tap **Check this ride**. If GPS is blocked, choose **Secunderabad Railway Station** at **22:00** to get **Red**. Point at the reason line and the two concrete options: "Lower after 01:00" and "Begumpet, 3.9 km away, is Green". Tap the 10:00 cell in the hour strip to show Amber, then **Share my trip**.
3. **(0:25) Trip share.** Tap Share. Open the link on a second phone: the location updates every 10 s, and the link ends after 3 hours.
4. **(0:35) Same place, other times.** Secunderabad at **10:00** gives Amber. **Begumpet** at **21:00** gives Green, "No reported incidents nearby". **Gachibowli** at **23:00** gives Amber: scroll down and click a real source link.
4b. **(0:45) Whole route.** Open `/route`, From **Gachibowli**, To **Secunderabad Railway Station**, 21:00. The road line turns amber at Gachibowli and HITEC City, then red at Secunderabad. The page says "Leaving at 01:00 instead lowers this route to Amber".
5. **(0:50) Honesty.** Point at the SAMPLE DATA badge and the footnote. "We never say safe."
6. **(0:55) No data connection.** On `/sim-sms`, send `RADAR Secunderabad 10PM` and show the 153-character reply.
7. **(1:05) Heatmap.** Open `/heatmap` and drag the hour slider from 06:00 to 22:00.
8. **(1:15) Authorities.** Open `/dashboard`. Areas are ranked, with weeks unresolved. Click **Gachibowli**: the map, the 21:00 to 00:00 peak and the source links show what to fix and when. Choose "Added patrols at peak hours", add a note, and click **Mark addressed**.
9. **(1:25) Live extraction.** Run `python scripts/extract_incident.py article.txt --url ... --insert` and reload the heatmap.

Backup: keep a screen recording of steps 2 to 6.

## Demo video

`demo/ride-radar-demo.mp4` (3 min 19 s, 1280x720, silent) walks through the app with captions and score charts. Re-record it after changes with:

```bash
python scripts/demo_video/record.py
```

It runs the app on a throwaway copy of `ride_radar.db` with the city clock fixed at 22:05, drives it with Playwright, and converts the result with ffmpeg. The real database is not touched. Route and address search scenes call OSRM and Photon, so they need internet.

## Project layout

```
app/        main.py (routes), risk.py (pure scoring), service.py (DB + scoring glue),
            db.py (schema, inserts), sms.py (parse + reply), config.py (all settings)
data/       areas.json, incidents.json (real), sample_incidents.json (placeholders)
scripts/    seed.py, extract_incident.py, demo_levels.py, practice_article.txt (fictional)
static/     index.html + app.js, heatmap.html, dashboard.html, trip.html, sim-sms.html,
            style.css, sw.js, manifest.json, icon.svg
tests/      test_risk.py, test_sms.py
```
