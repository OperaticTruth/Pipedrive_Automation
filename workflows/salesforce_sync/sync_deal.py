"""
Deal Sync Logic

Handles syncing Salesforce Loan records to Pipedrive Deals.
"""

import requests
import logging
from typing import Dict, Optional
from config import PIPEDRIVE_API_KEY
from .sync_person import sync_person_from_contact, sync_coborrower_from_loan
from .deal_mapping import get_deal_id_for_loan, store_deal_mapping

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pipedrive.com/v1"
BASE_URL_V2 = "https://api.pipedrive.com/v2"  # For leads conversion


def format_address_for_pipedrive(loan_data: Dict) -> Optional[str]:
    """
    Format address fields from Salesforce for Pipedrive Address field type.
    
    Pipedrive Address fields (with Google Maps autocomplete) may need:
    1. A formatted string that Google Maps can parse
    2. Or the base field key (without _formatted_address suffix)
    
    If Property Address contains "PREQUALIFICATION", skip it and just use city, state, postal.
    
    Args:
        loan_data: Dictionary with loan fields including address components
        
    Returns:
        Formatted address string or None
    """
    address = loan_data.get("MtgPlanner_CRM__Property_Address__c", "").strip()
    city = loan_data.get("MtgPlanner_CRM__Property_City__c", "").strip()
    state = loan_data.get("MtgPlanner_CRM__Property_State__c", "").strip()
    postal = loan_data.get("MtgPlanner_CRM__Property_Postal_Code__c", "").strip()
    
    # Build address parts
    parts = []
    
    # Skip address if it contains "PREQUALIFICATION"
    if address and "PREQUALIFICATION" not in address.upper():
        parts.append(address)
    
    if city:
        parts.append(city)
    
    # State and postal code together
    if state and postal:
        parts.append(f"{state} {postal}")
    elif state:
        parts.append(state)
    elif postal:
        parts.append(postal)
    
    if not parts:
        return None
    
    # Try simple format: "City, State ZIP, USA"
    # This is the most common format Google Maps accepts
    address_string = ", ".join(parts)
    if address_string and not address_string.endswith(", USA"):
        address_string += ", USA"
    
    return address_string


def format_deal_title(loan_data: Dict) -> str:
    """
    Format deal title as: "{BorrowerFullName} - Loan # {LoanNumber}"
    
    Args:
        loan_data: Dictionary with loan fields
        
    Returns:
        Formatted deal title
    """
    # Get borrower name from nested relationship
    borrower_relationship = "MtgPlanner_CRM__Borrower_Name__r"
    borrower = loan_data.get(borrower_relationship, {})
    borrower_name = borrower.get("Name", "") if isinstance(borrower, dict) else ""
    
    # Get loan number
    loan_number = loan_data.get("MtgPlanner_CRM__Loan_1st_TD__c", "")
    
    # Format title
    if borrower_name and loan_number:
        return f"{borrower_name} - Loan # {loan_number}"
    elif borrower_name:
        return f"{borrower_name} - Loan"
    elif loan_number:
        return f"Loan # {loan_number}"
    else:
        return loan_data.get("Name", "New Loan")


def map_salesforce_stage_to_pipedrive(salesforce_status: str) -> Optional[int]:
    """
    Map Salesforce loan status to Pipedrive stage ID.
    
    Mapping:
    - Application → Application In
    - Pre-Approved → Pre-Approved
    - GTR → Getting Things Rolling
    - In Process, Submitted, Cond. Approval, Approved, Suspended → Loan In Process
    - Clear to Close, Docs Out → Clear To Close
    - Closed → Clear To Close (and set status to won)
    - Cancelled → Cancelled (but don't sync - handled separately)
    
    Args:
        salesforce_status: Salesforce status value
        
    Returns:
        Pipedrive stage ID or None
    """
    import os
    from config import (
        APPLICATION_IN_STAGE_ID, PREAPPROVED_STAGE_ID, 
        GETTING_THINGS_ROLLING_STAGE_ID, IN_PROCESS_STAGE_ID, 
        CLEAR_TO_CLOSE_STAGE_ID
    )
    
    # Stage mapping based on requirements
    stage_mapping = {
        "Application": APPLICATION_IN_STAGE_ID,
        "Pre-Approved": PREAPPROVED_STAGE_ID,
        "GTR": GETTING_THINGS_ROLLING_STAGE_ID,
        "Getting Things Rolling": GETTING_THINGS_ROLLING_STAGE_ID,
        "In Process": IN_PROCESS_STAGE_ID,
        "Loan In Process": IN_PROCESS_STAGE_ID,
        "Submitted": IN_PROCESS_STAGE_ID,
        "Cond. Approval": IN_PROCESS_STAGE_ID,
        "Approved": IN_PROCESS_STAGE_ID,
        "Suspended": IN_PROCESS_STAGE_ID,
        "Clear to Close": CLEAR_TO_CLOSE_STAGE_ID,
        "Clear To Close": CLEAR_TO_CLOSE_STAGE_ID,
        "Docs Out": CLEAR_TO_CLOSE_STAGE_ID,
        "Closed": CLEAR_TO_CLOSE_STAGE_ID,  # Will also set status to won
    }
    
    # Try exact match first
    if salesforce_status in stage_mapping:
        return stage_mapping[salesforce_status]
    
    # Try case-insensitive match
    for sf_status, pd_stage_id in stage_mapping.items():
        if sf_status.lower() == salesforce_status.lower():
            return pd_stage_id
    
    logger.warning(f"No stage mapping found for Salesforce status: {salesforce_status}")
    return None


def map_salesforce_status_to_label(salesforce_status: str) -> Optional[int]:
    """
    Map Salesforce loan status to Pipedrive Deal label ID.
    
    Labels match exactly: Application, Pre-Approved, Getting Things Rolling, etc.
    
    Args:
        salesforce_status: Salesforce status value
        
    Returns:
        Pipedrive label option ID or None
    """
    import os
    from config import (
        LABEL_APPLICATION_ID, LABEL_PRE_APPROVED_ID, LABEL_GETTING_THINGS_ROLLING_ID,
        LABEL_IN_PROCESS_ID, LABEL_SUBMITTED_ID, LABEL_COND_APPROVAL_ID,
        LABEL_APPROVED_ID, LABEL_CLEAR_TO_CLOSE_ID, LABEL_DOCS_OUT_ID,
        LABEL_CLOSED_ID, LABEL_SUSPENDED_ID, LABEL_CANCELLED_ID
    )
    
    # Label mapping - exact match to Salesforce status values
    label_mapping = {
        "Application": LABEL_APPLICATION_ID,
        "Pre-Approved": LABEL_PRE_APPROVED_ID,
        "GTR": LABEL_GETTING_THINGS_ROLLING_ID,
        "Getting Things Rolling": LABEL_GETTING_THINGS_ROLLING_ID,
        "In Process": LABEL_IN_PROCESS_ID,
        "Loan In Process": LABEL_IN_PROCESS_ID,
        "Submitted": LABEL_SUBMITTED_ID,
        "Cond. Approval": LABEL_COND_APPROVAL_ID,
        "Approved": LABEL_APPROVED_ID,
        "Clear to Close": LABEL_CLEAR_TO_CLOSE_ID,
        "Clear To Close": LABEL_CLEAR_TO_CLOSE_ID,
        "Docs Out": LABEL_DOCS_OUT_ID,
        "Closed": LABEL_CLOSED_ID,
        "Suspended": LABEL_SUSPENDED_ID,
        "Cancelled": LABEL_CANCELLED_ID,
    }
    
    # Try exact match first
    if salesforce_status in label_mapping:
        return label_mapping[salesforce_status]
    
    # Try case-insensitive match
    for sf_status, label_id in label_mapping.items():
        if sf_status.lower() == salesforce_status.lower():
            return label_id
    
    logger.warning(f"No label mapping found for Salesforce status: {salesforce_status}")
    return None


