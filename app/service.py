"""Glue between the database and the pure risk engine. Used by the API, SMS, and scripts."""
from datetime import date, datetime

from app import clock, config, db, risk


def nearest_area(lat, lng, areas):
    """(area, distance_km) of the closest seeded area, or (None, inf) when there are none."""
    best, best_km = None, float("inf")
    for a in areas:
        d = risk.haversine_km(lat, lng, a["lat"], a["lng"])
        if d < best_km:
            best, best_km = a, d
    return best, best_km


def is_covered(lat, lng, areas):
    return nearest_area(lat, lng, areas)[1] <= config.COVERAGE_KM


def check_spot(conn, lat, lng, hour=None, now=None):
    """Score one spot. Reads only; never writes the location anywhere."""
    now = now or clock.now()
    hour = now.hour if hour is None else hour
    covered = is_covered(lat, lng, db.all_areas(conn))
    nearby = db.incidents_near(conn, lat, lng, config.RADIUS_KM) if covered else []
    result = risk.score(lat, lng, hour, nearby, now=now, covered=covered)
    result["hour"] = hour
    if covered:
        result["hours"] = risk.hour_profile(lat, lng, nearby, now=now)
        if result["level"] in ("amber", "red"):
            result["better_time"] = risk.better_hour(result["hours"], hour, result["level"])
            result["better_spot"] = better_spot(conn, lat, lng, hour, result["level"], now)
    result["helplines"] = config.HELPLINES if result["level"] in ("amber", "red") else []
    return result


def better_spot(conn, lat, lng, hour, level, now, max_km=None):
    """Nearest seeded area with a lower level at this hour, within BETTER_SPOT_KM."""
    max_km = config.BETTER_SPOT_KM if max_km is None else max_km
    incidents = db.all_incidents(conn)
    best = None
    for a in db.all_areas(conn):
        d = risk.haversine_km(lat, lng, a["lat"], a["lng"])
        if d < 0.3 or d > max_km or (best and d >= best["km"]):
            continue
        r = risk.score(a["lat"], a["lng"], hour, incidents, now=now)
        if risk.LEVEL_RANK[r["level"]] < risk.LEVEL_RANK[level]:
            best = {"area": a["name"], "km": round(d, 1), "level": r["level"],
                    "count": r["count"], "lat": a["lat"], "lng": a["lng"]}
    return best


def dashboard_rows(conn, today=None):
    """Areas ranked by weighted incident count (recency x source, any hour)."""
    today = today or clock.now().date()
    now = datetime.combine(today, datetime.min.time())
    areas = {a["id"]: a for a in db.all_areas(conn)}
    flags = {r["area_id"]: dict(r) for r in conn.execute("SELECT * FROM authority_flags")}
    rows = {}
    for inc in db.all_incidents(conn):
        r = rows.setdefault(inc["area_id"], {"weighted": 0.0, "count": 0, "last": inc["date"], "sample": False})
        r["count"] += 1
        # hour=incident hour so the hour factor is 1.0: ranking ignores time of day
        r["weighted"] += risk.incident_weight(inc, now, inc["incident_hour"])
        r["last"] = max(r["last"], inc["date"])
        r["sample"] = r["sample"] or bool(inc["is_sample"])
    out = []
    for area_id, r in rows.items():
        flag = flags.get(area_id)
        if flag and flag["resolved_at"] is None:
            weeks = max(0, (today - date.fromisoformat(flag["first_flagged_date"])).days // 7)
        else:
            weeks = 0
        out.append({
            "area_id": area_id,
            "area": areas[area_id]["name"],
            "incidents": r["count"],
            "weighted": round(r["weighted"], 2),
            "last_incident": r["last"],
            "weeks_unresolved": weeks,
            "resolved_at": flag["resolved_at"] if flag else None,
            "flagged": flag is not None,
            "sample": r["sample"],
        })
    out.sort(key=lambda x: (x["flagged"], x["weighted"]), reverse=True)
    return out


def area_detail(conn, area_id, today=None):
    """Everything an officer needs before marking an area addressed. None if unknown."""
    area = conn.execute("SELECT * FROM areas WHERE id = ?", (area_id,)).fetchone()
    if area is None:
        return None
    area = dict(area)
    today = today or clock.now().date()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM incidents WHERE area_id = ? ORDER BY date DESC, id DESC", (area_id,))]
    by_hour = [0] * 24
    by_category = {}
    recent = previous = 0
    for r in rows:
        by_hour[r["incident_hour"]] += 1
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1
        age = (today - date.fromisoformat(r["date"])).days
        if age <= 90:
            recent += 1
        elif age <= 180:
            previous += 1
    # Busiest 3-hour window, wrapping past midnight.
    peak = None
    if rows:
        start = max(range(24), key=lambda h: sum(by_hour[(h + k) % 24] for k in range(3)))
        peak = {"start": start, "end": (start + 3) % 24,
                "count": sum(by_hour[(start + k) % 24] for k in range(3))}
    flag = conn.execute("SELECT * FROM authority_flags WHERE area_id = ?", (area_id,)).fetchone()
    flag = dict(flag) if flag else None
    if flag:
        flag["resolution_label"] = config.RESOLUTION_ACTIONS.get(flag.get("resolution_action") or "")
    return {
        "area_id": area_id, "area": area["name"], "lat": area["lat"], "lng": area["lng"],
        "radius_km": config.RADIUS_KM,
        "count": len(rows),
        "by_hour": by_hour,
        "by_category": sorted(by_category.items(), key=lambda kv: kv[1], reverse=True),
        "peak": peak,
        "last_90_days": recent, "previous_90_days": previous,
        "news": sum(1 for r in rows if r["source_type"] == "news" and not r["is_sample"]),
        "reports": sum(1 for r in rows if r["source_type"] == "report"),
        "samples": sum(1 for r in rows if r["is_sample"]),
        "flag": flag,
        "incidents": [{
            "date": r["date"], "hour": r["incident_hour"], "category": r["category"],
            "snippet": r["snippet"], "source_type": r["source_type"], "source_url": r["source_url"],
            "is_sample": bool(r["is_sample"]), "lat": r["lat"], "lng": r["lng"],
        } for r in rows],
        "directions": {
            "google": f"https://www.google.com/maps/dir/?api=1&destination={area['lat']},{area['lng']}",
            "osm": f"https://www.openstreetmap.org/?mlat={area['lat']}&mlon={area['lng']}#map=16/{area['lat']}/{area['lng']}",
        },
        "actions": config.RESOLUTION_ACTIONS,
    }
