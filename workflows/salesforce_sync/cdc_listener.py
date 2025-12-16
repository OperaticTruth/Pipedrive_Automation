"""
Change Data Capture (CDC) Listener

Handles real-time sync via Salesforce Change Data Capture events.
"""

import logging
from typing import Dict, Any
from .salesforce_client import SalesforceClient
from .sync_deal import sync_deal_from_loan

logger = logging.getLogger(__name__)


def handle_cdc_event(event_data: Dict[str, Any]) -> dict:
    """
    Handle a Change Data Capture event from Salesforce.
    
    This function processes CDC events for Loan object changes and syncs
    them to Pipedrive if they match the Loan Officer filter.
    
    Args:
        event_data: CDC event payload from Salesforce
        
    Returns:
        Dictionary with processing result
    """
    # CDC events have this structure:
    # {
    #   "data": {
    #     "schema": "...",
    #     "payload": {
    #       "ChangeEventHeader": {
    #         "entityName": "Loan__c",
    #         "changeType": "CREATE" | "UPDATE" | "DELETE",
    #         "recordIds": ["a0X..."],
    #         "commitTimestamp": 1234567890,
    #         "commitUser": "005..."
    #       },
    #       "Id": "a0X...",
    #       "Loan_Officer__c": "Jake Elmendorf",
    #       ...
    #     }
    #   }
    # }
    
    try:
        logger.info(f"Received CDC event: {event_data}")
        # Extract payload
        payload = event_data.get("data", {}).get("payload", {})
        if not payload:
            logger.warning("CDC event missing payload")
            return {"success": False, "error": "Missing payload"}
        
        # Extract change event header
        header = payload.get("ChangeEventHeader", {})
        entity_name = header.get("entityName")
        change_type = header.get("changeType")
        record_ids = header.get("recordIds", [])
        
        # Only process Loan object events
        sf_client = SalesforceClient()
        if entity_name != sf_client.loan_object:
            logger.debug(f"Ignoring CDC event for {entity_name} (not {sf_client.loan_object})")
            return {"success": True, "skipped": True, "reason": "Wrong object type"}
        
        # Handle DELETE events
        if change_type == "DELETE":
            logger.info(f"DELETE event for Loan {record_ids[0]} - skipping (deletion not implemented)")
            return {"success": True, "skipped": True, "reason": "DELETE not implemented"}
        
        # For CREATE/UPDATE, fetch the full record
        if not record_ids:
            logger.warning("CDC event missing record IDs")
            return {"success": False, "error": "Missing record IDs"}
        
        loan_id = record_ids[0]
        
        # Check if this loan matches our Loan Officer filter
        # We need to fetch the full record to check the Loan Officer field
        loan = sf_client.get_loan_by_id(loan_id)
        if not loan:
            logger.warning(f"Could not fetch Loan {loan_id} from Salesforce")
            return {"success": False, "error": f"Loan {loan_id} not found"}
        
        # Check Loan Officer filter
        loan_officer = loan.get(sf_client.loan_officer_field)
        matches_filter = False
        
        if sf_client.loan_officer_user_id:
            # Compare with User ID
            if isinstance(loan_officer, dict):
                matches_filter = loan_officer.get("Id") == sf_client.loan_officer_user_id
            else:
                matches_filter = loan_officer == sf_client.loan_officer_user_id
        else:
            # Compare with name
            if isinstance(loan_officer, dict):
                matches_filter = loan_officer.get("Name") == sf_client.loan_officer_filter
            else:
                matches_filter = loan_officer == sf_client.loan_officer_filter
        
        if not matches_filter:
            logger.debug(f"Loan {loan_id} does not match Loan Officer filter, skipping")
            return {"success": True, "skipped": True, "reason": "Loan Officer filter"}
        
        # Check if status is Cancelled - don't sync cancelled loans
        status = loan.get("MtgPlanner_CRM__Status__c", "")
        if status == "Cancelled":
            logger.info(f"Loan {loan_id} is Cancelled - skipping sync")
            return {"success": True, "skipped": True, "reason": "Cancelled status"}
        
        # Sync the loan
        logger.info(f"Processing {change_type} event for Loan {loan_id} (Loan Officer: {loan_officer}, Status: {status})")
        deal_id = sync_deal_from_loan(loan)
        
        if deal_id:
            return {
                "success": True,
                "synced": True,
                "loan_id": loan_id,
                "deal_id": deal_id,
                "change_type": change_type
            }
        else:
            return {
                "success": False,
                "error": "Sync returned None",
                "loan_id": loan_id
            }
            
    except Exception as e:
        logger.error(f"Error processing CDC event: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def verify_cdc_webhook_signature(request_data: bytes, signature: str, secret: str) -> bool:
    """
    Verify the signature of a CDC webhook request.
    
    Salesforce CDC webhooks can include a signature for verification.
    This is a placeholder - implement based on Salesforce's signature method.
    
    Args:
        request_data: Raw request body
        signature: Signature from request headers
        secret: Shared secret for verification
        
    Returns:
        True if signature is valid, False otherwise
    """
    # TODO: Implement signature verification based on Salesforce documentation
    # This typically involves HMAC-SHA256 or similar
    logger.warning("CDC webhook signature verification not implemented")
    return True  # For now, skip verification (not recommended for production)

