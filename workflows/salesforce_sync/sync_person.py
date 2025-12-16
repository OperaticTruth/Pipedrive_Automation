"""
Person Sync Logic

Handles syncing Salesforce Contact records to Pipedrive Persons.
"""

import requests
import logging
from typing import Dict, Optional
from config import PIPEDRIVE_API_KEY, GROUP_KEY, CONTACT_GROUP_KEY, PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY, LEAD_GROUP_ID, BORROWER_GROUP_ID, CONTACT_TYPE_KEY, CONTACT_TYPE_CLIENT_ID, CONTACT_TYPE_BUSINESS_ID

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pipedrive.com/v1"


def find_person_by_email(email: str) -> Optional[int]:
    """
    Find a Pipedrive Person by email address.
    
    Args:
        email: Email address to search for
        
    Returns:
        Pipedrive Person ID if found, None otherwise
    """
    if not email:
        return None
    
    # Search for person by email
    url = f"{BASE_URL}/persons/search"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "term": email,
        "fields": "email"
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        result = resp.json()
        
        # Handle different response structures
        if not result.get("success", True):
            logger.warning(f"Person search returned success=False: {result}")
            return None
        
        data = result.get("data", {})
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        else:
            items = []
        
        # Check each result to see if email matches
        # Note: Search API doesn't always return email, so fetch full person record
        for item in items:
            # Handle different item structures
            if isinstance(item, dict) and "item" in item:
                person = item.get("item", {})
            elif isinstance(item, dict):
                person = item
            else:
                continue
                
            person_id = person.get("id")
            if not person_id:
                continue
            
            # Fetch full person record to get email (search API doesn't return it reliably)
            try:
                person_url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
                person_resp = requests.get(person_url)
                person_resp.raise_for_status()
                person_result = person_resp.json()
                if person_result.get("success"):
                    full_person = person_result.get("data", {})
                    person_emails = full_person.get("email", [])
                else:
                    person_emails = person.get("email", [])  # Fallback to search result
            except Exception as e:
                logger.warning(f"Failed to fetch person {person_id}: {e}")
                person_emails = person.get("email", [])  # Fallback to search result
            
            # Check if any email matches
            for email_obj in person_emails:
                email_value = None
                if isinstance(email_obj, dict):
                    email_value = email_obj.get("value", "")
                else:
                    email_value = str(email_obj)
                
                if email_value and email_value.lower() == email.lower():
                    logger.info(f"Found existing Person {person_id} with email {email}")
                    return person_id
        
        return None
        
    except Exception as e:
        logger.error(f"Error searching for person by email: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_person_by_salesforce_id(salesforce_contact_id: str) -> Optional[int]:
    """
    Find a Pipedrive Person by Salesforce Contact ID (for storing the ID).
    
    Args:
        salesforce_contact_id: Salesforce Contact ID
        
    Returns:
        Pipedrive Person ID if found, None otherwise
    """
    if not PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY or not salesforce_contact_id:
        return None
    
    # Search for person with matching Salesforce Contact ID
    url = f"{BASE_URL}/persons/search"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "term": salesforce_contact_id,
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
        
        # Check each result
        for item in items:
            # Handle different item structures
            if isinstance(item, dict) and "item" in item:
                person = item.get("item", {})
            elif isinstance(item, dict):
                person = item
            else:
                continue
                
            if not isinstance(person, dict):
                continue
                
            person_id = person.get("id")
            if not person_id:
                continue
            
            # Custom fields are at root level in Pipedrive API
            # Check if Salesforce Contact ID matches
            contact_id_value = person.get(PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY)
            if contact_id_value:
                # Handle dict or direct value
                if isinstance(contact_id_value, dict):
                    field_value = contact_id_value.get("value")
                else:
                    field_value = contact_id_value
                    
                if str(field_value) == str(salesforce_contact_id):
                    logger.info(f"Found existing Person {person_id} with Salesforce Contact ID {salesforce_contact_id}")
                    return person_id
        
        return None
        
    except Exception as e:
        logger.error(f"Error searching for person by Salesforce ID: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_person_groups(person_id: int) -> list:
    """
    Get current groups/labels for a person.
    
    Args:
        person_id: Pipedrive Person ID
        
    Returns:
        List of group IDs or names
    """
    # Use CONTACT_GROUP_KEY if available, otherwise GROUP_KEY
    group_key = CONTACT_GROUP_KEY or GROUP_KEY
    if not group_key:
        return []
    
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        result = resp.json()
        data = result.get("data", {})
        custom_fields = data.get("custom_fields", {})
        
        group_field = custom_fields.get(group_key)
        if not group_field:
            return []
        
        # Pipedrive returns groups as a list of IDs or comma-separated string
        if isinstance(group_field, list):
            return [str(g) for g in group_field]
        elif isinstance(group_field, str):
            return [g.strip() for g in group_field.split(",") if g.strip()]
        elif isinstance(group_field, dict):
            # Might be a dict with 'value' key
            value = group_field.get("value")
            if isinstance(value, list):
                return [str(g) for g in value]
            elif isinstance(value, str):
                return [g.strip() for g in value.split(",") if g.strip()]
        
        return []
        
    except Exception as e:
        logger.error(f"Error getting person groups: {e}")
        return []


def update_person_contact_type(person_id: int):
    """
    Update person Contact Type to "Client" unless it already contains "Business".
    
    This is for borrowers/co-borrowers on deals - they should be "Client" unless
    it's a business loan (rare case).
    
    Args:
        person_id: Pipedrive Person ID
    """
    if not CONTACT_TYPE_KEY or not CONTACT_TYPE_CLIENT_ID:
        return
    
    # Get current person to check existing Contact Type
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        result = resp.json()
        
        if not result.get("success"):
            return
        
        person_data = result.get("data", {})
        custom_fields = person_data.get("custom_fields", {})
        current_contact_type = custom_fields.get(CONTACT_TYPE_KEY)
        
        # Check if Contact Type already contains "Business"
        has_business = False
        if current_contact_type:
            # Handle different response structures
            if isinstance(current_contact_type, dict):
                type_value = current_contact_type.get("value")
            elif isinstance(current_contact_type, list) and current_contact_type:
                type_value = current_contact_type[0].get("value") if isinstance(current_contact_type[0], dict) else current_contact_type[0]
            else:
                type_value = current_contact_type
            
            # Check if it's Business (ID 89)
            if str(type_value) == str(CONTACT_TYPE_BUSINESS_ID):
                has_business = True
        
        # If it has Business, leave it alone
        if has_business:
            logger.debug(f"Person {person_id} already has Contact Type 'Business' - leaving unchanged")
            return
        
        # Otherwise, set to Client
        update_url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
        update_data = {
            CONTACT_TYPE_KEY: CONTACT_TYPE_CLIENT_ID
        }
        
        update_resp = requests.put(update_url, json=update_data)
        update_resp.raise_for_status()
        update_result = update_resp.json()
        
        if update_result.get("success"):
            logger.info(f"Updated Person {person_id} Contact Type to 'Client'")
        else:
            logger.warning(f"Failed to update Contact Type for Person {person_id}: {update_result}")
            
    except Exception as e:
        logger.warning(f"Error updating Contact Type for Person {person_id}: {e}")


def update_person_groups(person_id: int, remove_groups: list, add_groups: list):
    """
    Update person groups, removing and adding specific groups.
    
    Args:
        person_id: Pipedrive Person ID
        remove_groups: List of group names/IDs to remove (e.g., ["Lead"])
        add_groups: List of group names/IDs to add (e.g., ["Borrower"])
    """
    # Use CONTACT_GROUP_KEY if available, otherwise GROUP_KEY
    group_key = CONTACT_GROUP_KEY or GROUP_KEY
    if not group_key:
        return
    
    # Get current groups
    current_groups = get_person_groups(person_id)
    
    # Remove specified groups (by ID or name) - handle both IDs and names
    # Convert all to strings for comparison
    remove_str = [str(g) for g in remove_groups]
    updated_groups = [g for g in current_groups if str(g) not in remove_str]
    
    # Add new groups (avoid duplicates)
    existing_str = [str(g) for g in updated_groups]
    for group in add_groups:
        if str(group) not in existing_str:
            updated_groups.append(str(group))
    
    # Update person with new groups
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        # Pipedrive expects groups as comma-separated string or array
        # Try array first, fallback to string
        if len(updated_groups) == 0:
            update_data = {group_key: ""}
        else:
            # Try as array (Pipedrive might prefer this for multi-select)
            update_data = {group_key: updated_groups}
        
        resp = requests.put(url, json=update_data)
        resp.raise_for_status()
        logger.info(f"Updated groups for Person {person_id}: removed {remove_groups}, added {add_groups}")
    except Exception as e:
        logger.error(f"Error updating person groups: {e}")
        # Try fallback with comma-separated string
        try:
            update_data = {group_key: ",".join(updated_groups)}
            resp = requests.put(url, json=update_data)
            resp.raise_for_status()
            logger.info(f"Updated groups for Person {person_id} (using string format)")
        except Exception as e2:
            logger.error(f"Error updating person groups (fallback): {e2}")


def create_person(contact_data: Dict, salesforce_contact_id: str, email: str) -> Optional[int]:
    """
    Create a new Person in Pipedrive from Salesforce Contact data.
    
    Args:
        contact_data: Dictionary with Contact fields (Name, Email, Phone)
        salesforce_contact_id: Salesforce Contact ID to store
        email: Email address (for matching)
        
    Returns:
        Created Person ID or None
    """
    # Extract contact fields
    name = contact_data.get("Name")
    phone = contact_data.get("Phone")
    
    # Use email as name if name is missing
    if not name:
        name = email or "Unknown"
    
    # Build person data
    person_data = {
        "name": name,
    }
    
    if email:
        person_data["email"] = [{"value": email, "primary": True}]
    if phone:
        person_data["phone"] = [{"value": phone, "primary": True}]
    
    # Add Salesforce Contact ID to custom field
    if PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY and salesforce_contact_id:
        person_data[PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY] = str(salesforce_contact_id)
    
    # Add "Borrower" group (since this is coming from a loan sync)
    if GROUP_KEY:
        # Need to find the "Borrower" group ID - for now, we'll add it after creation
        # or you can provide the group ID in config
        pass
    
    url = f"{BASE_URL}/persons?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        resp = requests.post(url, json=person_data)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("success"):
            person_id = result.get("data", {}).get("id")
            logger.info(f"Created Person {person_id} from Salesforce Contact {salesforce_contact_id}")
            
            # Update groups: remove "Lead", add "Borrower" (since this is from a loan sync)
            # Use option IDs if available, otherwise use names
            remove_ids = [LEAD_GROUP_ID] if LEAD_GROUP_ID else ["Lead"]
            add_ids = [BORROWER_GROUP_ID] if BORROWER_GROUP_ID else ["Borrower"]
            update_person_groups(person_id, remove_groups=remove_ids, add_groups=add_ids)
            
            # Update Contact Type to "Client" (unless it's already "Business")
            update_person_contact_type(person_id)
            
            return person_id
        else:
            logger.error(f"Failed to create person: {result}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating person: {e}")
        return None


def update_person(person_id: int, contact_data: Dict, salesforce_contact_id: str, email: str, is_initial: bool = False) -> bool:
    """
    Update an existing Person in Pipedrive with Salesforce Contact data.
    
    Per requirements: Don't update contact info after initial creation, unless it's the initial sync.
    
    Args:
        person_id: Pipedrive Person ID
        contact_data: Dictionary with Contact fields
        salesforce_contact_id: Salesforce Contact ID (for verification)
        email: Email address
        is_initial: If True, update name/email/phone. If False, only update Salesforce ID.
        
    Returns:
        True if successful, False otherwise
    """
    update_data = {}
    
    # Only update contact info if this is initial creation
    if is_initial:
        name = contact_data.get("Name")
        phone = contact_data.get("Phone")
        
        if name:
            update_data["name"] = name
        if email:
            update_data["email"] = [{"value": email, "primary": True}]
        if phone:
            update_data["phone"] = [{"value": phone, "primary": True}]
    
    # Always ensure Salesforce Contact ID is set (even if updating existing person)
    if PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY and salesforce_contact_id:
        update_data[PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY] = str(salesforce_contact_id)
    
    # Update groups: remove "Lead", add "Borrower" (if this is from a loan sync)
    # Note: This requires group IDs - will need to be configured
    
    # Note: Contact Type will be updated separately after the main update
    
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    
    try:
        # Debug: Log what we're sending
        logger.debug(f"Updating Person {person_id} with data keys: {list(update_data.keys())}")
        if PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY:
            logger.debug(f"Salesforce Contact ID being set: {update_data.get(PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY)}")
        
        resp = requests.put(url, json=update_data)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("success"):
            logger.info(f"Updated Person {person_id} from Salesforce Contact {salesforce_contact_id}")
            
            # Verify the update worked
            verify_url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
            verify_resp = requests.get(verify_url)
            if verify_resp.status_code == 200:
                verify_data = verify_resp.json().get("data", {})
                verify_custom = verify_data.get("custom_fields", {})
                if PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY:
                    sf_id_after = verify_custom.get(PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY)
                    logger.info(f"Salesforce Contact ID after update: {sf_id_after}")
            
            # Update Contact Type to "Client" (unless it's already "Business")
            update_person_contact_type(person_id)
            
            return True
        else:
            logger.error(f"Failed to update person: {result}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating person: {e}")
        return False


def sync_person_from_contact(contact_data: Dict) -> Optional[int]:
    """
    Sync a Salesforce Contact to Pipedrive Person (upsert).
    
    Uses email as the unique identifier for matching.
    Per requirements: Don't update contact info after initial creation.
    
    Args:
        contact_data: Dictionary containing Contact fields
                     Can be direct Contact record or nested from Loan lookup
        
    Returns:
        Pipedrive Person ID if successful, None otherwise
    """
    import os
    primary_borrower_field = os.getenv("SALESFORCE_PRIMARY_BORROWER_FIELD", "MtgPlanner_CRM__Borrower_Name__c")
    
    # Extract Contact ID and fields - handle both direct and nested lookups
    salesforce_contact_id = None
    contact_fields = {}
    email = None
    
    # Check if this is a direct Contact record
    if "Id" in contact_data and contact_data.get("Name") and primary_borrower_field not in contact_data:
        # Direct contact record
        salesforce_contact_id = contact_data["Id"]
        contact_fields = {
            "Name": contact_data.get("Name"),
            "Email": contact_data.get("Email"),
            "Phone": contact_data.get("Phone"),
        }
        email = contact_data.get("Email")
    else:
        # Nested from Loan lookup - try different patterns
        borrower_relationship = primary_borrower_field.replace("__c", "__r")
        borrower_r = contact_data.get(borrower_relationship)
        
        if isinstance(borrower_r, dict) and borrower_r.get("Id"):
            salesforce_contact_id = borrower_r.get("Id")
            contact_fields = {
                "Name": borrower_r.get("Name"),
                "Email": borrower_r.get("Email"),
                "Phone": borrower_r.get("Phone"),
            }
            email = borrower_r.get("Email")
        else:
            logger.error(f"Could not extract Contact ID from data. Keys: {list(contact_data.keys())}")
            return None
    
    if not salesforce_contact_id:
        logger.error("No Salesforce Contact ID found in contact data")
        return None
    
    if not email:
        logger.warning(f"Contact {salesforce_contact_id} missing email - using name as fallback")
        email = contact_fields.get("Name", "unknown")
    
    # Find existing person by email (primary matching method)
    existing_person_id = find_person_by_email(email)
    
    # Also check by Salesforce Contact ID (in case email changed)
    existing_by_sf_id = find_person_by_salesforce_id(salesforce_contact_id)
    
    # Use the existing person if found by either method
    if existing_person_id:
        # Person found by email - update Salesforce ID if not set, but don't update contact info
        is_initial = not existing_by_sf_id  # Initial if Salesforce ID not already set
        update_person(existing_person_id, contact_fields, salesforce_contact_id, email, is_initial=is_initial)
        
        # Update groups: remove "Lead", add "Borrower" (since this is from a loan sync)
        # Use option IDs if available, otherwise use names
        remove_ids = [LEAD_GROUP_ID] if LEAD_GROUP_ID else ["Lead"]
        add_ids = [BORROWER_GROUP_ID] if BORROWER_GROUP_ID else ["Borrower"]
        update_person_groups(existing_person_id, remove_groups=remove_ids, add_groups=add_ids)
        
        return existing_person_id
    elif existing_by_sf_id:
        # Person found by Salesforce ID but different email - this shouldn't happen per requirements
        # But handle it gracefully
        logger.warning(f"Person found by Salesforce ID but email mismatch - updating email")
        update_person(existing_by_sf_id, contact_fields, salesforce_contact_id, email, is_initial=True)
        return existing_by_sf_id
    else:
        # Create new person
        return create_person(contact_fields, salesforce_contact_id, email)


def sync_coborrower_from_loan(loan_data: Dict) -> Optional[int]:
    """
    Sync co-borrower from loan data to Pipedrive Person.
    
    Creates or finds co-borrower person by email, then returns the person ID
    for association to the deal.
    
    Args:
        loan_data: Dictionary containing loan fields with co-borrower data
        
    Returns:
        Pipedrive Person ID if co-borrower exists, None otherwise
    """
    # Extract co-borrower fields from Contact relationship
    # Co-borrower fields are on the Contact object, accessed via Borrower_Name__r
    import os
    primary_borrower_field = os.getenv("SALESFORCE_PRIMARY_BORROWER_FIELD", "MtgPlanner_CRM__Borrower_Name__c")
    borrower_relationship = primary_borrower_field.replace("__c", "__r")
    borrower = loan_data.get(borrower_relationship, {})
    
    # Get co-borrower fields from the Contact relationship
    if isinstance(borrower, dict):
        co_first = borrower.get("MtgPlanner_CRM__Co_Borrower_First_Name__c", "").strip() if borrower.get("MtgPlanner_CRM__Co_Borrower_First_Name__c") else ""
        co_last = borrower.get("MtgPlanner_CRM__Co_Borrower_Last_Name__c", "").strip() if borrower.get("MtgPlanner_CRM__Co_Borrower_Last_Name__c") else ""
        co_email = borrower.get("MtgPlanner_CRM__Co_Borrower_Email__c", "").strip() if borrower.get("MtgPlanner_CRM__Co_Borrower_Email__c") else ""
        co_phone = borrower.get("Phone_Co_Borrower__c", "").strip() if borrower.get("Phone_Co_Borrower__c") else ""
        co_birthday = borrower.get("MtgPlanner_CRM__Birthdaycoborrower__c")
    else:
        co_first = ""
        co_last = ""
        co_email = ""
        co_phone = ""
        co_birthday = None
    
    # If no co-borrower email, there's no co-borrower
    if not co_email:
        return None
    
    # Combine first and last name
    co_name = f"{co_first} {co_last}".strip()
    if not co_name:
        co_name = co_email  # Use email as name if no name
    
    # Find existing person by email
    existing_person_id = find_person_by_email(co_email)
    
    if existing_person_id:
        # Update existing person with co-borrower data
        contact_fields = {
            "Name": co_name,
            "Email": co_email,
            "Phone": co_phone,
        }
        # Don't update contact info after initial (per requirements)
        # But ensure Salesforce Contact ID is set if we have it
        # Note: Co-borrower doesn't have a separate Contact ID in Salesforce
        # So we'll just ensure the person exists and is linked
        logger.info(f"Found existing co-borrower Person {existing_person_id} with email {co_email}")
        
        # Update Contact Type to "Client" (unless it's already "Business")
        update_person_contact_type(existing_person_id)
        
        return existing_person_id
    else:
        # Create new co-borrower person
        person_data = {
            "name": co_name,
            "email": [{"value": co_email, "primary": True}],
        }
        
        if co_phone:
            person_data["phone"] = [{"value": co_phone, "primary": True}]
        
        # Add birthday if available
        if co_birthday:
            from config import BIRTHDAY_KEY
            if BIRTHDAY_KEY:
                if isinstance(co_birthday, str) and 'T' in co_birthday:
                    person_data[BIRTHDAY_KEY] = co_birthday.split("T")[0]
                else:
                    person_data[BIRTHDAY_KEY] = str(co_birthday)
        
        url = f"{BASE_URL}/persons?api_token={PIPEDRIVE_API_KEY}"
        
        try:
            resp = requests.post(url, json=person_data)
            resp.raise_for_status()
            result = resp.json()
            
            if result.get("success"):
                person_id = result.get("data", {}).get("id")
                logger.info(f"Created co-borrower Person {person_id} with email {co_email}")
                
                # Update Contact Type to "Client" (unless it's already "Business")
                update_person_contact_type(person_id)
                
                return person_id
            else:
                logger.error(f"Failed to create co-borrower person: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating co-borrower person: {e}")
            return None
