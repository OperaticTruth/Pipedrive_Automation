import requests
from config import (
    PIPEDRIVE_API_KEY,
    CONTACT_LABEL_KEY,
    COBORROWER_KEY,
    APPLICATION_IN_STAGE_ID,
    PREAPPROVED_STAGE_ID,
    GETTING_THINGS_ROLLING_STAGE_ID,
    IN_PROCESS_STAGE_ID,
    CLEAR_TO_CLOSE_STAGE_ID,
    WON_STATUS,
    LOST_STATUS,
)

BASE_URL = "https://api.pipedrive.com/v1"

def get_person_labels(person_id):
    """
    Fetch and return the current multi-select labels on a person as a list.
    """
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    resp = requests.get(url)
    data = resp.json().get("data", {})
    raw = data.get("custom_fields", {}).get(CONTACT_LABEL_KEY)
    if not raw:
        return []
    # Pipedrive may return a comma-separated string or a list
    if isinstance(raw, str):
        return [lbl.strip() for lbl in raw.split(",") if lbl.strip()]
    if isinstance(raw, list):
        return raw
    return []

def update_person_labels(person_id, new_labels):
    """
    Update a person's labels to the new set.
    """
    payload = {CONTACT_LABEL_KEY: ",".join(new_labels)}
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    resp = requests.put(url, json=payload)
    print(f"[API] Updated person {person_id} labels to {new_labels} (Status {resp.status_code})")

def determine_stage_label(stage_id, status):
    """
    Determine what label should be applied based on stage and status.
    """
    if status == WON_STATUS:
        return "Closed Client"
    elif status == LOST_STATUS:
        return "REMOVE_ALL_EXCEPT_CLOSED"  # Special value to indicate remove all except "Closed Client"
    elif stage_id == APPLICATION_IN_STAGE_ID:
        return "Application In"
    elif stage_id == PREAPPROVED_STAGE_ID:
        return "Pre-Approved"
    elif stage_id in [GETTING_THINGS_ROLLING_STAGE_ID, IN_PROCESS_STAGE_ID, CLEAR_TO_CLOSE_STAGE_ID]:
        return "In Process"
    else:
        return None

def apply_labels_to_person(person_id, new_label, preserve_closed_client=False):
    """
    Apply new labels to a person, optionally preserving 'Closed Client'.
    """
    if not person_id:
        return
    
    current_labels = get_person_labels(person_id)
    
    if new_label == "REMOVE_ALL_EXCEPT_CLOSED":
        # Remove all labels except "Closed Client" if it exists
        if "Closed Client" in current_labels:
            final_labels = ["Closed Client"]
            print(f"[→] Person {person_id}: Lost deal - removing all labels except 'Closed Client'")
        else:
            final_labels = []
            print(f"[→] Person {person_id}: Lost deal - removing all labels")
    elif preserve_closed_client and "Closed Client" in current_labels:
        # Keep "Closed Client" and add the new label
        if new_label not in current_labels:
            final_labels = ["Closed Client", new_label]
        else:
            final_labels = ["Closed Client"]  # Already has the new label
        print(f"[→] Person {person_id}: Preserving 'Closed Client', adding '{new_label}'")
    else:
        # Replace all labels with the new one
        final_labels = [new_label]
        print(f"[→] Person {person_id}: Replacing all labels with '{new_label}'")
    
    # Only update if labels actually changed
    if set(current_labels) != set(final_labels):
        update_person_labels(person_id, final_labels)
    else:
        print(f"[✓] Person {person_id}: Labels already correct, skipping")

def comprehensive_stage_labels(payload):
    """
    Comprehensive stage label management for all pipeline stages.
    Handles lead-to-deal transitions and all stage changes.
    """
    data = payload.get('data', {})
    prev = payload.get('previous', {})
    meta = payload.get('meta', {})
    deal_id = data.get('id')
    
    if not deal_id or meta.get('change_source') == 'api':
        return
    
    # Check if this is a stage change or status change
    stage_changed = 'stage_id' in prev
    status_changed = 'status' in prev
    
    if not (stage_changed or status_changed):
        return  # No relevant changes
    
    current_stage = data.get('stage_id')
    current_status = data.get('status')
    prev_stage = prev.get('stage_id') if stage_changed else None
    prev_status = prev.get('status') if status_changed else None
    
    print(f"[→] Deal {deal_id}: Stage {prev_stage}→{current_stage}, Status {prev_status}→{current_status}")
    
    # Determine what label should be applied
    print(f"[DEBUG] Current stage: {current_stage} (type: {type(current_stage)})")
    print(f"[DEBUG] Current status: {current_status} (type: {type(current_status)})")
    print(f"[DEBUG] APPLICATION_IN_STAGE_ID: {APPLICATION_IN_STAGE_ID} (type: {type(APPLICATION_IN_STAGE_ID)})")
    
    new_label = determine_stage_label(current_stage, current_status)
    
    if not new_label:
        print(f"[→] No label change needed for stage {current_stage}, status {current_status}")
        return
    
    print(f"[→] Applying label: '{new_label}'")
    
    # Helper to extract person ID from custom fields
    def get_person_id(field_key):
        cf = data.get('custom_fields', {}).get(field_key)
        return cf.get('id') if isinstance(cf, dict) else None
    
    # Get main person and coborrower IDs
    main_person = data.get('person_id')
    main_person_id = main_person.get('value') if isinstance(main_person, dict) else main_person
    coborrower_id = get_person_id(COBORROWER_KEY)
    
    # Determine if we should preserve "Closed Client"
    preserve_closed_client = (new_label != "Closed Client")
    
    # Apply labels to main person
    if main_person_id:
        apply_labels_to_person(main_person_id, new_label, preserve_closed_client)
    
    # Apply labels to coborrower
    if coborrower_id:
        apply_labels_to_person(coborrower_id, new_label, preserve_closed_client)
    
    print(f"[✓] Completed label updates for Deal {deal_id}") 