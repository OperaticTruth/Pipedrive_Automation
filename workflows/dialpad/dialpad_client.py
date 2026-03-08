"""
Dialpad REST API client.
"""

import time
import requests
import logging
from config import DIALPAD_API_KEY

logger = logging.getLogger(__name__)
DIALPAD_BASE = "https://dialpad.com/api/v2"


class DialpadClient:
    def __init__(self):
        self.api_key = DIALPAD_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_call(self, call_id: str) -> dict:
        r = requests.get(f"{DIALPAD_BASE}/call/{call_id}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_call_with_summary_retry(
        self, call_id: str, max_attempts: int = 3, delay: int = 30
    ) -> dict:
        """Retry until AI summary is ready (up to max_attempts × delay seconds)."""
        for attempt in range(max_attempts):
            data = self.get_call(call_id)
            if data.get("recap_summary"):
                return data
            if attempt < max_attempts - 1:
                logger.info(
                    "AI summary not ready for call %s, retrying in %ss...", call_id, delay
                )
                time.sleep(delay)
        return data

    def search_contact_by_phone(self, phone: str) -> dict | None:
        """Search for a contact by phone using the full contacts list (search API misses local contacts)."""
        import re
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if not digits:
            return None
        for contact in self.list_all_contacts():
            primary = contact.get("primary_phone", "")
            phones_list = contact.get("phones") or []
            all_phones = [primary] + [
                (p if isinstance(p, str) else p.get("phone", "")) for p in phones_list
            ]
            for p in all_phones:
                p_digits = re.sub(r"\D", "", p or "")
                if len(p_digits) == 11 and p_digits.startswith("1"):
                    p_digits = p_digits[1:]
                if p_digits and p_digits == digits:
                    return contact
        return None

    def list_all_contacts(self) -> list:
        """Fetch all contacts from Dialpad (paginated), including local and shared."""
        contacts = []
        cursor = None
        while True:
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(
                f"{DIALPAD_BASE}/contacts",
                headers=self.headers,
                params=params,
                timeout=30,
            )
            if not r.ok:
                # Dialpad cursor pagination can return 400 on subsequent pages — stop gracefully
                logger.warning("Dialpad contacts page returned %s — stopping pagination with %d contacts so far", r.status_code, len(contacts))
                break
            data = r.json()
            contacts.extend(data.get("items", []))
            cursor = data.get("next_cursor") or data.get("cursor")
            if not cursor or not data.get("items"):
                break
        return contacts

    def create_contact(self, name: str, phone: str) -> dict:
        payload = {"display_name": name, "phones": [{"phone": phone}]}
        r = requests.post(
            f"{DIALPAD_BASE}/contacts",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def update_contact(
        self, contact_id: str, name: str | None = None, phone: str | None = None
    ) -> dict:
        payload = {}
        if name is not None:
            payload["display_name"] = name
        if phone is not None:
            payload["phones"] = [{"phone": phone}]
        r = requests.patch(
            f"{DIALPAD_BASE}/contacts/{contact_id}",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
