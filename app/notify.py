"""Reaching emergency contacts: WhatsApp Cloud API when configured, prefilled wa.me links otherwise."""
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from app import config

log = logging.getLogger("ride_radar.notify")


def whatsapp_configured():
    return bool(config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID and config.WHATSAPP_TEMPLATE)


def digits(phone):
    return re.sub(r"\D", "", phone)


def alert_text(name, url):
    return f"{name}, I need help. Live location and video from Ride Radar: {url}"


def wa_link(phone, name, url):
    """A link that opens WhatsApp with the alert prefilled; the rider taps send."""
    return f"https://wa.me/{digits(phone)}?text={urllib.parse.quote(alert_text(name, url))}"


def send_whatsapp(phone, name, url):
    """Send the approved alert template through the WhatsApp Cloud API. Returns True on success.

    Business-initiated WhatsApp messages must use a template approved in Meta Business Manager,
    with body parameters {{1}} = contact name and {{2}} = alert link.
    """
    body = {
        "messaging_product": "whatsapp",
        "to": digits(phone),
        "type": "template",
        "template": {
            "name": config.WHATSAPP_TEMPLATE,
            "language": {"code": config.WHATSAPP_TEMPLATE_LANG},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": name}, {"type": "text", "text": url}]}],
        },
    }
    req = urllib.request.Request(
        f"https://graph.facebook.com/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        log.error("WhatsApp send failed: HTTP %s %s", e.code, e.read().decode("utf-8", "replace")[:300])
    except urllib.error.URLError as e:
        log.error("WhatsApp unreachable: %s", e.reason)
    return False


def notify_contacts(contacts, url):
    """Try automatic WhatsApp. Returns (status, links) where status is sent, partial, manual or failed.

    Links are always returned so the phone can offer one-tap sending for anyone not reached.
    """
    links = [{"name": c["name"], "href": wa_link(c["phone"], c["name"], url)} for c in contacts]
    if not contacts:
        return "none", []
    if not whatsapp_configured():
        return "manual", links
    ok = [send_whatsapp(c["phone"], c["name"], url) for c in contacts]
    if all(ok):
        return "sent", links
    return ("partial" if any(ok) else "failed"), links
