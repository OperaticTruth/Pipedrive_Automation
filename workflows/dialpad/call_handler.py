"""
Dialpad call webhook handler: answered and missed calls → Pipedrive activities.
"""

import logging
from datetime import timezone
from .utils import (
    extract_external_phone,
    format_call_note,
    is_phone_number_string,
    is_spam_number,
    seconds_to_duration,
    to_pacific,
)
from .dialpad_client import DialpadClient
from .pipedrive_helpers import (
    check_is_business,
    create_person_from_phone,
    create_person_in_pipedrive,
    create_pipedrive_activity,
    find_person_by_phone,
    get_most_recent_open_deal,
)

logger = logging.getLogger(__name__)


def handle_call_event(event_data: dict | None) -> dict:
    """
    Process a Dialpad call webhook. Act only on state hangup (answered) or missed.
    event_data: decoded webhook payload (from JSON or JWT); route should decode before calling.
    """
    payload = event_data or {}
    if not isinstance(payload, dict):
        logger.warning("Call webhook: invalid payload")
        return {"success": True, "skipped": "no_payload"}

    state = payload.get("state")
    if state not in ("hangup", "missed"):
        logger.debug("Call webhook: ignoring state=%s", state)
        return {"success": True, "skipped": True, "state": state}

    call_id = payload.get("call_id")
    direction = payload.get("direction", "inbound")
    external_phone = extract_external_phone(payload)

    if not external_phone:
        logger.warning("Call webhook: no external phone in payload")
        return {"success": True, "skipped": "no_phone"}

    person = find_person_by_phone(external_phone)
    # Check if Dialpad payload has a real name for this caller
    contact_obj = payload.get("contact") or {}
    dialpad_name = (contact_obj.get("name") or contact_obj.get("display_name") or "").strip()
    if person:
        person_id = person["id"]
        person_name = person.get("name", external_phone)
        is_business = check_is_business(person)
        # If the existing PD name is a placeholder and Dialpad has a real name, update it
        if dialpad_name and not is_phone_number_string(dialpad_name) and is_phone_number_string(person_name):
            from .pipedrive_helpers import update_person_fields
            if update_person_fields(person_id, {"name": dialpad_name}):
                person_name = dialpad_name
                logger.info("Updated placeholder name for %s → %s", external_phone, dialpad_name)
    else:
        if is_spam_number(external_phone, name=None):
            return {"success": True, "skipped": "spam"}
        # Use contact name from Dialpad payload if available (known local contact)
        if dialpad_name and not is_phone_number_string(dialpad_name):
            person_id = create_person_in_pipedrive(name=dialpad_name, phone=external_phone)
            person_name = dialpad_name
        else:
            person_id = create_person_from_phone(external_phone)
            person_name = external_phone
        if not person_id:
            return {"success": False, "error": "Failed to create person"}
        is_business = False

    deal_id = None
    if not is_business:
        deal_id = get_most_recent_open_deal(person_id)

    if state == "missed":
        return _handle_missed_call(
            payload=payload,
            direction=direction,
            person_id=person_id,
            person_name=person_name,
            deal_id=deal_id,
        )

    return _handle_answered_call(
        call_id=call_id,
        payload=payload,
        direction=direction,
        person_id=person_id,
        person_name=person_name,
        deal_id=deal_id,
    )


def _handle_missed_call(
    payload: dict,
    direction: str,
    person_id: int,
    person_name: str,
    deal_id: int | None,
) -> dict:
    """Create a deadline activity for a missed call."""
    call_started = payload.get("date_started") or payload.get("start_time") or payload.get("timestamp")
    call_dt_pt = to_pacific(call_started)
    call_dt_utc = call_dt_pt.astimezone(timezone.utc)
    subject = f"Missed Call [{direction.capitalize()}] — {person_name}"
    note = (
        f"Missed {direction} call on {call_dt_pt.strftime('%B %d, %Y')} "
        f"at {call_dt_pt.strftime('%I:%M %p PT')}.<br>No answer — no summary available."
    )
    create_pipedrive_activity(
        activity_type="missed_call",
        subject=subject,
        person_id=person_id,
        deal_id=deal_id,
        due_date=call_dt_utc.strftime("%Y-%m-%d"),
        due_time=call_dt_utc.strftime("%H:%M"),
        note=note,
        done=True,
    )
    return {"success": True}


def _handle_answered_call(
    call_id: str,
    payload: dict,
    direction: str,
    person_id: int,
    person_name: str,
    deal_id: int | None,
) -> dict:
    """Fetch call details + AI summary, then create call activity."""
    if not call_id:
        logger.warning("Answered call webhook: missing call_id")
        return {"success": True, "skipped": "no_call_id"}

    client = DialpadClient()
    call_data = client.get_call_with_summary_retry(call_id)
    recap = call_data.get("recap_summary", "")
    action_items = call_data.get("action_items", "")
    recording_url = call_data.get("recording_url", "")
    if not recording_url and call_data.get("recording_urls"):
        first = call_data["recording_urls"][0]
        recording_url = first.get("url", "") if isinstance(first, dict) else str(first)
    raw_duration = call_data.get("duration", 0) or 0
    duration_sec = int(raw_duration / 1000)  # Dialpad always returns duration in milliseconds
    call_started = call_data.get("date_started") or call_data.get("start_time") or payload.get("date_started")
    call_dt_pt = to_pacific(call_started)
    call_dt_utc = call_dt_pt.astimezone(timezone.utc)

    if not recap:
        logger.warning("AI summary still empty for call %s after retries", call_id)

    note_text = format_call_note(
        direction=direction,
        duration_sec=duration_sec,
        call_datetime_pt=call_dt_pt,
        summary=recap,
        action_items=action_items,
        recording_url=recording_url,
    )
    subject = person_name
    create_pipedrive_activity(
        activity_type="call",  # Pipedrive activity type: Call
        subject=subject,
        person_id=person_id,
        deal_id=deal_id,
        due_date=call_dt_utc.strftime("%Y-%m-%d"),
        due_time=call_dt_utc.strftime("%H:%M"),
        duration=seconds_to_duration(duration_sec),
        note=note_text,
        done=True,
    )
    return {"success": True}
