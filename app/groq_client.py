"""Minimal Groq client on the standard library (no SDK dependency).

Groq speaks the OpenAI-compatible REST API: https://console.groq.com/docs
"""
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app import config

BASE = "https://api.groq.com/openai/v1"


class GroqError(RuntimeError):
    pass


def enabled():
    return bool(config.GROQ_API_KEY)


def _request(url, data, content_type, timeout):
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": content_type,
        "User-Agent": "ride-radar/1.1",  # Groq's edge rejects urllib's default agent
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise GroqError(f"Groq HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise GroqError(f"Groq unreachable: {e.reason}") from None


def chat_json(system, user, schema, name="result", timeout=60):
    """Chat completion constrained to a strict JSON schema. Returns the parsed object."""
    body = {
        "model": config.GROQ_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    data = _request(f"{BASE}/chat/completions", json.dumps(body).encode("utf-8"), "application/json", timeout)
    try:
        return json.loads(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise GroqError(f"unexpected Groq response: {e}") from None


def transcribe(path, mime, timeout=120):
    """Speech to text with Whisper on Groq. Returns the transcript text."""
    path = Path(path)
    boundary = uuid.uuid4().hex
    parts = []
    for field, value in (("model", config.GROQ_WHISPER_MODEL), ("response_format", "json")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode()
    )
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    data = _request(f"{BASE}/audio/transcriptions", b"".join(parts),
                    f"multipart/form-data; boundary={boundary}", timeout)
    return (data.get("text") or "").strip()
