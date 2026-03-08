"""
Dialpad ↔ Pipedrive Integration

Handles call activity logging, SMS deduplication, and bidirectional contact sync.
"""

from .call_handler import handle_call_event
from .sms_handler import handle_sms_event
from .contact_sync import handle_dialpad_contact_event, run_dialpad_contact_sync, resolve_pending_names

__all__ = [
    "handle_call_event",
    "handle_sms_event",
    "handle_dialpad_contact_event",
    "run_dialpad_contact_sync",
    "resolve_pending_names",
]
