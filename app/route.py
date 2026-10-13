"""Route check: score every stretch of a ride from pickup to drop.

The road route comes from an OSRM server (config.ROUTING_URL). If that is off or
fails, the route is a straight line at config.FALLBACK_SPEED_KMH, and the result
says so. Nothing here writes to the database.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime

from app import clock, config, db, risk, service

log = logging.getLogger("ride_radar")


def road_route(a, b, timeout=4):
    """[(lat, lng), ...], distance_km, minutes from OSRM, or None when unavailable."""
    if not config.ROUTING_URL:
        return None
    url = (f"{config.ROUTING_URL.rstrip('/')}/route/v1/driving/"
           f"{a[1]:.5f},{a[0]:.5f};{b[1]:.5f},{b[0]:.5f}?overview=full&geometries=geojson")
    req = urllib.request.Request(url, headers={"User-Agent": "ride-radar/1.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        r = data["routes"][0]
        coords = [(lat, lng) for lng, lat in r["geometry"]["coordinates"]]
        return coords, r["distance"] / 1000, r["duration"] / 60
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
        log.warning("routing unavailable: %s", e)
        return None


def straight_route(a, b):
    km = risk.haversine_km(a[0], a[1], b[0], b[1])
    n = max(1, int(km / 0.25))  # dense enough that each stretch can take its own colour
    coords = [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]
    return coords, km, km / config.FALLBACK_SPEED_KMH * 60


def sample(coords, step_km):
    """Points every `step_km` along a polyline, each as (lat, lng, km_from_start)."""
    out = [(coords[0][0], coords[0][1], 0.0)]
    done, next_at = 0.0, step_km
    for (la1, ln1), (la2, ln2) in zip(coords, coords[1:]):
        seg = risk.haversine_km(la1, ln1, la2, ln2)
        while seg > 0 and next_at <= done + seg:
            f = (next_at - done) / seg
            out.append((la1 + (la2 - la1) * f, ln1 + (ln2 - ln1) * f, next_at))
            next_at += step_km
        done += seg
    if done - out[-1][2] > 0.05:
        out.append((coords[-1][0], coords[-1][1], done))
    return out, done


def _score_points(points, total_km, minutes, start_hour, incidents, now):
    scored = []
    for lat, lng, km in points:
        elapsed = minutes * (km / total_km) if total_km else 0
        hour = int(start_hour + elapsed // 60) % 24
        r = risk.score(lat, lng, hour, incidents, now=now)
        scored.append({"lat": lat, "lng": lng, "km": km, "hour": hour, "level": r["level"],
                       "count": r["count"], "sample": r["sample"]})
    return scored


def _worst(scored):
    return max((p["level"] for p in scored), key=risk.LEVEL_RANK.get, default="green")


def check_route(conn, start, end, hour=None, now=None):
    now = now or clock.now()
    hour = now.hour if hour is None else hour
    areas = db.all_areas(conn)
    if not (service.is_covered(*start, areas) and service.is_covered(*end, areas)):
        return {"level": "not_covered",
                "reason": f"Not covered yet. Ride Radar only has data for {config.CITY}."}

    got = road_route(start, end)
    routing = "road" if got else "straight"
    coords, _, minutes = got or straight_route(start, end)
    points, total_km = sample(coords, config.ROUTE_STEP_KM)
    incidents = db.all_incidents(conn)
    scored = _score_points(points, total_km, minutes, hour, incidents, now)
    level = _worst(scored)

    # Colour the drawn line: each stretch takes the level of its nearest sample point.
    segments, cum, i = [], 0.0, 0
    for (la1, ln1), (la2, ln2) in zip(coords, coords[1:]):
        mid = cum + risk.haversine_km(la1, ln1, la2, ln2) / 2
        while i + 1 < len(scored) and abs(scored[i + 1]["km"] - mid) < abs(scored[i]["km"] - mid):
            i += 1
        lvl = scored[i]["level"]
        if segments and segments[-1]["level"] == lvl:
            segments[-1]["coords"].append([la2, ln2])
        else:
            segments.append({"level": lvl, "coords": [[la1, ln1], [la2, ln2]]})
        cum += risk.haversine_km(la1, ln1, la2, ln2)

    # Hotspots: amber/red stretches, named by their nearest seeded area.
    hotspots = {}
    for p in scored:
        if p["level"] == "green":
            continue
        area, _ = service.nearest_area(p["lat"], p["lng"], areas)
        h = hotspots.get(area["name"])
        if not h or risk.LEVEL_RANK[p["level"]] > risk.LEVEL_RANK[h["level"]]:
            hotspots[area["name"]] = {"area": area["name"], "level": p["level"], "km": round(p["km"], 1),
                                     "hour": p["hour"], "count": p["count"]}
    hotspots = sorted(hotspots.values(), key=lambda h: h["km"])

    better = None
    if level != "green":
        for step in range(1, 13):
            h = (hour + step) % 24
            alt = _worst(_score_points(points, total_km, minutes, h, incidents, now))
            if risk.LEVEL_RANK[alt] < risk.LEVEL_RANK[level]:
                better = {"hour": h, "level": alt, "in_hours": step}
                break

    flagged = sum(1 for p in scored if p["level"] != "green")
    if level == "green":
        reason = "No stretch of this route has many reported incidents at this time."
    else:
        names = ", ".join(h["area"] for h in hotspots[:3])
        reason = f"{len(hotspots)} stretch{'es' if len(hotspots) != 1 else ''} with reported incidents: {names}."
    return {
        "level": level,
        "reason": reason,
        "hour": hour,
        "distance_km": round(total_km, 1),
        "minutes": round(minutes),
        "routing": routing,
        "segments": segments,
        "hotspots": hotspots,
        "flagged_share": round(flagged / len(scored), 2),
        "better_time": better,
        "sample": any(p["sample"] for p in scored),
        "city": config.CITY,
    }
