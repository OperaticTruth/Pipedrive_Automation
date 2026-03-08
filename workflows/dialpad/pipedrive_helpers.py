"""
Pipedrive helpers for Dialpad: find by phone, open deals, activities, person CRUD.
Uses raw requests and config (same pattern as workflows/utils.py and salesforce_sync).
"""

import re
import requests
import logging
from config import (
    PIPEDRIVE_API_KEY,
    CONTACT_TYPE_KEY,
    CONTACT_TYPE_BUSINESS_ID,
)

logger = logging.getLogger(__name__)
BASE_URL = "https://api.pipedrive.com/v1"


def _format_phone_display(phone: str) -> str:
    """
    Format a raw phone number into a readable display name.
    +17024982856 or 17024982856 → (702) 498-2856
    Falls back to original if not a standard 10-digit US number.
    """
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def _normalize_phone_variants(phone: str) -> list[str]:
    """
    Return a list of phone number variants to try when searching Pipedrive.
    Handles E.164 (+17037311745) vs local (7037311745) vs formatted (703-731-1745).
    """
    variants = [phone.strip()]
    digits_only = re.sub(r"\D", "", phone)
    # Strip leading country code 1 for US numbers
    if len(digits_only) == 11 and digits_only.startswith("1"):
        digits_only = digits_only[1:]
    if digits_only and digits_only not in variants:
        variants.append(digits_only)
    return variants


def _search_pipedrive_phone(term: str) -> dict | None:
    """Search Pipedrive persons by a single phone term. Returns full person dict or None."""
    url = f"{BASE_URL}/persons/search"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "term": term,
        "fields": "phone",
        "exact_match": True,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("data", {}).get("items", [])
        if not items:
            return None
        person_id = items[0].get("item", {}).get("id")
        if not person_id:
            return None
        full_resp = requests.get(
            f"{BASE_URL}/persons/{person_id}",
            params={"api_token": PIPEDRIVE_API_KEY},
            timeout=30,
        )
        full_resp.raise_for_status()
        return full_resp.json().get("data")
    except Exception as e:
        logger.error("Error searching person by phone %s: %s", term, e)
        return None


def find_person_by_phone(phone: str) -> dict | None:
    """
    Find a Pipedrive Person by phone number.
    Tries multiple formats (E.164, 10-digit local) to handle mismatches
    between how Dialpad sends numbers vs how Pipedrive stores them.
    Returns the full person dict or None if not found.
    """
    if not phone:
        return None
    for variant in _normalize_phone_variants(phone):
        person = _search_pipedrive_phone(variant)
        if person:
            return person
    return None


def get_most_recent_open_deal(person_id: int) -> int | None:
    """
    Get the most recently created open deal for a person.
    Returns deal_id or None. Picks the one with latest add_time if multiple.
    """
    url = f"{BASE_URL}/persons/{person_id}/deals"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "status": "open",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        deals = resp.json().get("data") or []
        if not deals:
            return None
        deals.sort(key=lambda d: d.get("add_time", ""), reverse=True)
        return deals[0]["id"]
    except Exception as e:
        logger.error("Error getting open deals for person %s: %s", person_id, e)
        return None


def check_is_business(person: dict) -> bool:
    """
    Returns True if this person has Contact Type = 'Business' (ID 89).
    """
    if not CONTACT_TYPE_KEY:
        return False
    ct = person.get(CONTACT_TYPE_KEY)
    if not ct:
        return False
    if isinstance(ct, dict):
        val = ct.get("value")
    elif isinstance(ct, list) and ct:
        val = ct[0].get("value") if isinstance(ct[0], dict) else ct[0]
    else:
        val = ct
    return str(val) == str(CONTACT_TYPE_BUSINESS_ID)


