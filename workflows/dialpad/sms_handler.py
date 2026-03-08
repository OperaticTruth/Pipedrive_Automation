"""
Dialpad SMS webhook handler: one activity per person per PT day, linked to deal when applicable.
"""

import logging
from .utils import extract_external_phone, is_spam_number, to_pacific
from .pipedrive_helpers import (
    already_texted_today,
    check_is_business,
    create_person_from_phone,
    create_pipedrive_activity,
    find_person_by_phone,
    get_most_recent_open_deal,
)

logger = logging.getLogger(__name__)

SMS_NOTE_MAX_LEN = 300


def handle_sms_event(event_data: dict | None) -> dict:
    """
    Process a Dialpad SMS webhook. Dedupe: one SMS activity per person per PT day.
    event_data: decoded webhook payload (from JSON or JWT); route should decode before calling.
    """
    payload = event_data or {}
    if not isinstance(payload, dict):
        logger.warning("SMS webhook: invalid payload")
        return {"success": True, "skipped": "no_payload"}

    external_phone = extract_external_phone(payload)
    if not external_phone:
        logger.warning("SMS webhook: no external phone")
        return {"success": True, "skipped": "no_phone"}

    ts = payload.get("timestamp") or payload.get("date") or payload.get("created_at")
    msg_dt_pt = to_pacific(ts)
    direction = payload.get("direction", "inbound")

    person = find_person_by_phone(external_phone)
    if person:
        person_id = person["id"]
        person_name = person.get("name", external_phone)
        is_business = check_is_business(person)
    else:
        if is_spam_number(external_phone, name=None):
            return {"success": True, "skipped": "spam"}
        person_id = create_person_from_phone(external_phone)
        if not person_id:
            return {"success": False, "error": "Failed to create person"}
        person_name = external_phone
        is_business = False

    if already_texted_today(person_id):
        return {"success": True, "skipped": "dedup"}

    text = (payload.get("text") or payload.get("body") or payload.get("message") or "").strip()
    if len(text) > SMS_NOTE_MAX_LEN:
        text = text[:SMS_NOTE_MAX_LEN] + "…"

    note = (
        'First message today:\n\n"%s"\n\nDirection: %s'
        % (text.replace('"', "'"), direction.capitalize())
    )

    deal_id = None
    if not is_business:
        deal_id = get_most_recent_open_deal(person_id)

    subject = f"Text — {person_name}"
    create_pipedrive_activity(
        activity_type="text",  # Pipedrive activity type: Text
        subject=subject,
        person_id=person_id,
        deal_id=deal_id,
        due_date=msg_dt_pt.strftime("%Y-%m-%d"),
        due_time=msg_dt_pt.strftime("%H:%M"),
        note=note,
        done=True,
    )
    return {"success": True}