def find_active_lead_for_person(person_id: int) -> Optional[int]:
    """
    Find the first active Lead associated with a Person.
    
    Active leads are those that are:
    - Not "Cancelled"
    - Not "Applied"
    - Not archived
    
    Args:
        person_id: Pipedrive Person ID
        
    Returns:
        Lead ID if found, None otherwise
    """
    url = f"{BASE_URL}/leads"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "person_id": person_id,
        "status": "open"  # Only get non-archived leads
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        result = resp.json()
        
        # Handle different response structures
        if not result.get("success", True):
            logger.warning(f"Lead search returned success=False: {result}")
            return None
        
        data = result.get("data", [])
        if isinstance(data, dict):
            # Sometimes API returns {"data": {"items": [...]}}
            data = data.get("items", [])
        
        if not data:
            return None
        
        # Filter out "Cancelled" and "Applied" leads
        # Check the label field to determine status
        for lead in data:
            lead_id = lead.get("id")
            if not lead_id:
                continue
                
            label = lead.get("label")
            
            # Handle label - could be ID, dict with name, or None
            label_name = None
            if isinstance(label, dict):
                label_name = label.get("name", "")
            elif isinstance(label, (str, int)):
                # If it's an ID, we'd need to look it up, but for now skip
                # Most APIs return the label name directly
                label_name = str(label)
            
            # Skip if Cancelled or Applied
            if label_name and label_name.lower() in ["cancelled", "applied"]:
                logger.debug(f"Skipping Lead {lead_id} with label '{label_name}'")
                continue
            
            # Found an active lead - return the first one
            logger.info(f"Found active Lead {lead_id} for Person {person_id} (label: {label_name})")
            return lead_id
        
        return None
        
    except Exception as e:
        logger.error(f"Error searching for active lead: {e}")
        # If the leads endpoint doesn't exist or has different structure, return None
        # This allows the sync to continue and create a new deal
        return None


def convert_lead_to_deal(lead_id: int, loan_data: Dict, person_id: int) -> Optional[int]:
    """
    Convert a Lead to a Deal using Pipedrive's conversion API.
    
    Args:
        lead_id: Pipedrive Lead ID to convert
        loan_data: Dictionary with loan fields (for initial deal data)
        person_id: Pipedrive Person ID
        
    Returns:
        Created Deal ID or None
    """
    # Try v2 API first (newer endpoint - POST /api/v2/leads/{id}/convert/deal)
    url = f"{BASE_URL_V2}/leads/{lead_id}/convert/deal"
    params = {
        "api_token": PIPEDRIVE_API_KEY
    }
    
    # Prepare conversion data
    # Format deal title
    title = format_deal_title(loan_data)
    
    # Get initial stage (Application In)
    from config import APPLICATION_IN_STAGE_ID
    stage_id = APPLICATION_IN_STAGE_ID
    
    conversion_data = {
        "title": title,
        "person_id": person_id,
    }
    
    if stage_id:
        conversion_data["stage_id"] = stage_id
    
    # Get loan amount
    # Total Loan Amount is now: MtgPlanner_CRM__Loan_Amount_1st_TD__c
    total_amount = loan_data.get("MtgPlanner_CRM__Loan_Amount_1st_TD__c") or 0
    if total_amount:
        conversion_data["value"] = float(total_amount)
    
    try:
        resp = requests.post(url, params=params, json=conversion_data)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("success"):
            deal_id = result.get("data", {}).get("id")
            logger.info(f"Converted Lead {lead_id} to Deal {deal_id} using v2 API")
            return deal_id
        else:
            logger.warning(f"v2 API returned success=False: {result}")
            # Fall through to fallback approach
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.warning(f"v2 API endpoint not found (404) - Lead conversion may not be available in your Pipedrive plan")
        else:
            logger.warning(f"v2 API error: {e}")
        # Fall through to fallback approach
    except Exception as e:
        logger.warning(f"v2 API error: {e}")
        # Fall through to fallback approach
    
    # Fallback: Create deal manually and mark lead as "Applied"
    # This approach creates a new deal and updates the lead status
    logger.info(f"Using fallback: creating Deal from Lead {lead_id} data")
    try:
        # Create deal from loan data
        deal_id = create_deal(loan_data, person_id, loan_data.get("Id"))
        
        if deal_id:
            # Try to update lead to mark as "Applied"
            # Note: This requires finding the "Applied" label ID
            # For now, we'll just log - you can manually mark as Applied if needed
            logger.info(f"Created Deal {deal_id} from Lead {lead_id} data. Please mark Lead {lead_id} as 'Applied' manually if needed.")
            return deal_id
        
        return None
        
    except Exception as e:
        logger.error(f"Error in fallback lead conversion: {e}")
        return None


def is_deal_archived_or_lost(deal_id: int) -> bool:
    """
    Check if a deal is archived or has status = lost.
    
    Note: If a deal is archived, the standard /deals/{id} endpoint might not work.
    We check the active field and status field.
    
    Args:
        deal_id: Pipedrive Deal ID
        
    Returns:
        True if deal is archived or lost, False otherwise
    """
    url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        result = resp.json()
        
        if not result.get("success"):
            # If the endpoint fails, it might be archived - check archived endpoint
            logger.debug(f"Standard endpoint failed for deal {deal_id}, checking if archived")
            return _check_if_deal_is_archived(deal_id)
        
        deal = result.get("data", {})
        
        # Check if archived
        if deal.get("active") == False:
            logger.debug(f"Deal {deal_id} is archived (active=False)")
            return True
        
        # Check if status is lost
        status = deal.get("status")
        if status == "lost":
            logger.debug(f"Deal {deal_id} is lost (status=lost)")
            return True
        
        return False
        
    except requests.exceptions.HTTPError as e:
        # If we get a 404 or other error, the deal might be archived
        if e.response.status_code == 404:
            logger.debug(f"Deal {deal_id} not found via standard endpoint (404) - checking archived")
            return _check_if_deal_is_archived(deal_id)
        logger.warning(f"Error checking deal {deal_id} status: {e}")
        return False
    except Exception as e:
        logger.warning(f"Error checking deal {deal_id} status: {e}")
        return False


def _check_if_deal_is_archived(deal_id: int) -> bool:
    """
    Check if a deal is in the archived deals list.
    
    Args:
        deal_id: Pipedrive Deal ID
        
    Returns:
        True if deal is found in archived list, False otherwise
    """
    try:
        archived_url = f"{BASE_URL_V2}/deals/archived"
        archived_params = {
            "api_token": PIPEDRIVE_API_KEY,
            "limit": 500
        }
        
        archived_resp = requests.get(archived_url, params=archived_params)
        archived_resp.raise_for_status()
        archived_result = archived_resp.json()
        
        archived_deals = archived_result.get("data", {}).get("items", [])
        if not isinstance(archived_deals, list):
            archived_deals = []
        
        # Check if this deal_id is in the archived list
        for deal in archived_deals:
            if isinstance(deal, dict) and deal.get("id") == deal_id:
                logger.debug(f"Deal {deal_id} found in archived deals list")
                return True
        
        return False
    except Exception as e:
        logger.warning(f"Error checking if deal {deal_id} is archived: {e}")
        return False


