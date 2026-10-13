"""Address search for the route page, through a Photon geocoder (config.GEOCODE_URL).

Photon is built for type-ahead search on OpenStreetMap data. Results are limited
to a box around the seeded areas, so every suggestion can be scored.
"""
import json
import re
import logging
import urllib.error
import urllib.parse
import urllib.request

from app import config

log = logging.getLogger("ride_radar")


def bbox(areas, pad=0.05):
    lats = [a["lat"] for a in areas]
    lngs = [a["lng"] for a in areas]
    return min(lngs) - pad, min(lats) - pad, max(lngs) + pad, max(lats) + pad


def _label(p):
    name = p.get("name") or p.get("street") or ""
    if p.get("housenumber") and p.get("street"):
        name = f"{p['street']} {p['housenumber']}"
    parts = [name] + [p.get(k) for k in ("locality", "district", "city") if p.get(k) and p.get(k) != name]
    return ", ".join(x for x in parts if x)[:120]


_cache = {}  # successful lookups only, so a timeout is retried next time


def normalize(q):
    """Lower-case, drop punctuation and the city name: "Begum Bazar , Hyderabad" -> "begum bazar"."""
    q = re.sub(r"[^\w\s-]", " ", q.lower())
    city = config.CITY.lower()
    words = [w for w in q.split() if w not in (city, "india", "telangana")]
    return " ".join(words) or q.strip()


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": config.GEOCODE_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _photon(q, box, timeout):
    qs = urllib.parse.urlencode({
        "q": q, "limit": 6, "lang": "en",
        "lat": config.CITY_CENTER[0], "lon": config.CITY_CENTER[1],
        "bbox": ",".join(f"{v:.4f}" for v in box),
    })
    data = _get(f"{config.GEOCODE_URL.rstrip('/')}/api/?{qs}", timeout)
    out = []
    for f in data.get("features", []):
        lng, lat = f["geometry"]["coordinates"]
        out.append({"label": _label(f.get("properties", {})), "lat": round(lat, 5), "lng": round(lng, 5)})
    return out


def _nominatim(q, box, timeout):
    """One-off search for a typed address nobody picked. Not used for type-ahead (policy)."""
    qs = urllib.parse.urlencode({
        "q": f"{q}, {config.CITY}", "format": "jsonv2", "limit": 3, "countrycodes": "in",
        "viewbox": ",".join(f"{v:.4f}" for v in box), "bounded": 1,
    })
    data = _get(f"{config.NOMINATIM_URL.rstrip('/')}/search?{qs}", timeout)
    return [{"label": d.get("display_name", "")[:120], "lat": round(float(d["lat"]), 5),
             "lng": round(float(d["lon"]), 5)} for d in data]


def search(q, box, final=False):
    """[{label, lat, lng}] for a query, or [] when nothing is found or the services are down.

    `final` is the submit-time lookup: it may also ask Nominatim once.
    """
    q = normalize(q)
    key = (q, box, final)
    if key in _cache:
        return _cache[key]
    out, ok = [], False
    if config.GEOCODE_URL:
        for timeout in (5, 8):  # one retry: the public server is sometimes slow
            try:
                out, ok = _photon(q, box, timeout), True
                break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
                log.warning("photon unavailable: %s", e)
    if final and not out and config.NOMINATIM_URL:
        try:
            out, ok = _nominatim(q, box, 8), True
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            log.warning("nominatim unavailable: %s", e)
    seen, uniq = set(), []
    for r in out:
        if r["label"] and r["label"] not in seen:
            seen.add(r["label"])
            uniq.append(r)
    if ok:
        if len(_cache) > 1000:
            _cache.clear()
        _cache[key] = uniq
    return uniq
