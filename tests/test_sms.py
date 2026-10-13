from app import sms

AREAS = ["Secunderabad Railway Station", "Gachibowli", "HITEC City", "LB Nagar", "MGBS Bus Station"]


def test_parses_area_and_pm_time_case_insensitive():
    assert sms.parse("radar gachibowli 9PM", AREAS) == ("Gachibowli", 21)


def test_defaults_hour_to_none_when_missing():
    assert sms.parse("RADAR Gachibowli", AREAS) == ("Gachibowli", None)


def test_fuzzy_and_partial_area_names():
    assert sms.parse("RADAR gachibowly", AREAS)[0] == "Gachibowli"
    assert sms.parse("RADAR secunderabad 10:30pm", AREAS) == ("Secunderabad Railway Station", 22)
    assert sms.parse("RADAR hitec city 7 am", AREAS) == ("HITEC City", 7)
    assert sms.parse("RADAR lb nagar 12am", AREAS) == ("LB Nagar", 0)


def test_unknown_area_or_missing_keyword():
    assert sms.parse("RADAR Warangal", AREAS) == (None, None)
    assert sms.parse("hello", AREAS) == (None, None)


def test_reply_fits_one_sms_and_never_says_safe():
    result = {"level": "green", "count": 0, "total": 0, "reason": "No reported incidents nearby.", "sample": True}
    text = sms.reply_text("Secunderabad Railway Station", 21, result)
    assert len(text) <= 160
    assert "safe" not in text.lower()
    red = {"level": "red", "count": 9, "total": 7.0, "sample": True,
           "reason": "9 reported incidents within 1 km, 9 of them around this hour."}
    assert len(sms.reply_text("Secunderabad Railway Station", 22, red)) <= 160


def test_long_reply_keeps_sample_tag_and_advice():
    red = {"level": "red", "count": 12, "total": 9.0, "sample": True,
           "reason": "12 reported incidents within 1 km, 11 of them around this hour."}
    text = sms.reply_text("Secunderabad Railway Station", 22, red)
    assert len(text) <= 160
    assert text.endswith("[SAMPLE DATA]")
    assert "share" in text.lower()
