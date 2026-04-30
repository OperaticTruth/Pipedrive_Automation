"""
Lightweight local instrumentation for Salesforce -> Pipedrive syncs.

This module keeps per-loan audit records for outbound-message processing and
counts Pipedrive API calls by endpoint/category. Records are written locally as
JSONL so they can be inspected without any external writes.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "salesforce_sync_metrics.jsonl"
_ACTIVE_AUDIT = contextvars.ContextVar("salesforce_sync_active_audit", default=None)
_WRITE_LOCK = threading.Lock()
_PATCH_LOCK = threading.Lock()
_ORIGINAL_SESSION_REQUEST = requests.sessions.Session.request
_PATCH_INSTALLED = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit_log_path() -> Path:
    override = os.getenv("SALESFORCE_SYNC_AUDIT_LOG")
    return Path(override) if override else _DEFAULT_LOG_PATH


def _is_pipedrive_url(url: str) -> bool:
    try:
        return urlparse(url).netloc.lower() == "api.pipedrive.com"
    except Exception:
        return False


def _classify_pipedrive_request(method: str, url: str) -> Tuple[str, str]:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[0] in {"v1", "v2", "api"}:
        segments = segments[1:]

    entity = segments[0] if segments else "unknown"
    action = method.upper()

    def update_action(default_get: str = "get") -> str:
        if action == "GET":
            return default_get
        if action in {"PUT", "PATCH"}:
            return "update"
        if action == "POST":
            return "create"
        if action == "DELETE":
            return "delete"
        return action.lower()

    if entity == "persons":
        if len(segments) >= 2 and segments[1] == "search":
            endpoint = "persons.search"
        elif len(segments) >= 3 and segments[2] == "deals":
            endpoint = "persons.deals"
        elif len(segments) >= 2:
            endpoint = f"persons.{update_action()}"
        else:
            endpoint = f"persons.{update_action(default_get='list')}"
    elif entity == "deals":
        if len(segments) >= 2 and segments[1] == "search":
            endpoint = "deals.search"
        elif len(segments) >= 2 and segments[1] == "archived":
            endpoint = "deals.archived"
        elif len(segments) >= 3 and segments[2] == "participants":
            endpoint = f"participants.{update_action(default_get='list')}"
        elif len(segments) >= 2:
            endpoint = f"deals.{update_action()}"
        else:
            endpoint = f"deals.{update_action(default_get='list')}"
    elif entity == "leads":
        if len(segments) >= 4 and segments[2] == "convert" and segments[3] == "deal":
            endpoint = "leads.convert"
        elif len(segments) >= 2:
            endpoint = f"leads.{update_action()}"
        else:
            endpoint = f"leads.{update_action(default_get='list')}"
    else:
        endpoint = f"{entity}.{update_action(default_get='list')}"

    if endpoint.endswith(".search"):
        category = "search"
    elif endpoint.startswith("participants."):
        category = "participants"
    elif endpoint.endswith((".update", ".create", ".convert", ".delete")):
        category = "updates"
    elif endpoint.startswith("persons."):
        category = "persons"
    elif endpoint.startswith("deals."):
        category = "deals"
    elif endpoint.startswith("leads."):
        category = "leads"
    else:
        category = entity

    return endpoint, category


@dataclass
class SyncAudit:
    source: str
    received_at: str
    loan_id: Optional[str] = None
    message_id: Optional[str] = None
    organization_id: Optional[str] = None
    action_id: Optional[str] = None
    batch_index: Optional[int] = None
    batch_size: Optional[int] = None
    last_modified: Optional[str] = None
    result: str = "pending"
    reason: Optional[str] = None
    deal_id: Optional[int] = None
    salesforce_fetch_succeeded: bool = False
    pipedrive_calls_total: int = 0
    pipedrive_calls_by_category: Dict[str, int] = field(default_factory=dict)
    pipedrive_calls_by_endpoint: Dict[str, int] = field(default_factory=dict)
    pipedrive_status_codes: Dict[str, int] = field(default_factory=dict)

    def mark_salesforce_fetch(self, *, last_modified: Optional[str] = None) -> None:
        self.salesforce_fetch_succeeded = True
        if last_modified:
            self.last_modified = str(last_modified)

    def record_pipedrive_call(self, method: str, url: str, status_code: Optional[int]) -> None:
        endpoint, category = _classify_pipedrive_request(method, url)
        self.pipedrive_calls_total += 1
        self.pipedrive_calls_by_endpoint[endpoint] = self.pipedrive_calls_by_endpoint.get(endpoint, 0) + 1
        self.pipedrive_calls_by_category[category] = self.pipedrive_calls_by_category.get(category, 0) + 1
        if status_code is not None:
            code_key = str(status_code)
            self.pipedrive_status_codes[code_key] = self.pipedrive_status_codes.get(code_key, 0) + 1

    def finish(self, result: str, *, reason: Optional[str] = None, deal_id: Optional[int] = None) -> None:
        self.result = result
        if reason is not None:
            self.reason = reason
        if deal_id is not None:
            self.deal_id = int(deal_id)

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "received_at": self.received_at,
            "loan_id": self.loan_id,
            "message_id": self.message_id,
            "organization_id": self.organization_id,
            "action_id": self.action_id,
            "batch_index": self.batch_index,
            "batch_size": self.batch_size,
            "last_modified": self.last_modified,
            "result": self.result,
            "reason": self.reason,
            "deal_id": self.deal_id,
            "salesforce_fetch_succeeded": self.salesforce_fetch_succeeded,
            "pipedrive_calls_total": self.pipedrive_calls_total,
            "pipedrive_calls_by_category": dict(sorted(self.pipedrive_calls_by_category.items())),
            "pipedrive_calls_by_endpoint": dict(sorted(self.pipedrive_calls_by_endpoint.items())),
            "pipedrive_status_codes": dict(sorted(self.pipedrive_status_codes.items())),
        }


def _append_audit_record(record: SyncAudit) -> None:
    log_path = _audit_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record.to_dict(), sort_keys=True)
    with _WRITE_LOCK:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")


@contextmanager
def sync_audit_context(
    *,
    source: str,
    loan_id: Optional[str],
    message_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    action_id: Optional[str] = None,
    batch_index: Optional[int] = None,
    batch_size: Optional[int] = None,
) -> Iterator[SyncAudit]:
    audit = SyncAudit(
        source=source,
        received_at=_utc_now_iso(),
        loan_id=loan_id,
        message_id=message_id,
        organization_id=organization_id,
        action_id=action_id,
        batch_index=batch_index,
        batch_size=batch_size,
    )
    token = _ACTIVE_AUDIT.set(audit)
    try:
        yield audit
    except Exception as exc:
        if audit.result == "pending":
            audit.finish("failed", reason=str(exc))
        raise
    finally:
        _ACTIVE_AUDIT.reset(token)
        if audit.result == "pending":
            audit.finish("unknown")
        _append_audit_record(audit)


def install_pipedrive_request_instrumentation() -> None:
    global _PATCH_INSTALLED
    if _PATCH_INSTALLED:
        return

    with _PATCH_LOCK:
        if _PATCH_INSTALLED:
            return

        if getattr(requests.sessions.Session.request, "_salesforce_sync_instrumented", False):
            _PATCH_INSTALLED = True
            return

        def instrumented_request(session, method, url, **kwargs):
            active_audit = _ACTIVE_AUDIT.get()
            if active_audit is None or not isinstance(url, str) or not _is_pipedrive_url(url):
                return _ORIGINAL_SESSION_REQUEST(session, method, url, **kwargs)

            response = _ORIGINAL_SESSION_REQUEST(session, method, url, **kwargs)
            active_audit.record_pipedrive_call(method, url, getattr(response, "status_code", None))
            return response

        instrumented_request._salesforce_sync_instrumented = True  # type: ignore[attr-defined]
        requests.sessions.Session.request = instrumented_request
        _PATCH_INSTALLED = True
        logger.debug("Installed Pipedrive request instrumentation for Salesforce syncs")