def find_deal_by_salesforce_id(salesforce_loan_id: str, include_archived: bool = True) -> Optional[int]:
    """
    Find a Pipedrive Deal by Salesforce Loan ID.
    
    Note: Pipedrive API excludes archived deals from standard endpoints.
    We check both active deals (via search) and archived deals (via archived endpoint).
    
    Args:
        salesforce_loan_id: Salesforce Loan ID
        include_archived: Whether to include archived deals in search
        
    Returns:
        Pipedrive Deal ID if found, None otherwise
    """
    import os
    from config import PIPEDRIVE_SALESFORCE_LOAN_ID_KEY
    
    loan_id_key = PIPEDRIVE_SALESFORCE_LOAN_ID_KEY
    if not loan_id_key:
        return None
    
    # Step 1: Search active deals by Salesforce Loan ID
    # Search API might include archived deals in results, so we check all results
    url = f"{BASE_URL}/deals/search"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "term": salesforce_loan_id,
        "fields": "custom_fields"
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        result = resp.json()
        data = result.get("data", {})
        
        # Handle different response structures
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        else:
            items = []
        
        logger.info(f"Search API returned {len(items)} results for Salesforce Loan ID {salesforce_loan_id}")
        
        # Check each result to see if it matches our custom field
        for item in items:
            # Handle different item structures
            if isinstance(item, dict) and "item" in item:
                deal = item.get("item", {})
            elif isinstance(item, dict):
                deal = item
            else:
                continue
                
            if not isinstance(deal, dict):
                continue
                
            deal_id = deal.get("id")
            if not deal_id:
                continue
            
            # Custom fields are at root level in Pipedrive API
            # Check if Salesforce Loan ID matches
            loan_id_value = deal.get(loan_id_key)
            if loan_id_value:
                # Handle dict or direct value
                if isinstance(loan_id_value, dict):
                    field_value = loan_id_value.get("value")
                else:
                    field_value = loan_id_value
                    
                if str(field_value) == str(salesforce_loan_id):
                    logger.info(f"Found existing Deal {deal_id} with Salesforce Loan ID {salesforce_loan_id} in search results")
                    return deal_id
    except Exception as e:
        logger.warning(f"Error searching active deals by Salesforce ID: {e}")
    
    # Step 2: If including archived, try alternative methods
    # Note: The /api/v2/deals/archived endpoint may not be available on all plans
    # We'll try it but handle 404 gracefully and use fallback methods
    if include_archived:
        # Try v2 archived endpoint first
        try:
            archived_url = f"{BASE_URL_V2}/deals/archived"
            archived_params = {
                "api_token": PIPEDRIVE_API_KEY,
                "limit": 500
            }
            
            archived_resp = requests.get(archived_url, params=archived_params)
            archived_resp.raise_for_status()
            archived_result = archived_resp.json()
            
            archived_deals = archived_result.get("data", {}).get("items", [])
            if not isinstance(archived_deals, list):
                archived_deals = []
            
            logger.info(f"Checking {len(archived_deals)} archived deals for Salesforce Loan ID {salesforce_loan_id}")
            
            # Check each archived deal
            for deal in archived_deals:
                if not isinstance(deal, dict):
                    continue
                
                deal_id = deal.get("id")
                if not deal_id:
                    continue
                
                # Try to get custom fields from archived endpoint response
                loan_id_value = deal.get(loan_id_key)
                if not loan_id_value:
                    custom_fields = deal.get("custom_fields", {})
                    if isinstance(custom_fields, dict):
                        loan_id_value = custom_fields.get(loan_id_key)
                
                if loan_id_value:
                    if isinstance(loan_id_value, dict):
                        field_value = loan_id_value.get("value")
                    else:
                        field_value = loan_id_value
                    
                    if str(field_value) == str(salesforce_loan_id):
                        logger.info(f"Found existing archived Deal {deal_id} with Salesforce Loan ID {salesforce_loan_id}")
                        return deal_id
                    
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning("Archived deals endpoint not available (404) - this may not be supported on your Pipedrive plan")
            else:
                logger.warning(f"Error accessing archived deals endpoint: {e}")
        except Exception as e:
            logger.warning(f"Error searching archived deals: {e}")
        
        # Fallback: Try searching all deals with status filter (if supported)
        # This is a workaround since archived endpoint may not be available
        logger.info("Note: Cannot reliably check archived deals via API. If a deal was archived, a new deal may be created.")
    
    return None


