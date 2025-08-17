from datetime import datetime
from config import BIRTHDAY_KEY, BIRTH_MONTH_KEY
from workflows.utils import update_person_custom_field

def extract_birth_month(payload):
    """
    Extract birth month from birthday field and update birth month helper field.
    This enables easy filtering by birth month (1-12) for birthday campaigns.
    """
    data = payload.get('data', {})
    prev = payload.get('previous', {})
    meta = payload.get('meta', {})
    person_id = data.get('id')
    
    if not person_id or meta.get('change_source') == 'api':
        return
    
    # Check if birthday field changed or has a value
    current_birthday = data.get('custom_fields', {}).get(BIRTHDAY_KEY)
    prev_birthday = prev.get('custom_fields', {}).get(BIRTHDAY_KEY)
    
    # If birthday field exists and has a value, process it
    if current_birthday:
        birthday_value = current_birthday.get('value') if isinstance(current_birthday, dict) else current_birthday
        
        if birthday_value:
            try:
                # Parse the birthday - handle different date formats
                if isinstance(birthday_value, str):
                    # Try different date formats
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            birth_date = datetime.strptime(birthday_value, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        print(f"[✗] Could not parse birthday format: {birthday_value}")
                        return
                else:
                    print(f"[✗] Unexpected birthday field type: {type(birthday_value)}")
                    return
                
                # Extract month number (1-12)
                birth_month = birth_date.month
                print(f"[→] Extracted birth month: {birth_month} from birthday {birth_date.strftime('%Y-%m-%d')}")
                
                # Check if we already have this birth month to avoid loops
                existing_month = data.get('custom_fields', {}).get(BIRTH_MONTH_KEY)
                if existing_month:
                    existing_value = existing_month.get('value') if isinstance(existing_month, dict) else existing_month
                    if existing_value == birth_month:
                        print(f"[✓] Birth month already set to {birth_month}, skipping")
                        return
                
                # Update the birth month field
                print(f"[→] Updating birth month field to {birth_month} for Person {person_id}")
                update_person_custom_field(person_id, BIRTH_MONTH_KEY, birth_month)
                
            except Exception as e:
                print(f"[✗] Error processing birthday {birthday_value}: {e}")
                return
        else:
            print(f"[→] Birthday field exists but has no value for Person {person_id}")
    else:
        print(f"[→] No birthday field found for Person {person_id}") 