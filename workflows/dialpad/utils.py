"""
Dialpad integration utilities: timezone, spam checks, note formatters, JWT decode.
Uses python-dateutil (already in requirements), PyJWT for webhook verification.
"""

import re
import logging
from typing import Any

try:
    import jwt
except ImportError:
    jwt = None
from datetime import datetime, timezone
from dateutil import tz

logger = logging.getLogger(__name__)
PACIFIC = tz.gettz("America/Los_Angeles")


def is_spam(name: str) -> bool:
    """Returns True if contact name looks like spam and should be skipped."""
    if not name:
        return True
    if re.search(r'\bca\b', name.lower()):
        return True
    if re.match(r"^\+?[\d\s\-\(\)\.]+$", name.strip()):
        return True
    return False


def is_spam_number(phone: str, name: str | None = None) -> bool:
    """
    Returns True if the contact should be treated as spam (skip creating activity).
    If name is provided, uses is_spam(name). Otherwise no phone blacklist in use.
    """
    if name is not None and is_spam(name):
        return True
    if not phone or len(phone.strip()) < 10:
        return True
    return False


def is_valid_name(name: str) -> bool:
    """Valid for Dialpad→PD sync: not empty, not spam."""
    return bool(name and name.strip() and not is_spam(name))


def is_phone_number_string(s: str) -> bool:
    """Returns True if string looks like a raw phone number (placeholder name)."""
    if not s:
        return False
    return bool(re.match(r"^\+?[\d\s\-\(\)\.]+$", s.strip()))


def to_pacific(timestamp) -> datetime:
    """
    Convert a Unix timestamp (int/float, seconds or milliseconds) or ISO string
    to Pacific Time datetime. Dialpad returns timestamps in milliseconds.
    """
    # Coerce numeric strings to numbers first
    if isinstance(timestamp, str):
        stripped = timestamp.strip()
        if stripped.lstrip("-").isdigit():
            timestamp = int(stripped)
        else:
            try:
                timestamp = float(stripped)
            except ValueError:
                pass

    if isinstance(timestamp, (int, float)):
        if timestamp > 1e10:  # milliseconds → convert to seconds
            timestamp = timestamp / 1000
        dt_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    elif isinstance(timestamp, str):
        from dateutil.parser import parse
        dt_utc = parse(timestamp)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = datetime.now(timezone.utc)
    return dt_utc.astimezone(PACIFIC)


def today_pacific() -> str:
    """Returns today's date in PT as YYYY-MM-DD string."""
    return datetime.now(PACIFIC).strftime("%Y-%m-%d")


def seconds_to_duration(seconds: int) -> str:
    """Convert seconds to HH:MM:SS string (Pipedrive duration field format)."""
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def extract_external_phone(payload: dict) -> str:
    """
    Extract the external (non-Jake) party's phone number from a Dialpad call/SMS payload.
    For inbound: the caller's number. For outbound: the number dialed.
    """
    direction = payload.get("direction", "")
    contact = payload.get("contact", {}) or {}
    target = payload.get("target", {}) or {}

    if direction == "inbound":
        return (
            contact.get("phone", "")
            or contact.get("number", "")
            or target.get("phone", "")
            or target.get("number", "")
            or ""
        ).strip()
    else:
        return (
            contact.get("phone", "")
            or contact.get("number", "")
            or target.get("phone", "")
            or target.get("number", "")
            or ""
        ).strip()


def format_call_note(
    direction: str,
    duration_sec: int,
    call_datetime_pt: datetime,
    summary: str,
    action_items: str,
    recording_url: str,
) -> str:
    """Build the formatted note body for a completed call activity."""
    duration_str = f"{duration_sec // 60} min {duration_sec % 60} sec"
    dt_str = call_datetime_pt.strftime("%B %d, %Y at %I:%M %p PT")
    note = (
        f"📞 <b>Call Summary</b><br>"
        f"<b>Direction:</b> {direction.capitalize()}<br>"
        f"<b>Duration:</b> {duration_str}<br>"
        f"<b>Date/Time:</b> {dt_str}<br><br>"
        f"─────────────────────────<br>"
        f"<b>SUMMARY</b><br>"
        f"{summary or 'Summary not available.'}<br>"
    )
    if action_items:
        note += f"<br><b>ACTION ITEMS</b><br>{action_items}<br>"
    note += f"<br>─────────────────────────<br>🔗 <b>Full Recording & Transcript:</b> {recording_url or 'Not available'}"
    return note


def decode_dialpad_webhook(body: str | bytes, secret: str | None) -> dict[str, Any] | None:
    """
    Decode Dialpad webhook payload. Body may be raw JWT string or JSON.
    If secret is set and body looks like JWT, verify and decode. Otherwise parse as JSON.
    """
    if not body:
        return None
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace").strip()
    if secret and jwt and body.startswith("eyJ"):
        try:
            decoded = jwt.decode(
                body, secret, algorithms=["HS256"], options={"verify_signature": True}
            )
            return decoded
        except Exception as e:
            logger.warning("Dialpad JWT decode failed: %s", e)
            return None
    try:
        import json
        return json.loads(body) if body else None
    except Exception as e:
        logger.warning("Dialpad webhook body parse failed: %s", e)
        return None
