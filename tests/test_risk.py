from datetime import datetime, timedelta

from app import risk

NOW = datetime(2026, 10, 11, 20, 0)
SPOT = (17.4401, 78.3489)  # Gachibowli


def incident(days_ago=0, hour=20, lat=SPOT[0], lng=SPOT[1], source_type="news", **extra):
    return {
        "id": extra.get("id", 1),
        "source_type": source_type,
        "source_url": "TODO",
        "snippet": "Sample incident.",
        "area_name": "Gachibowli",
        "lat": lat,
        "lng": lng,
        "incident_hour": hour,
        "date": (NOW - timedelta(days=days_ago)).date().isoformat(),
        "category": "harassment",
        "is_sample": True,
    }


def test_hour_window_wraps_around_midnight():
    assert risk.hour_matches(23, 1)
    assert risk.hour_matches(1, 23)
    assert risk.hour_matches(0, 22)
    assert not risk.hour_matches(23, 2)
    assert not risk.hour_matches(12, 9)


def test_incident_weight_halves_after_half_life():
    fresh = risk.incident_weight(incident(days_ago=0), NOW, 20)
    old = risk.incident_weight(incident(days_ago=180), NOW, 20)
    assert fresh == 1.0
    assert abs(old - 0.5) < 1e-9


def test_off_hour_and_report_weights():
    assert abs(risk.incident_weight(incident(hour=8), NOW, 20) - 0.4) < 1e-9
    assert abs(risk.incident_weight(incident(source_type="report"), NOW, 20) - 0.6) < 1e-9


def test_haversine_known_distance():
    # Ameerpet to Secunderabad station is roughly 5.7 km
    d = risk.haversine_km(17.4375, 78.4482, 17.4337, 78.5016)
    assert 5.2 < d < 6.2


def test_level_thresholds_at_boundaries():
    assert risk.level_for(0) == "green"
    assert risk.level_for(1.99) == "green"
    assert risk.level_for(2.0) == "amber"
    assert risk.level_for(5.0) == "amber"
    assert risk.level_for(5.01) == "red"


def test_empty_area_is_green_and_never_says_safe():
    result = risk.score(*SPOT, 20, [], now=NOW, covered=True)
    assert result["level"] == "green"
    assert result["count"] == 0
    assert result["reason"] == "No reported incidents nearby."
    assert "safe" not in result["reason"].lower()


def test_outside_coverage_returns_not_covered_without_score():
    result = risk.score(*SPOT, 20, [incident()], now=NOW, covered=False)
    assert result["level"] == "not_covered"
    assert result["total"] is None


def test_far_incidents_are_ignored():
    far = incident(lat=SPOT[0] + 0.05)  # ~5.5 km north
    result = risk.score(*SPOT, 20, [far], now=NOW, covered=True)
    assert result["count"] == 0


def test_six_fresh_on_hour_incidents_are_red_with_reason():
    incidents = [incident(id=i) for i in range(6)]
    result = risk.score(*SPOT, 20, incidents, now=NOW, covered=True)
    assert result["level"] == "red"
    assert result["count"] == 6
    assert result["reason"] == "6 reported incidents within 1 km, 6 of them around this hour."
    assert result["sample"] is True
    assert len(result["sources"]) == 6


def test_hour_profile_and_better_hour():
    from datetime import datetime
    from app import risk
    now = datetime(2026, 10, 1)
    incs = [{"lat": 17.0, "lng": 78.0, "source_type": "news", "date": "2026-10-01", "incident_hour": 22}] * 6
    prof = risk.hour_profile(17.0, 78.0, incs, now=now)
    assert len(prof) == 24 and prof[22]["level"] == "red"
    better = risk.better_hour(prof, 22, "red")
    assert better["hour"] == 1 and better["in_hours"] == 3
    assert risk.better_hour(prof, 10, "green") is None


def test_geocode_query_normalized():
    from app import geocode
    assert geocode.normalize("Begum Bazar , Hyderabad") == "begum bazar"
    assert geocode.normalize("Hyderabad") == "hyderabad"