def find_deal_by_loan_number(loan_number: str, person_id: int, include_archived: bool = True) -> Optional[int]:
    """
    Find a Pipedrive Deal by Loan Number and Person ID.
    
    This is useful when a Deal was manually created/converted from a Lead
    before the Salesforce sync ran, so it won't have the Salesforce Loan ID yet.
    
    Args:
        loan_number: Loan number from Salesforce
        person_id: Pipedrive Person ID to narrow the search
        include_archived: Whether to include archived deals in search
        
    Returns:
        Pipedrive Deal ID if found, None otherwise
    """
    from config import LOAN_NUMBER_KEY
    
    if not loan_number or not LOAN_NUMBER_KEY:
        return None
    
    # Alternative approach: Get deals for this person and check loan numbers
    # This is more reliable than search API
    url = f"{BASE_URL}/persons/{person_id}/deals"
    params = {
        "api_token": PIPEDRIVE_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        result = resp.json()
        
        if not result.get("success", True):
            logger.warning(f"Failed to get deals for person {person_id}: {result}")
            # Fall back to search method
            return _find_deal_by_loan_number_search(loan_number, person_id, include_archived)
        
        deals = result.get("data")
        if deals is None:
            deals = []
        if not isinstance(deals, list):
            deals = []
        
        logger.error(f"Checking {len(deals)} deals for person {person_id} with loan number {loan_number}")
        
        # Check each deal for matching loan number
        # Note: Need to fetch full deal to get custom fields (person deals endpoint doesn't return them)
        for deal in deals:
            if not isinstance(deal, dict):
                continue
                
            deal_id = deal.get("id")
            if not deal_id:
                continue
            
            # Fetch full deal to get custom fields
            deal_url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
            try:
                deal_resp = requests.get(deal_url)
                deal_resp.raise_for_status()
                deal_result = deal_resp.json()
                if deal_result.get("success"):
                    full_deal = deal_result.get("data", {})
                    custom_fields = full_deal.get("custom_fields", {})
                else:
                    continue
            except Exception as e:
                logger.warning(f"Failed to fetch deal {deal_id}: {e}")
                continue
            
            loan_number_field = custom_fields.get(LOAN_NUMBER_KEY)
            
            # Check custom field first
            if loan_number_field:
                field_value = loan_number_field.get("value") if isinstance(loan_number_field, dict) else loan_number_field
                if str(field_value) == str(loan_number):
                    # Check if archived/lost if we're not including archived
                    if include_archived or not is_deal_archived_or_lost(deal_id):
                        logger.info(f"Found existing Deal {deal_id} with Loan Number {loan_number} for Person {person_id}")
                        return deal_id
            
            # Fallback: Check deal title for loan number (format: "Name - Loan # 123456789")
            deal_title = full_deal.get("title", "")
            if deal_title and f"Loan # {loan_number}" in deal_title:
                # Check if archived/lost if we're not including archived
                if include_archived or not is_deal_archived_or_lost(deal_id):
                    logger.info(f"Found existing Deal {deal_id} by loan number in title '{deal_title}' for Person {person_id}")
                    return deal_id
        
        # If including archived, also check archived deals for this person
        if include_archived:
            try:
                # Get archived deals and filter by person_id
                archived_url = f"{BASE_URL_V2}/deals/archived"
                archived_params = {
                    "api_token": PIPEDRIVE_API_KEY,
                    "limit": 500
                }
                
                archived_resp = requests.get(archived_url, params=archived_params)
                archived_resp.raise_for_status()
                archived_result = archived_resp.json()
                
                archived_deals = archived_result.get("data", {}).get("items", [])
                if not isinstance(archived_deals, list):
                    archived_deals = []
                
                # Filter by person_id and check loan number
                for deal in archived_deals:
                    if not isinstance(deal, dict):
                        continue
                    
                    deal_person_id = deal.get("person_id")
                    if isinstance(deal_person_id, dict):
                        deal_person_id = deal_person_id.get("value")
                    
                    if deal_person_id and int(deal_person_id) == person_id:
                        deal_id = deal.get("id")
                        if not deal_id:
                            continue
                        
                        # Fetch full deal to get custom fields
                        deal_url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
                        try:
                            deal_resp = requests.get(deal_url)
                            deal_resp.raise_for_status()
                            deal_result = deal_resp.json()
                            if deal_result.get("success"):
                                full_deal = deal_result.get("data", {})
                                custom_fields = full_deal.get("custom_fields", {})
                                loan_number_field = custom_fields.get(LOAN_NUMBER_KEY) or full_deal.get(LOAN_NUMBER_KEY)
                                
                                if loan_number_field:
                                    field_value = loan_number_field.get("value") if isinstance(loan_number_field, dict) else loan_number_field
                                    if str(field_value) == str(loan_number):
                                        logger.info(f"Found existing archived Deal {deal_id} with Loan Number {loan_number} for Person {person_id}")
                                        return deal_id
                                
                                # Also check title
                                deal_title = full_deal.get("title", "")
                                if deal_title and f"Loan # {loan_number}" in deal_title:
                                    logger.info(f"Found existing archived Deal {deal_id} by loan number in title for Person {person_id}")
                                    return deal_id
                        except Exception as e:
                            logger.debug(f"Error fetching archived deal {deal_id}: {e}")
                            continue
            except Exception as e:
                logger.warning(f"Error checking archived deals for person {person_id}: {e}")
        
        logger.debug(f"No matching deal found for loan number {loan_number} and person {person_id}")
        return None
        
    except Exception as e:
        logger.warning(f"Error getting deals for person {person_id}: {e}, trying search method")
        return _find_deal_by_loan_number_search(loan_number, person_id, include_archived)


def _find_deal_by_loan_number_search(loan_number: str, person_id: int, include_archived: bool = True) -> Optional[int]:
    """
    Fallback method: Search for deals by loan number using search API.
    
    Args:
        loan_number: Loan number from Salesforce
        person_id: Pipedrive Person ID to narrow the search
        include_archived: Whether to include archived deals in search
    """
    from config import LOAN_NUMBER_KEY
    
    url = f"{BASE_URL}/deals/search"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "term": str(loan_number),
        "fields": "custom_fields"
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        result = resp.json()
        
        if not result.get("success", True):
            return None
        
        data = result.get("data", {})
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        else:
            items = []
        
        # Check each result
        for item in items:
            if not isinstance(item, dict):
                continue
                
            # Get deal from item
            deal = item.get("item") if "item" in item else item
            if not isinstance(deal, dict):
                continue
                
            deal_id = deal.get("id")
            if not deal_id:
                continue
            
            # Get person_id
            person_id_field = deal.get("person_id")
            deal_person_id = None
            if isinstance(person_id_field, dict):
                deal_person_id = person_id_field.get("value")
            elif isinstance(person_id_field, (int, str)):
                deal_person_id = person_id_field
            
            # Must match person
            if deal_person_id and int(deal_person_id) != person_id:
                continue
            
            # Check loan number
            custom_fields = deal.get("custom_fields", {})
            loan_number_field = custom_fields.get(LOAN_NUMBER_KEY)
            if loan_number_field:
                field_value = loan_number_field.get("value") if isinstance(loan_number_field, dict) else loan_number_field
                if str(field_value) == str(loan_number):
                    # Check if archived/lost if we're not including archived
                    if include_archived or not is_deal_archived_or_lost(deal_id):
                        logger.info(f"Found existing Deal {deal_id} with Loan Number {loan_number} (search method)")
                        return deal_id
                    else:
                        logger.info(f"Found Deal {deal_id} with Loan Number {loan_number} but it's archived/lost - skipping")
                        return None
        
        return None
        
    except Exception as e:
        logger.error(f"Error in search fallback: {e}")
        return None


def map_all_deal_fields(loan_data: Dict) -> Dict:
    """
    Map all Salesforce loan fields to Pipedrive Deal custom fields.
    
    Args:
        loan_data: Dictionary with loan fields from Salesforce
        
    Returns:
        Dictionary of Pipedrive field keys to values
    """
    import os
    from config import (
        BASE_LOAN_AMOUNT_KEY, PRE_APPROVAL_SENT_DATE_KEY, STRATEGY_CALL_KEY,
        LOAN_PAID_OFF_KEY, PROPERTY_TYPE_KEY, PROPERTY_ADDRESS_KEY,
        LOAN_TYPE_KEY, LOAN_PURPOSE_KEY, OCCUPANCY_KEY,
        APPRAISED_VALUE_KEY, PURCHASE_PRICE_KEY, DOWN_PAYMENT_KEY,
        INTEREST_RATE_KEY, TERM_KEY, FUNDING_FEE_KEY, CREDIT_SCORE_KEY,
        LOAN_PROGRAM_KEY, MONTHLY_PAYMENT_KEY, HOMEOWNERS_INSURANCE_KEY,
        PROPERTY_TAX_KEY, MORTGAGE_INSURANCE_KEY, HOA_KEY,
        SUPPLEMENTAL_PROPERTY_INSURANCE_KEY, B1_ANNUAL_INCOME_KEY, B2_ANNUAL_INCOME_KEY,
        ECONSENT_KEY, LE_DUE_KEY, LE_SENT_KEY, LE_RECEIVED_KEY,
        APPRAISAL_ORDERED_KEY, APPRAISAL_RECEIVED_KEY, TITLE_RECEIVED_KEY,
        INSURANCE_RECEIVED_KEY, CD_SENT_KEY, CD_RECEIVED_KEY,
        LOAN_NUMBER_KEY, PIPEDRIVE_SALESFORCE_LOAN_ID_KEY
    )
    
    field_mapping = {}
    
    # Helper to safely get value and format dates
    def get_value(sf_field, pd_key, format_date=False):
        value = loan_data.get(sf_field)
        if value is None:
            return None
        if format_date and isinstance(value, str) and 'T' in value:
            return value.split('T')[0]  # Extract date part
        return value
    
    # Basic loan fields
    if BASE_LOAN_AMOUNT_KEY:
        # Base Loan Amount is now: Base_Loan_Amount__c
        field_mapping[BASE_LOAN_AMOUNT_KEY] = get_value("Base_Loan_Amount__c", BASE_LOAN_AMOUNT_KEY)
    
    if PRE_APPROVAL_SENT_DATE_KEY:
        field_mapping[PRE_APPROVAL_SENT_DATE_KEY] = get_value("Pre_Approval_Sent__c", PRE_APPROVAL_SENT_DATE_KEY, format_date=True)
    
    if STRATEGY_CALL_KEY:
        field_mapping[STRATEGY_CALL_KEY] = get_value("Strategy_Call__c", STRATEGY_CALL_KEY, format_date=True)
    
    if LOAN_PAID_OFF_KEY:
        field_mapping[LOAN_PAID_OFF_KEY] = get_value("In_Process_or_Paid_Off__c", LOAN_PAID_OFF_KEY)
    
    # Property fields
    if PROPERTY_ADDRESS_KEY:
        address = format_address_for_pipedrive(loan_data)
        if address:
            # Pipedrive Address fields have subfields like _formatted_address
            # Use the base field key (remove _formatted_address suffix if present)
            base_key = PROPERTY_ADDRESS_KEY.replace("_formatted_address", "") if "_formatted_address" in PROPERTY_ADDRESS_KEY else PROPERTY_ADDRESS_KEY
            
            # Set the address using the base key
            field_mapping[base_key] = str(address)
            logger.info(f"Setting Property Address to base key '{base_key}': {address}")
            print(f"[ADDRESS] Setting Property Address to base key '{base_key}': '{address}'")
        else:
            # Log why address isn't being set
            sf_address = loan_data.get("MtgPlanner_CRM__Property_Address__c", "")
            city = loan_data.get("MtgPlanner_CRM__Property_City__c", "")
            state = loan_data.get("MtgPlanner_CRM__Property_State__c", "")
            postal = loan_data.get("MtgPlanner_CRM__Property_Postal_Code__c", "")
            logger.warning(f"No address to set - Address: '{sf_address}', City: '{city}', State: '{state}', Postal: '{postal}'")
            print(f"[ADDRESS DEBUG] No address - Address: '{sf_address}', City: '{city}', State: '{state}', Postal: '{postal}'")
    
    if PROPERTY_TYPE_KEY:
        field_mapping[PROPERTY_TYPE_KEY] = get_value("MtgPlanner_CRM__Property_Type__c", PROPERTY_TYPE_KEY)
    
    # Loan details
    if LOAN_TYPE_KEY:
        field_mapping[LOAN_TYPE_KEY] = get_value("MtgPlanner_CRM__Loan_Type_1st_TD__c", LOAN_TYPE_KEY)
    
    if LOAN_PURPOSE_KEY:
        field_mapping[LOAN_PURPOSE_KEY] = get_value("MtgPlanner_CRM__Loan_Purpose__c", LOAN_PURPOSE_KEY)
    
    if OCCUPANCY_KEY:
        # Map Salesforce occupancy values to Pipedrive option IDs
        sf_occupancy = loan_data.get("MtgPlanner_CRM__Occupancy__c")
        if sf_occupancy:
            from config import PRIMARY_OCCUPANCY_ID, SECOND_HOME_OCCUPANCY_ID, INVESTMENT_OCCUPANCY_ID
            # Map SF values to PD option IDs
            occupancy_mapping = {
                "Primary": PRIMARY_OCCUPANCY_ID if PRIMARY_OCCUPANCY_ID else "Primary",
                "PrimaryResidence": PRIMARY_OCCUPANCY_ID if PRIMARY_OCCUPANCY_ID else "Primary",
                "Secondary": SECOND_HOME_OCCUPANCY_ID if SECOND_HOME_OCCUPANCY_ID else "Second Home",
                "Investment": INVESTMENT_OCCUPANCY_ID if INVESTMENT_OCCUPANCY_ID else "Investment",
                "None": None,
            }
            # Try exact match first
            pd_occupancy = occupancy_mapping.get(sf_occupancy)
            if pd_occupancy is None:
                # Try case-insensitive
                for sf_val, pd_val in occupancy_mapping.items():
                    if sf_val.lower() == sf_occupancy.lower():
                        pd_occupancy = pd_val
                        break
            
            if pd_occupancy:
                field_mapping[OCCUPANCY_KEY] = pd_occupancy
    
    # Financial fields
    if APPRAISED_VALUE_KEY:
        field_mapping[APPRAISED_VALUE_KEY] = get_value("MtgPlanner_CRM__Appraised_Value__c", APPRAISED_VALUE_KEY)
    
    if PURCHASE_PRICE_KEY:
        field_mapping[PURCHASE_PRICE_KEY] = get_value("MtgPlanner_CRM__Purchase_Price__c", PURCHASE_PRICE_KEY)
    
    if DOWN_PAYMENT_KEY:
        # Down Payment is a dollar amount in SF, store as-is
        field_mapping[DOWN_PAYMENT_KEY] = get_value("MtgPlanner_CRM__Down_Payment__c", DOWN_PAYMENT_KEY)
    
    # Calculate Down Payment %: ((Purchase Price - Base Loan Amount) / Purchase Price) * 100
    from config import DOWN_PAYMENT_PERCENT_KEY
    if DOWN_PAYMENT_PERCENT_KEY:
        # Base Loan Amount is now: Base_Loan_Amount__c
        base_loan = loan_data.get("Base_Loan_Amount__c")
        purchase_price = loan_data.get("MtgPlanner_CRM__Purchase_Price__c")
        
        if base_loan and purchase_price:
            try:
                base_loan_float = float(base_loan)
                purchase_price_float = float(purchase_price)
                if purchase_price_float > 0:
                    # Down payment % = (Down Payment Amount / Purchase Price) * 100
                    # Or: ((Purchase Price - Base Loan) / Purchase Price) * 100
                    down_payment_percent = ((purchase_price_float - base_loan_float) / purchase_price_float) * 100
                    # Round to 2 decimal places, output as number (e.g., 5.0 for 5%, 3.5 for 3.5%)
                    field_mapping[DOWN_PAYMENT_PERCENT_KEY] = round(down_payment_percent, 2)
            except (ValueError, TypeError):
                pass  # Skip if values can't be converted to float
    
    if INTEREST_RATE_KEY:
        # Convert percent to decimal if needed (e.g., 3.5% → 3.5)
        rate = get_value("MtgPlanner_CRM__Rate_1st_TD__c", INTEREST_RATE_KEY)
        if rate is not None:
            field_mapping[INTEREST_RATE_KEY] = float(rate) if rate else None
    
    if TERM_KEY:
        field_mapping[TERM_KEY] = get_value("MtgPlanner_CRM__Term_1st_TD__c", TERM_KEY)
    
    if FUNDING_FEE_KEY:
        # Funding Fee is text in SF, should be currency - try to convert
        fee = get_value("Funding_Fee__c", FUNDING_FEE_KEY)
        if fee:
            try:
                # Try to extract number from text
                import re
                numbers = re.findall(r'\d+\.?\d*', str(fee))
                if numbers:
                    field_mapping[FUNDING_FEE_KEY] = float(numbers[0])
            except:
                field_mapping[FUNDING_FEE_KEY] = fee
    
    if CREDIT_SCORE_KEY:
        field_mapping[CREDIT_SCORE_KEY] = get_value("Middle_Credit_Score_Borrower__c", CREDIT_SCORE_KEY)
    
    if LOAN_PROGRAM_KEY:
        field_mapping[LOAN_PROGRAM_KEY] = get_value("MtgPlanner_CRM__Loan_Program_1st_TD__c", LOAN_PROGRAM_KEY)
    
    if MONTHLY_PAYMENT_KEY:
        # Monthly Payment is Total Monthly Payment: MtgPlanner_CRM__Monthly_Payment_1st_TD__c
        field_mapping[MONTHLY_PAYMENT_KEY] = get_value("MtgPlanner_CRM__Monthly_Payment_1st_TD__c", MONTHLY_PAYMENT_KEY)
    
    # P&I Payment: P_I_Payment__c
    from config import PI_PAYMENT_KEY
    if PI_PAYMENT_KEY:
        field_mapping[PI_PAYMENT_KEY] = get_value("P_I_Payment__c", PI_PAYMENT_KEY)
    
    if HOMEOWNERS_INSURANCE_KEY:
        field_mapping[HOMEOWNERS_INSURANCE_KEY] = get_value("MtgPlanner_CRM__Hazard_Ins_1st_TD__c", HOMEOWNERS_INSURANCE_KEY)
    
    # Supplemental Property Insurance: Supplemental_Property_Insurance__c
    from config import SUPPLEMENTAL_PROPERTY_INSURANCE_KEY
    if SUPPLEMENTAL_PROPERTY_INSURANCE_KEY:
        field_mapping[SUPPLEMENTAL_PROPERTY_INSURANCE_KEY] = get_value("Supplemental_Property_Insurance__c", SUPPLEMENTAL_PROPERTY_INSURANCE_KEY)
    
    if PROPERTY_TAX_KEY:
        field_mapping[PROPERTY_TAX_KEY] = get_value("MtgPlanner_CRM__Property_Tax_1st_TD__c", PROPERTY_TAX_KEY)
    
    if MORTGAGE_INSURANCE_KEY:
        field_mapping[MORTGAGE_INSURANCE_KEY] = get_value("MtgPlanner_CRM__Mortgage_Ins_1st_TD__c", MORTGAGE_INSURANCE_KEY)
    
    if HOA_KEY:
        field_mapping[HOA_KEY] = get_value("MtgPlanner_CRM__HOA_1st_TD__c", HOA_KEY)
    
    # Income fields (from Contact, but go to Deal)
    borrower_relationship = "MtgPlanner_CRM__Borrower_Name__r"
    borrower = loan_data.get(borrower_relationship, {})
    if isinstance(borrower, dict):
        if B1_ANNUAL_INCOME_KEY:
            field_mapping[B1_ANNUAL_INCOME_KEY] = borrower.get("MtgPlanner_CRM__Income_Borrower__c")
        if B2_ANNUAL_INCOME_KEY:
            field_mapping[B2_ANNUAL_INCOME_KEY] = borrower.get("MtgPlanner_CRM__Income_Co_Borrower__c")
    
    # Important Dates
    if ECONSENT_KEY:
        field_mapping[ECONSENT_KEY] = get_value("eConsent__c", ECONSENT_KEY, format_date=True)
    if LE_DUE_KEY:
        field_mapping[LE_DUE_KEY] = get_value("LE_Due__c", LE_DUE_KEY, format_date=True)
    if LE_SENT_KEY:
        field_mapping[LE_SENT_KEY] = get_value("LE_Sent__c", LE_SENT_KEY, format_date=True)
    if LE_RECEIVED_KEY:
        field_mapping[LE_RECEIVED_KEY] = get_value("LE_Received__c", LE_RECEIVED_KEY, format_date=True)
    if APPRAISAL_ORDERED_KEY:
        field_mapping[APPRAISAL_ORDERED_KEY] = get_value("Appraisal_Ordered__c", APPRAISAL_ORDERED_KEY, format_date=True)
    if APPRAISAL_RECEIVED_KEY:
        field_mapping[APPRAISAL_RECEIVED_KEY] = get_value("Appraisal_Received__c", APPRAISAL_RECEIVED_KEY, format_date=True)
    if TITLE_RECEIVED_KEY:
        field_mapping[TITLE_RECEIVED_KEY] = get_value("Title_Received__c", TITLE_RECEIVED_KEY, format_date=True)
    if INSURANCE_RECEIVED_KEY:
        field_mapping[INSURANCE_RECEIVED_KEY] = get_value("Insurance_Received__c", INSURANCE_RECEIVED_KEY, format_date=True)
    if CD_SENT_KEY:
        field_mapping[CD_SENT_KEY] = get_value("CD_Sent__c", CD_SENT_KEY, format_date=True)
    if CD_RECEIVED_KEY:
        field_mapping[CD_RECEIVED_KEY] = get_value("CD_Received__c", CD_RECEIVED_KEY, format_date=True)
    
    # Loan number
    if LOAN_NUMBER_KEY:
        field_mapping[LOAN_NUMBER_KEY] = get_value("MtgPlanner_CRM__Loan_1st_TD__c", LOAN_NUMBER_KEY)
    
    # Salesforce Loan ID (ensure it's always set as string)
    if PIPEDRIVE_SALESFORCE_LOAN_ID_KEY:
        sf_loan_id = loan_data.get("Id")
        if sf_loan_id:
            field_mapping[PIPEDRIVE_SALESFORCE_LOAN_ID_KEY] = str(sf_loan_id)
        else:
            logger.warning("Salesforce Loan ID is missing from loan_data")
    
    # Remove None values
    return {k: v for k, v in field_mapping.items() if v is not None}


def create_deal(loan_data: Dict, person_id: int, salesforce_loan_id: str) -> Optional[int]:
    """
    Create a new Deal in Pipedrive from Salesforce Loan data.
    
    Args:
        loan_data: Dictionary with Loan fields
        person_id: Pipedrive Person ID to link the deal to
        salesforce_loan_id: Salesforce Loan ID to store
        
    Returns:
        Created Deal ID or None
    """
    from config import (
        PIPEDRIVE_SALESFORCE_LOAN_ID_KEY, DEAL_LABEL_FIELD_KEY
    )
    
    # Format deal title
    title = format_deal_title(loan_data)
    
    # Get loan amount (Total Loan Amount)
    # Total Loan Amount is now: MtgPlanner_CRM__Loan_Amount_1st_TD__c
    total_amount = loan_data.get("MtgPlanner_CRM__Loan_Amount_1st_TD__c") or 0
    
    # Get status for stage and label mapping
    status = loan_data.get("MtgPlanner_CRM__Status__c", "")
    
    # Build deal data
    deal_data = {
        "title": title,
        "person_id": person_id,
        "value": float(total_amount) if total_amount else 0,
    }
    
    # Map stage
    stage_id = map_salesforce_stage_to_pipedrive(status)
    if stage_id:
        deal_data["stage_id"] = stage_id
    
    # Map label
    label_id = map_salesforce_status_to_label(status)
    if label_id and DEAL_LABEL_FIELD_KEY:
        deal_data[DEAL_LABEL_FIELD_KEY] = label_id
    
    # Add close date (Pipedrive standard field)
    close_date = loan_data.get("MtgPlanner_CRM__Est_Closing_Date__c")
    if close_date:
        if isinstance(close_date, str):
            deal_data["expected_close_date"] = close_date.split("T")[0]
        else:
            deal_data["expected_close_date"] = str(close_date)
    
    # Handle "Closed" status - set to won
    if status == "Closed":
        deal_data["status"] = "won"
    
    # Add all custom field mappings
    custom_fields = map_all_deal_fields(loan_data)
    deal_data.update(custom_fields)
    
    # Ensure Salesforce Loan ID is set
    if PIPEDRIVE_SALESFORCE_LOAN_ID_KEY and salesforce_loan_id:
        deal_data[PIPEDRIVE_SALESFORCE_LOAN_ID_KEY] = str(salesforce_loan_id)
    
    url = f"{BASE_URL}/deals?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        resp = requests.post(url, json=deal_data)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("success"):
            deal_id = result.get("data", {}).get("id")
            logger.info(f"Created Deal {deal_id} from Salesforce Loan {salesforce_loan_id}")
            
            # Store mapping for future reference (handles archived deals)
            if salesforce_loan_id:
                store_deal_mapping(salesforce_loan_id, deal_id)
            
            # Calculate commission after creating deal
            try:
                from workflows.commission import calculate_commission_for_deal
                commission = calculate_commission_for_deal(deal_id)
                if commission is not None:
                    logger.info(f"Calculated commission ${commission} for Deal {deal_id}")
            except Exception as e:
                logger.warning(f"Failed to calculate commission: {e}")
            
            return deal_id
        else:
            logger.error(f"Failed to create deal: {result}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating deal: {e}")
        return None


def update_deal(deal_id: int, loan_data: Dict, person_id: Optional[int], salesforce_loan_id: str) -> bool:
    """
    Update an existing Deal in Pipedrive with Salesforce Loan data.
    
    Args:
        deal_id: Pipedrive Deal ID
        loan_data: Dictionary with Loan fields
        person_id: Pipedrive Person ID (optional, only update if provided)
        salesforce_loan_id: Salesforce Loan ID (for verification)
        
    Returns:
        True if successful, False otherwise
    """
    from config import (
        PIPEDRIVE_SALESFORCE_LOAN_ID_KEY, DEAL_LABEL_FIELD_KEY
    )
    
    # Format deal title
    title = format_deal_title(loan_data)
    
    # Get loan amount
    # Total Loan Amount is now: MtgPlanner_CRM__Loan_Amount_1st_TD__c
    total_amount = loan_data.get("MtgPlanner_CRM__Loan_Amount_1st_TD__c")
    
    # Get status
    status = loan_data.get("MtgPlanner_CRM__Status__c", "")
    
    # Build update data
    update_data = {
        "title": title,
    }
    
    # Update value (Total Loan Amount → both Loan Amount field and Value field)
    # Value and Loan Amount should always be equal
    if total_amount is not None:
        total_amount_float = float(total_amount)
        update_data["value"] = total_amount_float
        # Also update Loan Amount custom field - must equal Value
        from config import LOAN_AMOUNT_KEY
        if LOAN_AMOUNT_KEY:
            update_data[LOAN_AMOUNT_KEY] = total_amount_float
    
    if person_id:
        update_data["person_id"] = person_id
    
    # Map stage
    stage_id = map_salesforce_stage_to_pipedrive(status)
    if stage_id:
        update_data["stage_id"] = stage_id
    
    # Map label
    label_id = map_salesforce_status_to_label(status)
    if label_id and DEAL_LABEL_FIELD_KEY:
        update_data[DEAL_LABEL_FIELD_KEY] = label_id
    
    # Add close date (Pipedrive standard field)
    close_date = loan_data.get("MtgPlanner_CRM__Est_Closing_Date__c")
    if close_date:
        if isinstance(close_date, str):
            update_data["expected_close_date"] = close_date.split("T")[0]
        else:
            update_data["expected_close_date"] = str(close_date)
    
    # Handle "Closed" status - set to won
    if status == "Closed":
        update_data["status"] = "won"
    
    # Handle "Cancelled" - don't update (per requirements)
    if status == "Cancelled":
        logger.info(f"Loan {salesforce_loan_id} is Cancelled - skipping update per requirements")
        return True  # Return success but don't actually update
    
    # Add all custom field mappings
    custom_fields = map_all_deal_fields(loan_data)
    update_data.update(custom_fields)
    
    # Ensure Salesforce Loan ID is set (always, even if updating existing deal)
    if PIPEDRIVE_SALESFORCE_LOAN_ID_KEY and salesforce_loan_id:
        update_data[PIPEDRIVE_SALESFORCE_LOAN_ID_KEY] = str(salesforce_loan_id)
        logger.info(f"Setting Salesforce Loan ID: {salesforce_loan_id} to field {PIPEDRIVE_SALESFORCE_LOAN_ID_KEY}")
    else:
        logger.warning(f"Salesforce Loan ID not set - key: {PIPEDRIVE_SALESFORCE_LOAN_ID_KEY}, id: {salesforce_loan_id}")
    
    # Debug: Log what we're sending
    from config import PROPERTY_ADDRESS_KEY
    logger.debug(f"Update data keys: {list(update_data.keys())}")
    if PROPERTY_ADDRESS_KEY:
        logger.debug(f"Property Address in update_data: {update_data.get(PROPERTY_ADDRESS_KEY)}")
    
    url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        resp = requests.put(url, json=update_data)
        
        # Check for errors before parsing JSON
        if resp.status_code != 200:
            error_body = resp.text
            logger.error(f"Failed to update Deal {deal_id}: {resp.status_code} {resp.reason}")
            logger.error(f"Error response: {error_body}")
            logger.error(f"Update data sent: {list(update_data.keys())}")
            # Log problematic fields that might cause issues
            for key, value in update_data.items():
                if value is None:
                    logger.debug(f"  {key}: None (might cause issues)")
                elif isinstance(value, (dict, list)) and len(str(value)) > 200:
                    logger.debug(f"  {key}: {type(value).__name__} (length: {len(str(value))})")
            resp.raise_for_status()
        
        result = resp.json()
        
        if result.get("success"):
            logger.info(f"Updated Deal {deal_id} from Salesforce Loan {salesforce_loan_id}")
            
            # Verify the update worked by fetching the deal
            # Note: Pipedrive API doesn't return custom_fields by default
            # We'll check the update response instead
            if result.get("data"):
                updated_data = result.get("data", {})
                logger.info(f"Deal update response: {updated_data.get('id')} updated successfully")
            
            # Calculate commission after updating deal
            try:
                from workflows.commission import calculate_commission_for_deal
                commission = calculate_commission_for_deal(deal_id)
                if commission is not None:
                    logger.info(f"Calculated commission ${commission} for Deal {deal_id}")
            except Exception as e:
                logger.warning(f"Failed to calculate commission: {e}")
            
            return True
        else:
            logger.error(f"Failed to update deal: {result}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating deal: {e}")
        return False


def sync_deal_from_loan(loan_data: Dict) -> Optional[int]:
    """
    Sync a Salesforce Loan to Pipedrive Deal (upsert).
    
    This function:
    1. Extracts Salesforce Loan ID
    2. Syncs the associated Contact to Person first
    3. Handles co-borrower if present
    4. Searches for existing Deal with that Loan ID
    5. Creates or updates Deal accordingly
    
    Args:
        loan_data: Dictionary containing Loan fields and nested Contact data
        
    Returns:
        Pipedrive Deal ID if successful, None otherwise
    """
    salesforce_loan_id = loan_data.get("Id")
    if not salesforce_loan_id:
        logger.error("No Salesforce Loan ID found in loan data")
        return None
    
    logger.error(f"=== STARTING SYNC for Loan {salesforce_loan_id} ===")
    logger.error(f"Loan Status: {loan_data.get('MtgPlanner_CRM__Status__c', 'N/A')}")
    logger.error(f"Loan Number: {loan_data.get('MtgPlanner_CRM__Loan_1st_TD__c', 'N/A')}")
    
    # Check if status is Cancelled - don't sync per requirements
    status = loan_data.get("MtgPlanner_CRM__Status__c", "")
    if status == "Cancelled":
        logger.info(f"Loan {salesforce_loan_id} is Cancelled - skipping sync per requirements")
        return None
    
    # First, sync the primary borrower Contact to Person
    contact_data = loan_data
    logger.info(f"Syncing person for loan {salesforce_loan_id}")
    person_id = sync_person_from_contact(contact_data)
    if not person_id:
        logger.error(f"Failed to sync Contact for Loan {salesforce_loan_id}")
        return None
    logger.info(f"Person synced/found: Person ID {person_id}")
    
    # Handle co-borrower if present
    coborrower_person_id = sync_coborrower_from_loan(loan_data)
    
    # Step 0: Check stored mapping first (handles archived deals)
    # This is our workaround since archived deals can't be queried via API
    logger.error(f"Step 0: Checking stored mapping for Salesforce Loan ID {salesforce_loan_id}")
    mapped_deal_id = get_deal_id_for_loan(salesforce_loan_id)
    if mapped_deal_id:
        logger.info(f"Found Deal {mapped_deal_id} in stored mapping for Loan {salesforce_loan_id}")
        # Try to fetch the deal to check if it exists and is active
        try:
            deal_url = f"{BASE_URL}/deals/{mapped_deal_id}?api_token={PIPEDRIVE_API_KEY}"
            deal_resp = requests.get(deal_url)
            deal_resp.raise_for_status()
            deal_result = deal_resp.json()
            
            if deal_result.get("success"):
                deal = deal_result.get("data", {})
                # Check if archived or lost
                if deal.get("active") == False or deal.get("status") == "lost":
                    logger.info(f"Deal {mapped_deal_id} from mapping is archived or lost - skipping sync for Loan {salesforce_loan_id}")
                    logger.info(f"SKIP: Deal {mapped_deal_id} is archived/lost - will NOT create duplicate")
                    return None
                
                # Deal exists and is active - update it
                logger.info(f"Found Deal {mapped_deal_id} from stored mapping - updating")
                update_deal(mapped_deal_id, loan_data, person_id, salesforce_loan_id)
                # Update co-borrower association if we have one
                if coborrower_person_id:
                    from config import COBORROWER_NAME_KEY
                    if COBORROWER_NAME_KEY:
                        try:
                            url = f"{BASE_URL}/deals/{mapped_deal_id}?api_token={PIPEDRIVE_API_KEY}"
                            resp = requests.put(url, json={COBORROWER_NAME_KEY: coborrower_person_id})
                            resp.raise_for_status()
                            logger.info(f"Updated co-borrower association for Deal {mapped_deal_id}")
                        except Exception as e:
                            logger.warning(f"Failed to update co-borrower: {e}")
                return mapped_deal_id
        except requests.exceptions.HTTPError as e:
            # If we get 404, the deal is likely archived (can't be fetched)
            if e.response.status_code == 404:
                logger.info(f"Deal {mapped_deal_id} from mapping not found (404 - likely archived) - skipping sync for Loan {salesforce_loan_id}")
                logger.info(f"SKIP: Deal {mapped_deal_id} is archived - will NOT create duplicate")
                return None
            # Other errors - log but continue with normal search
            logger.warning(f"Error fetching deal {mapped_deal_id} from mapping: {e}")
        except Exception as e:
            logger.warning(f"Error checking mapped deal {mapped_deal_id}: {e}")
    else:
        logger.info(f"No stored mapping found for Salesforce Loan ID {salesforce_loan_id}")
    
    # Step 1: Check for existing deal by Salesforce Loan ID (already synced)
    # Include archived deals so we can check their status
    logger.error(f"Step 1: Searching for deal by Salesforce Loan ID {salesforce_loan_id}")
    existing_deal_id = find_deal_by_salesforce_id(salesforce_loan_id, include_archived=True)
    
    if existing_deal_id:
        logger.info(f"Step 1: FOUND existing Deal {existing_deal_id} by Salesforce Loan ID")
        # Store the mapping for future reference
        store_deal_mapping(salesforce_loan_id, existing_deal_id)
        
        # Check if deal is archived or lost - if so, skip syncing
        if is_deal_archived_or_lost(existing_deal_id):
            logger.info(f"Deal {existing_deal_id} is archived or lost - skipping sync")
            return None
        
        # Update existing deal
        update_deal(existing_deal_id, loan_data, person_id, salesforce_loan_id)
        
        # Update co-borrower association if we have one
        if coborrower_person_id:
            from config import COBORROWER_NAME_KEY
            if COBORROWER_NAME_KEY:
                try:
                    url = f"{BASE_URL}/deals/{existing_deal_id}?api_token={PIPEDRIVE_API_KEY}"
                    resp = requests.put(url, json={COBORROWER_NAME_KEY: coborrower_person_id})
                    resp.raise_for_status()
                    logger.info(f"Updated co-borrower association for Deal {existing_deal_id}")
                except Exception as e:
                    logger.warning(f"Failed to update co-borrower: {e}")
        
        return existing_deal_id
    else:
        logger.info(f"Step 1: No deal found by Salesforce Loan ID")
    
    # Step 2: Check for existing deal by Loan Number (most reliable unique ID)
    # This handles the case where a Lead was manually converted to a Deal
    # before the sync ran, so it won't have the Salesforce Loan ID yet
    # Also checks for archived deals since they won't show up in standard searches
    loan_number = loan_data.get("MtgPlanner_CRM__Loan_1st_TD__c")
    if loan_number:
        logger.error(f"Step 2: Checking for existing deal by Loan Number {loan_number} for Person {person_id}")
        
        # Search by loan number value directly - this should search custom fields
        # The search API might include archived deals in results
        try:
            from config import LOAN_NUMBER_KEY
            
            search_url = f"{BASE_URL}/deals/search"
            search_params = {
                "api_token": PIPEDRIVE_API_KEY,
                "term": str(loan_number),  # Search for the loan number value
                "fields": "custom_fields"  # Include custom fields in search
            }
            
            search_resp = requests.get(search_url, params=search_params)
            search_resp.raise_for_status()
            search_result = search_resp.json()
            search_data = search_result.get("data", {})
            
            if isinstance(search_data, list):
                search_items = search_data
            elif isinstance(search_data, dict):
                search_items = search_data.get("items", [])
            else:
                search_items = []
            
            logger.info(f"Search API returned {len(search_items)} results for loan number {loan_number}")
            
            # Check each search result for matching loan number in custom field
            for item in search_items:
                if isinstance(item, dict) and "item" in item:
                    deal = item.get("item", {})
                elif isinstance(item, dict):
                    deal = item
                else:
                    continue
                
                deal_id = deal.get("id")
                if not deal_id:
                    continue
                
                deal_person_id = deal.get("person_id")
                if isinstance(deal_person_id, dict):
                    deal_person_id = deal_person_id.get("value")
                
                # Must match person
                if not deal_person_id or int(deal_person_id) != person_id:
                    continue
                
                # Check loan number custom field
                if LOAN_NUMBER_KEY:
                    loan_number_field = deal.get(LOAN_NUMBER_KEY)
                    if loan_number_field:
                        if isinstance(loan_number_field, dict):
                            field_value = loan_number_field.get("value")
                        else:
                            field_value = loan_number_field
                        
                        if str(field_value) == str(loan_number):
                            # Found matching deal - store mapping first
                            store_deal_mapping(salesforce_loan_id, deal_id)
                            
                            # Check if archived/lost
                            logger.info(f"Found Deal {deal_id} with matching Loan Number {loan_number} in search results")
                            if is_deal_archived_or_lost(deal_id):
                                logger.info(f"Deal {deal_id} is archived or lost - skipping sync (mapping stored)")
                                return None
                            else:
                                logger.info(f"Found existing Deal {deal_id} by Loan Number {loan_number} - updating")
                                update_deal(deal_id, loan_data, person_id, salesforce_loan_id)
                                return deal_id
        except Exception as e:
            logger.warning(f"Error searching by loan number: {e}")
        
        # Fallback: Use the regular loan number search (checks person's deals)
        existing_deal_by_loan_number = find_deal_by_loan_number(loan_number, person_id, include_archived=True)
        
        if existing_deal_by_loan_number:
            # Store the mapping for future reference
            store_deal_mapping(salesforce_loan_id, existing_deal_by_loan_number)
            
            # Check if deal is archived or lost - if so, skip syncing
            if is_deal_archived_or_lost(existing_deal_by_loan_number):
                logger.info(f"Deal {existing_deal_by_loan_number} is archived or lost - skipping sync")
                return None
            
            logger.info(f"Found existing Deal {existing_deal_by_loan_number} by Loan Number {loan_number} - updating with Salesforce data")
            # Update the deal with all Salesforce data (including Salesforce Loan ID)
            update_deal(existing_deal_by_loan_number, loan_data, person_id, salesforce_loan_id)
            
            # Update co-borrower association if we have one
            if coborrower_person_id:
                from config import COBORROWER_NAME_KEY
                if COBORROWER_NAME_KEY:
                    try:
                        url = f"{BASE_URL}/deals/{existing_deal_by_loan_number}?api_token={PIPEDRIVE_API_KEY}"
                        resp = requests.put(url, json={COBORROWER_NAME_KEY: coborrower_person_id})
                        resp.raise_for_status()
                        logger.info(f"Updated co-borrower association for Deal {existing_deal_by_loan_number}")
                    except Exception as e:
                        logger.warning(f"Failed to update co-borrower: {e}")
            
            return existing_deal_by_loan_number
        else:
            logger.info(f"Step 2: No deal found by Loan Number {loan_number}")
    
    # Step 3: No existing deal found - check for active Lead to convert
    logger.info(f"Step 3: Checking for active Lead for Person {person_id}")
    active_lead_id = find_active_lead_for_person(person_id)
    
    if active_lead_id:
        logger.info(f"Step 3: Found active Lead {active_lead_id} - converting to Deal")
        deal_id = convert_lead_to_deal(active_lead_id, loan_data, person_id)
        
        if deal_id:
            # Update the newly created deal with all Salesforce data
            # (This will also calculate commission)
            update_deal(deal_id, loan_data, person_id, salesforce_loan_id)
            
            # Update co-borrower association if we have one
            if coborrower_person_id:
                from config import COBORROWER_NAME_KEY
                if COBORROWER_NAME_KEY:
                    try:
                        url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
                        resp = requests.put(url, json={COBORROWER_NAME_KEY: coborrower_person_id})
                        resp.raise_for_status()
                        logger.info(f"Added co-borrower association for Deal {deal_id}")
                    except Exception as e:
                        logger.warning(f"Failed to add co-borrower: {e}")
            
            return deal_id
        else:
            logger.warning(f"Failed to convert Lead {active_lead_id} - will create new Deal instead")
    else:
        logger.info(f"Step 3: No active Lead found for Person {person_id}")
    
    # Step 4: No active lead found - create new deal
    logger.warning(f"=== CREATING NEW DEAL for Loan {salesforce_loan_id} ===")
    logger.warning(f"Reason: No existing deal found via mapping, Salesforce ID search, or loan number search")
    logger.warning(f"Loan Number: {loan_data.get('MtgPlanner_CRM__Loan_1st_TD__c', 'N/A')}")
    logger.warning(f"Person ID: {person_id}")
    deal_id = create_deal(loan_data, person_id, salesforce_loan_id)
    
    # Update co-borrower association if we have one
    if deal_id and coborrower_person_id:
        from config import COBORROWER_NAME_KEY
        if COBORROWER_NAME_KEY:
            try:
                url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
                resp = requests.put(url, json={COBORROWER_NAME_KEY: coborrower_person_id})
                resp.raise_for_status()
                logger.info(f"Added co-borrower association for Deal {deal_id}")
            except Exception as e:
                logger.warning(f"Failed to add co-borrower: {e}")
    
    return deal_id
