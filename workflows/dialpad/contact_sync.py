"""
Bidirectional contact sync: Pipedrive ↔ Dialpad.
- PD → Dialpad: scheduled (or manual) push of recently updated persons.
- Dialpad → PD: webhook when contact is created/updated in Dialpad; PD wins on conflict.
"""

import re
import logging
import requests
from datetime import datetime, timedelta, timezone

from config import PIPEDRIVE_API_KEY
from .utils import is_spam, is_valid_name, is_phone_number_string
from .pipedrive_helpers import (
    extract_primary_phone,
    find_person_by_phone,
    create_person_in_pipedrive,
    update_person_fields,
)
from .dialpad_client import DialpadClient

logger = logging.getLogger(__name__)
BASE_URL = "https://api.pipedrive.com/v1"


def _last10(phone: str) -> str:
    """Return the last 10 digits of a phone number for comparison."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _phones_match(phone1: str, phone2: str) -> bool:
    """True if two phone numbers refer to the same 10-digit US number."""
    d1, d2 = _last10(phone1), _last10(phone2)
    return bool(d1 and d2 and d1 == d2)


def _extract_dialpad_phone(dp_contact: dict) -> str:
    """Pull the first phone number out of a Dialpad contact dict."""
    # primary_phone is most reliable
    if dp_contact.get("primary_phone"):
        return dp_contact["primary_phone"]
    # phones can be a list of strings OR a list of dicts
    phones = dp_contact.get("phones") or []
    if phones:
        if isinstance(phones[0], str):
            return phones[0]
        if isinstance(phones[0], dict):
            return phones[0].get("phone", "") or phones[0].get("number", "")
    return dp_contact.get("phone", "") or dp_contact.get("number", "")


def _parse_ts(ts) -> float:
    """Parse Pipedrive timestamp (ISO string or unix) to epoch float for comparison."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        from dateutil.parser import parse
        return parse(ts).timestamp()
    except Exception:
        return 0.0