def create_person_from_phone(phone: str) -> int | None:
    """
    Create a new Person in Pipedrive with phone as placeholder name.
    Adds a 'Pending Name' label so it can be cleaned up later.
    """
    display_name = _format_phone_display(phone)
    person_data = {
        "name": display_name,
        "phone": [{"value": phone, "primary": True}],
        "label": "Pending Name",
    }
    url = f"{BASE_URL}/persons"
    try:
        resp = requests.post(
            url,
            params={"api_token": PIPEDRIVE_API_KEY},
            json=person_data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("success"):
            person_id = result["data"]["id"]
            logger.info("Created placeholder Person %s for phone %s", person_id, phone)
            return person_id
        return None
    except Exception as e:
        logger.error("Error creating person from phone %s: %s", phone, e)
        return None


def create_person_in_pipedrive(name: str, phone: str) -> int | None:
    """Create a Person in Pipedrive with real name and phone (no Pending Name label)."""
    person_data = {
        "name": name,
        "phone": [{"value": phone, "primary": True}],
    }
    url = f"{BASE_URL}/persons"
    try:
        resp = requests.post(
            url,
            params={"api_token": PIPEDRIVE_API_KEY},
            json=person_data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("success"):
            person_id = result["data"]["id"]
            logger.info("Created Person %s for %s", person_id, name)
            return person_id
        return None
    except Exception as e:
        logger.error("Error creating person %s: %s", name, e)
        return None


def update_person_fields(person_id: int, updates: dict) -> bool:
    """Update selected fields on a Pipedrive person. Returns True on success."""
    if not updates:
        return True
    url = f"{BASE_URL}/persons/{person_id}"
    try:
        resp = requests.put(
            url,
            params={"api_token": PIPEDRIVE_API_KEY},
            json=updates,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("success"):
            logger.info("Updated Person %s with %s", person_id, list(updates.keys()))
            return True
        return False
    except Exception as e:
        logger.error("Error updating person %s: %s", person_id, e)
        return False


def extract_primary_phone(person: dict) -> str:
    """Extract primary phone from a Pipedrive person's phone array."""
    phones = person.get("phone") or []
    for p in phones:
        if isinstance(p, dict) and p.get("primary"):
            return (p.get("value") or "").strip()
    if phones and isinstance(phones[0], dict):
        return (phones[0].get("value") or "").strip()
    return ""


def already_texted_today(person_id: int, activity_type_key: str = "text") -> bool:
    """Check if an SMS activity already exists for this person today (PT)."""
    from .utils import today_pacific
    today_pt = today_pacific()
    url = f"{BASE_URL}/activities"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "person_id": person_id,
        "type": activity_type_key,
        "start": today_pt,
        "end": today_pt,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data") or []
        return len(data) > 0
    except Exception as e:
        logger.error("Error checking SMS dedup for person %s: %s", person_id, e)
        return False


def create_pipedrive_activity(
    activity_type: str,
    subject: str,
    person_id: int,
    deal_id: int | None,
    due_date: str,
    due_time: str,
    note: str,
    done: bool = True,
    duration: str | None = None,
) -> int | None:
    """
    Create an activity in Pipedrive.
    activity_type: 'call', 'text', 'missed_call' (must match type key in Pipedrive).
    """
    payload = {
        "type": activity_type,
        "subject": subject,
        "person_id": person_id,
        "due_date": due_date,
        "due_time": due_time,
        "note": note,
        "done": 1 if done else 0,
    }
    if deal_id is not None:
        payload["deal_id"] = deal_id
    if duration is not None:
        payload["duration"] = duration

    url = f"{BASE_URL}/activities"
    try:
        resp = requests.post(
            url,
            params={"api_token": PIPEDRIVE_API_KEY},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("success"):
            activity_id = result["data"]["id"]
            logger.info(
                "Created %s activity %s for Person %s",
                activity_type,
                activity_id,
                person_id,
            )
            return activity_id
        logger.error("Failed to create activity: %s", result)
        return None
    except Exception as e:
        logger.error("Error creating activity: %s", e)
        return None
