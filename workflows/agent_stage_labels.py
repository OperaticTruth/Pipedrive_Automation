import requests
from config import (
    PIPEDRIVE_API_KEY,
    CONTACT_LABEL_KEY,
    BUYER_AGENT_KEY,
    LISTING_AGENT_KEY,
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

def determine_agent_stage_label(stage_id, status):
    """
    Determine what label should be applied to agents based on stage and status.
    """
    if status == WON_STATUS:
        return None  # Will remove "In Process" label
    elif status == LOST_STATUS:
        return None # Will remove all labels except "Closed Client"
    elif stage_id in [GETTING_THINGS_ROLLING_STAGE_ID, IN_PROCESS_STAGE_ID, CLEAR_TO_CLOSE_STAGE_ID]:
        return "In Process"
    else:
        return None

def apply_labels_to_agent(person_id, new_label, preserve_closed_client=False, is_lost_deal=False):
    """
    Apply new labels to an agent, optionally preserving 'Closed Client'.
    """
    if not person_id:
        return
    
    current_labels = get_person_labels(person_id)
    
    if new_label is None:
        if is_lost_deal:
            # Lost deal: remove all labels except "Closed Client"
            if "Closed Client" in current_labels:
                final_labels = ["Closed Client"]
                print(f"[→] Agent {person_id}: Lost deal - removing all labels except 'Closed Client'")
            else:
                final_labels = []
                print(f"[→] Agent {person_id}: Lost deal - removing all labels")
        else:
            # Won deal: Remove "In Process" label but preserve "Closed Client"
            if "In Process" in current_labels:
                final_labels = [lbl for lbl in current_labels if lbl != "In Process"]
                print(f"[→] Agent {person_id}: Removing 'In Process' label, preserving other labels")
            else:
                print(f"[✓] Agent {person_id}: No 'In Process' label to remove")
                return
    elif preserve_closed_client and "Closed Client" in current_labels:
        # Keep "Closed Client" and add the new label
        if new_label not in current_labels:
            final_labels = ["Closed Client", new_label]
        else:
            final_labels = ["Closed Client"]  # Already has the new label
        print(f"[→] Agent {person_id}: Preserving 'Closed Client', adding '{new_label}'")
    else:
        # Replace all labels with the new one
        final_labels = [new_label]
        print(f"[→] Agent {person_id}: Replacing all labels with '{new_label}'")
    
    # Only update if labels actually changed
    if set(current_labels) != set(final_labels):
        update_person_labels(person_id, final_labels)
    else:
        print(f"[✓] Agent {person_id}: Labels already correct, skipping")

def agent_stage_labels(payload):
    """
    Handle buyer agent and listing agent labels based on pipeline stages.
    Sets "In Process" label when deal moves to active stages.
    Removes "In Process" label when deal is closed/won.
    """
    data = payload.get('data', {})
    prev = payload.get('previous', {})
    meta = payload.get('meta', {})
    deal_id = data.get('id')
    
    print(f"[DEBUG] Processing deal {deal_id} for agent labels")
    
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
    
    # Determine what label should be applied to agents
    new_label = determine_agent_stage_label(current_stage, current_status)
    
    if new_label is None and current_status != WON_STATUS:
        print(f"[→] No agent label change needed for stage {current_stage}, status {current_status}")
        return
    
    # Helper to extract person ID from custom fields
    def get_person_id(field_key):
        cf = data.get('custom_fields', {}).get(field_key)
        return cf.get('id') if isinstance(cf, dict) else None
    
    # Get buyer agent and listing agent IDs
    buyer_agent_id = get_person_id(BUYER_AGENT_KEY)
    listing_agent_id = get_person_id(LISTING_AGENT_KEY)
    
    print(f"[DEBUG] Buyer agent ID: {buyer_agent_id}")
    print(f"[DEBUG] Listing agent ID: {listing_agent_id}")
    
    # Determine if we should preserve "Closed Client"
    preserve_closed_client = (new_label != "Closed Client")
    
    # Determine if this is a lost deal
    is_lost_deal = (new_label is None and current_status == LOST_STATUS)

    # Apply labels to buyer agent
    if buyer_agent_id:
        print(f"[→] Processing buyer agent {buyer_agent_id}")
        apply_labels_to_agent(buyer_agent_id, new_label, preserve_closed_client, is_lost_deal)
    
    # Apply labels to listing agent
    if listing_agent_id:
        print(f"[→] Processing listing agent {listing_agent_id}")
        apply_labels_to_agent(listing_agent_id, new_label, preserve_closed_client, is_lost_deal)
    
    print(f"[✓] Completed agent label updates for Deal {deal_id}")