def handle_dialpad_contact_event(event_data: dict | None) -> dict:
    """
    Process Dialpad contact webhook: create or update Pipedrive person.
    Pipedrive always wins: only update PD if field is blank or phone placeholder.
    """
    payload = event_data or {}
    if not isinstance(payload, dict):
        return {"success": True, "skipped": "no_payload"}

    name = (payload.get("display_name") or payload.get("name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if isinstance(payload.get("phones"), list) and payload["phones"]:
        phone = (payload["phones"][0].get("phone") or payload["phones"][0].get("number") or phone) or phone
    if not phone and isinstance(payload.get("contact"), dict):
        ph = payload["contact"].get("phone") or payload["contact"].get("number")
        if ph:
            phone = str(ph).strip()

    if not is_valid_name(name):
        return {"success": True, "skipped": "invalid_name"}

    existing = find_person_by_phone(phone)
    if existing:
        updates = {}
        current_name = (existing.get("name") or "").strip()
        if not current_name or is_phone_number_string(current_name):
            updates["name"] = name
        if updates:
            update_person_fields(existing["id"], updates)
        return {"success": True}
    else:
        pid = create_person_in_pipedrive(name=name, phone=phone)
        return {"success": True} if pid else {"success": False, "error": "Failed to create person"}


def sync_pipedrive_to_dialpad(minutes_ago: int = 65) -> dict:
    """
    Push recently updated Pipedrive persons to Dialpad.
    Uses overlapping window (e.g. 65 min) to avoid gaps when run every ~60 min.
    """
    since_dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    since_ts = since_dt.timestamp()
    url = f"{BASE_URL}/persons"
    used_fallback = False
    try:
        resp = requests.get(
            url,
            params={"api_token": PIPEDRIVE_API_KEY, "limit": 500, "since_timestamp": since_str},
            timeout=60,
        )
        if resp.status_code == 400:
            resp = requests.get(
                url,
                params={"api_token": PIPEDRIVE_API_KEY, "limit": 500},
                timeout=60,
            )
            resp.raise_for_status()
            used_fallback = True
        else:
            resp.raise_for_status()
        data = resp.json()
        persons = data.get("data") or []
        if used_fallback:
            persons = [p for p in persons if _parse_ts(p.get("update_time") or p.get("add_time")) >= since_ts]
    except Exception as e:
        logger.error("Failed to fetch persons from Pipedrive: %s", e)
        return {"success": False, "error": str(e)}

    if data.get("success") is False and not persons:
        return {"success": False, "error": data.get("error", "Unknown error")}

    client = DialpadClient()
    synced = 0
    for person in persons:
        name = (person.get("name") or "").strip()
        phone = extract_primary_phone(person)
        if not phone or not name:
            continue
        if is_spam(name):
            continue
        existing = client.search_contact_by_phone(phone)
        try:
            if existing:
                client.update_contact(existing["id"], name=name, phone=phone)
            else:
                client.create_contact(name=name, phone=phone)
            synced += 1
        except Exception as e:
            logger.warning("Sync failed for %s (%s): %s", name, phone, e)

    return {"success": True, "synced": synced, "total": len(persons)}


def run_dialpad_contact_sync(minutes_ago: int = 65) -> dict:
    """Entry point for manual or scheduled PD → Dialpad contact sync."""
    return sync_pipedrive_to_dialpad(minutes_ago=minutes_ago)


def resolve_pending_names() -> dict:
    """
    Find all Pipedrive persons whose name is a phone placeholder (e.g. '(702) 498-2856'),
    look each one up in Dialpad by phone, and update PD with the real name if found.
    Run this on a schedule or manually after updating contact names in Dialpad.
    """
    url = f"{BASE_URL}/persons"
    all_persons = []
    start = 0
    while True:
        try:
            resp = requests.get(
                url,
                params={"api_token": PIPEDRIVE_API_KEY, "limit": 500, "start": start},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Failed to fetch persons from Pipedrive: %s", e)
            return {"success": False, "error": str(e)}

        all_persons.extend(data.get("data") or [])
        pagination = data.get("additional_data", {}).get("pagination", {})
        if not pagination.get("more_items_in_collection"):
            break
        start += 500

    pending = [
        p for p in all_persons
        if is_phone_number_string((p.get("name") or "").strip())
    ]

    if not pending:
        return {"success": True, "resolved": 0, "checked": 0}

    # Build a phone→contact map from Dialpad once (search API misses local contacts)
    try:
        client = DialpadClient()
        all_dp_contacts = client.list_all_contacts()
    except Exception as e:
        logger.error("Failed to fetch Dialpad contacts: %s", e)
        return {"success": False, "error": str(e)}

    import re as _re
    def _digits10(p):
        d = _re.sub(r"\D", "", p or "")
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        return d

    dp_by_phone = {}
    for c in all_dp_contacts:
        primary = c.get("primary_phone", "")
        phones_list = c.get("phones") or []
        all_phones = [primary] + [
            (p if isinstance(p, str) else p.get("phone", "")) for p in phones_list
        ]
        for p in all_phones:
            d = _digits10(p)
            if d:
                dp_by_phone[d] = c

    logger.debug("Loaded %d Dialpad contacts into lookup map", len(dp_by_phone))
    logger.debug("Map keys containing '702': %s", [k for k in dp_by_phone if "702" in k])
    # Log any contacts with no phone stored at all
    no_phone = [c.get("display_name") for c in all_dp_contacts if not c.get("primary_phone") and not c.get("phones")]
    logger.debug("Contacts with no phone in API: %s", no_phone[:20])

    resolved = 0
    for person in pending:
        phone = extract_primary_phone(person)
        key = _digits10(phone) if phone else ""
        logger.debug("Pending person '%s' → phone=%s key=%s in_map=%s", person.get("name"), phone, key, key in dp_by_phone)
        if not phone:
            continue
        dp_contact = dp_by_phone.get(key)
        if not dp_contact:
            continue
        dp_name = (dp_contact.get("display_name") or dp_contact.get("name") or "").strip()
        logger.debug("  Dialpad match found — name='%s' is_placeholder=%s", dp_name, is_phone_number_string(dp_name))
        if not dp_name or is_phone_number_string(dp_name):
            continue
        updates = {"name": dp_name, "label": None}
        if update_person_fields(person["id"], updates):
            logger.info("Resolved pending name %s → %s", phone, dp_name)
            resolved += 1

    return {"success": True, "resolved": resolved, "checked": len(pending)}
