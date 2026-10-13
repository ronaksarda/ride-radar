"""SMS parsing and reply text. Message format: RADAR <area> [time], e.g. "RADAR Gachibowli 9PM"."""
import difflib
import re

KEYWORD = "radar"
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)
LABELS = {"green": "GREEN", "amber": "AMBER", "red": "RED", "not_covered": "NOT COVERED"}
ADVICE = {
    "amber": "Try a busier stop or another time.",
    "red": "Try a busier stop or another time. Share your trip.",
}
HELP = "Ride Radar: text RADAR <area> [time], e.g. RADAR Gachibowli 9PM. In danger? Call 112."
STOP = "Ride Radar only replies when you text it. You will get no other messages."
STOP_WORDS = {"stop", "unsubscribe", "cancel", "end", "quit"}


def keyword_reply(body):
    """Reply for HELP/STOP-style keywords, or None when the text is a normal query."""
    word = (body or "").strip().lower()
    if word in STOP_WORDS:
        return STOP
    if word in {"help", "info", "radar"}:
        return HELP
    return None


def _parse_hour(text):
    m = TIME_RE.search(text)
    if not m:
        return text, None
    hour, minutes, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ampm:
        if not 1 <= hour <= 12:
            return text, None
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    elif hour > 23 or minutes > 59:
        return text, None
    return text[: m.start()].strip(), hour


def _match_area(query, area_names):
    q = query.lower().strip()
    if not q:
        return None
    lowered = {name.lower(): name for name in area_names}
    if q in lowered:
        return lowered[q]
    for low, name in lowered.items():
        if low.startswith(q) or q in re.split(r"[ ()]+", low):
            return name
    # fuzzy: compare against full names and their first words
    candidates = dict(lowered)
    for low, name in lowered.items():
        candidates.setdefault(low.split(" (")[0], name)
    best = difflib.get_close_matches(q, list(candidates), n=1, cutoff=0.75)
    return candidates[best[0]] if best else None


def parse(body, area_names):
    """Return (area_name, hour) or (None, None). hour is None when the text gives no time."""
    words = (body or "").strip().split(None, 1)
    if len(words) < 2 or words[0].lower() != KEYWORD:
        return None, None
    rest, hour = _parse_hour(words[1])
    area = _match_area(rest, area_names)
    if not area:
        return None, None
    return area, hour


def reply_text(area_name, hour, result):
    short_area = area_name.split(" (")[0]
    if len(short_area) > 14:  # "Secunderabad Railway Station" -> "Secunderabad"
        short_area = short_area.split()[0]
    label = LABELS[result["level"]]
    head = f"{label}: {short_area} ~{hour:02d}:00."
    advice = ADVICE.get(result["level"], "")
    tag = "[SAMPLE DATA]" if result.get("sample") else ""
    fixed = " ".join(p for p in (head, advice, tag) if p)
    # the reason line is the only part that gets shortened, so label, advice and tag always survive
    room = 160 - len(fixed) - 1
    reason = result["reason"] if len(result["reason"]) <= room else result["reason"][: room - 3].rstrip() + "..."
    return " ".join(p for p in (head, reason, advice, tag) if p)
