import re
from config import LOAN_NUMBER_KEY, DEAL_TITLE_KEY
from .utils import update_deal_custom_field

def extract_loan_number(payload):
    """
    Extract the last 9 digits from deal name and update the Loan # field.
    Only runs when deal name changes.
    """
    data = payload.get('data', {})
    prev = payload.get('previous', {})
    meta = payload.get('meta', {})
    deal_id = data.get('id')
    
    if not deal_id or meta.get('change_source') == 'api':
        return
    
    # Check if deal name changed
    current_name = data.get(DEAL_TITLE_KEY, '')
    prev_name = prev.get(DEAL_TITLE_KEY, '')
    
    if current_name == prev_name:
        return  # No name change
    
    print(f"[→] Deal name changed ({prev_name} → {current_name})")
    
    # Extract the last 9 digits from the deal name
    # Look for 9 consecutive digits at the end of the string
    match = re.search(r'(\d{9})$', current_name)
    
    if not match:
        print(f"[✗] No 9-digit number found at end of deal name: {current_name}")
        return
    
    loan_number = match.group(1)
    print(f"[→] Extracted loan number: {loan_number}")
    
    # Check if we already have this loan number to avoid loops
    existing_loan_number = data.get('custom_fields', {}).get(LOAN_NUMBER_KEY)
    if existing_loan_number:
        existing_value = existing_loan_number.get('value') if isinstance(existing_loan_number, dict) else existing_loan_number
        if existing_value == loan_number:
            print(f"[✓] Loan number already set to {loan_number}, skipping")
            return
    
    # Update the Loan # field
    print(f"[→] Updating Loan # field to {loan_number} for Deal {deal_id}")
    update_deal_custom_field(deal_id, LOAN_NUMBER_KEY, loan_number) 