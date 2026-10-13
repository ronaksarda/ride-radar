"""Risk scoring. Pure functions only: no database, no clock unless passed in."""
import math
from datetime import date, datetime

from app import config


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def hour_matches(h1, h2, window=config.HOUR_WINDOW):
    diff = abs(int(h1) - int(h2)) % 24
    return min(diff, 24 - diff) <= window


def incident_weight(incident, now, hour):
    source = config.SOURCE_WEIGHTS.get(incident["source_type"], config.SOURCE_WEIGHTS["report"])
    age_days = max(0, (now.date() - date.fromisoformat(incident["date"])).days)
    recency = 0.5 ** (age_days / config.HALF_LIFE_DAYS)
    hour_factor = 1.0 if hour_matches(incident["incident_hour"], hour) else config.OFF_HOUR_FACTOR
    return source * recency * hour_factor


def level_for(total):
    if total > config.RED_MIN:
        return "red"
    if total >= config.AMBER_MIN:
        return "amber"
    return "green"


def _reason(count, on_hour):
    if count == 0:
        return "No reported incidents nearby."
    noun = "incident" if count == 1 else "incidents"
    radius = f"{config.RADIUS_KM:g} km"
    if on_hour == 0:
        return f"{count} reported {noun} within {radius}, none around this hour."
    if count == 1:
        return f"1 reported incident within {radius}, around this hour."
    return f"{count} reported {noun} within {radius}, {on_hour} of them around this hour."


def score(lat, lng, hour, incidents, now=None, covered=True):
    """Return {level, total, count, reason, sources, sample} for a spot and hour.

    `covered` is False when the spot is too far from every seeded area; then no
    score is computed, so the app never shows a made-up rating.
    """
    if not covered:
        return {
            "level": "not_covered",
            "total": None,
            "count": 0,
            "reason": f"Not covered yet. Ride Radar only has data for {config.CITY}.",
            "sources": [],
            "sample": False,
        }
    now = now or datetime.now()
    nearby = []
    for inc in incidents:
        if haversine_km(lat, lng, inc["lat"], inc["lng"]) <= config.RADIUS_KM:
            nearby.append((inc, incident_weight(inc, now, hour)))
    total = round(sum(w for _, w in nearby), 2)
    on_hour = sum(1 for inc, _ in nearby if hour_matches(inc["incident_hour"], hour))
    nearby.sort(key=lambda pair: pair[1], reverse=True)
    sources = [
        {
            "area": inc.get("area_name"),
            "category": inc["category"],
            "date": inc["date"],
            "hour": inc["incident_hour"],
            "snippet": inc["snippet"],
            "source_url": inc["source_url"],
            "is_sample": bool(inc.get("is_sample")),
        }
        for inc, _ in nearby
    ]
    return {
        "level": level_for(total),
        "total": total,
        "count": len(nearby),
        "reason": _reason(len(nearby), on_hour),
        "sources": sources,
        "sample": any(s["is_sample"] for s in sources),
    }


def hour_profile(lat, lng, incidents, now=None):
    """Level and total for each hour 0-23 at one spot, from the same nearby incidents."""
    now = now or datetime.now()
    nearby = [inc for inc in incidents
              if haversine_km(lat, lng, inc["lat"], inc["lng"]) <= config.RADIUS_KM]
    out = []
    for h in range(24):
        total = round(sum(incident_weight(inc, now, h) for inc in nearby), 2)
        out.append({"hour": h, "level": level_for(total), "total": total})
    return out


LEVEL_RANK = {"green": 0, "amber": 1, "red": 2}


def better_hour(profile, hour, level, horizon=12):
    """First hour in the next `horizon` hours with a lower level than now, or None."""
    for step in range(1, horizon + 1):
        cand = profile[(hour + step) % 24]
        if LEVEL_RANK[cand["level"]] < LEVEL_RANK[level]:
            return {"hour": cand["hour"], "level": cand["level"], "in_hours": step}
    return None
