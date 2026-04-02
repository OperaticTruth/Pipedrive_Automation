"""
Salesforce Outbound Message Listener

Handles Salesforce Outbound Message SOAP payloads and reuses the existing
Salesforce → Pipedrive sync logic.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from .salesforce_client import SalesforceClient
from .sync_deal import sync_deal_from_loan

logger = logging.getLogger(__name__)

SOAP_RESPONSE = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\">
  <soapenv:Body>
    <notificationsResponse xmlns=\"http://soap.sforce.com/2005/09/outbound\">
      <Ack>true</Ack>
    </notificationsResponse>
  </soapenv:Body>
</soapenv:Envelope>
"""


class OutboundMessageError(Exception):
    """Raised when the Salesforce Outbound Message payload is invalid."""


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _find_first(element: ET.Element, name: str) -> Optional[ET.Element]:
    for child in element.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _find_children(element: ET.Element, name: str) -> List[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _loan_matches_filter(sf_client: SalesforceClient, loan: Dict[str, Any]) -> bool:
    loan_officer = loan.get(sf_client.loan_officer_field)

    if sf_client.loan_officer_user_id:
        if isinstance(loan_officer, dict):
            return loan_officer.get("Id") == sf_client.loan_officer_user_id
        return loan_officer == sf_client.loan_officer_user_id

    if isinstance(loan_officer, dict):
        return loan_officer.get("Name") == sf_client.loan_officer_filter
    return loan_officer == sf_client.loan_officer_filter


def _borrower_missing(sf_client: SalesforceClient, loan: Dict[str, Any]) -> bool:
    borrower_relationship = sf_client.primary_borrower_field.replace("__c", "__r")
    borrower_id = loan.get(sf_client.primary_borrower_field)
    borrower_record = loan.get(borrower_relationship)
    return not borrower_id and not isinstance(borrower_record, dict)


def parse_outbound_message(xml_payload: bytes) -> Dict[str, Any]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as exc:
        raise OutboundMessageError(f"Invalid XML payload: {exc}") from exc

    notifications = _find_first(root, "notifications")
    if notifications is None:
        raise OutboundMessageError("SOAP payload missing notifications element")

    organization_id = _text(_find_first(notifications, "OrganizationId").text if _find_first(notifications, "OrganizationId") is not None else None)
    action_id = _text(_find_first(notifications, "ActionId").text if _find_first(notifications, "ActionId") is not None else None)
    notification_nodes = _find_children(notifications, "Notification")

    parsed_notifications: List[Dict[str, Optional[str]]] = []
    for notification in notification_nodes:
        message_id = _text(_find_first(notification, "Id").text if _find_first(notification, "Id") is not None else None)
        sobject = _find_first(notification, "sObject")

        if sobject is None:
            parsed_notifications.append({
                "message_id": message_id or None,
                "object_id": None,
                "object_type": None,
            })
            continue

        object_id = None
        for child in sobject:
            if _local_name(child.tag) == "Id":
                object_id = _text(child.text) or None
                break

        xsi_type = None
        for attr_name, attr_value in sobject.attrib.items():
            if _local_name(attr_name) == "type":
                xsi_type = _text(attr_value) or None
                break

        parsed_notifications.append({
            "message_id": message_id or None,
            "object_id": object_id,
            "object_type": xsi_type,
        })

    return {
        "organization_id": organization_id or None,
        "action_id": action_id or None,
        "notifications": parsed_notifications,
    }


def handle_outbound_message(xml_payload: bytes) -> Dict[str, Any]:
    parsed = parse_outbound_message(xml_payload)
    notifications = parsed.get("notifications", [])

    if not notifications:
        return {
            "success": False,
            "error": "No notifications found in outbound message payload",
            "synced": 0,
            "skipped": 0,
            "failed": 0,
        }

    sf_client = SalesforceClient()
    results: List[Dict[str, Any]] = []
    synced = 0
    skipped = 0
    failed = 0

    for notification in notifications:
        loan_id = notification.get("object_id")
        message_id = notification.get("message_id")

        if not loan_id:
            skipped += 1
            results.append({
                "message_id": message_id,
                "success": False,
                "skipped": True,
                "reason": "Missing Salesforce object ID in SOAP payload",
            })
            continue

        try:
            loan = sf_client.get_loan_by_id(loan_id)
        except Exception as exc:
            failed += 1
            logger.error("Failed to fetch Salesforce loan %s from outbound message: %s", loan_id, exc, exc_info=True)
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "success": False,
                "retryable": True,
                "error": str(exc),
            })
            continue

        if not loan:
            skipped += 1
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "success": False,
                "skipped": True,
                "reason": "Loan not found in Salesforce",
            })
            continue

        if not _loan_matches_filter(sf_client, loan):
            skipped += 1
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "success": True,
                "skipped": True,
                "reason": "Loan Officer filter",
            })
            continue

        if _borrower_missing(sf_client, loan):
            skipped += 1
            logger.warning("Skipping Salesforce loan %s because borrower lookup is missing", loan_id)
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "success": False,
                "skipped": True,
                "reason": "Primary borrower lookup missing on Salesforce loan",
            })
            continue

        try:
            deal_id = sync_deal_from_loan(loan)
        except Exception as exc:
            failed += 1
            logger.error("Unexpected sync error for Salesforce loan %s: %s", loan_id, exc, exc_info=True)
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "success": False,
                "retryable": True,
                "error": str(exc),
            })
            continue

        if deal_id:
            synced += 1
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "deal_id": deal_id,
                "success": True,
                "synced": True,
            })
        else:
            skipped += 1
            results.append({
                "message_id": message_id,
                "loan_id": loan_id,
                "success": False,
                "skipped": True,
                "reason": "Sync returned None",
            })

    return {
        "success": failed == 0,
        "synced": synced,
        "skipped": skipped,
        "failed": failed,
        "total": len(notifications),
        "organization_id": parsed.get("organization_id"),
        "action_id": parsed.get("action_id"),
        "results": results,
    }


def build_outbound_message_ack() -> str:
    return SOAP_RESPONSE
