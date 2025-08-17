from config import BUY_SIDES_KEY, BUY_VOLUME_KEY, AVERAGE_BUY_VOLUME_KEY
from workflows.utils import update_person_custom_field

def calculate_average_buy_volume(payload):
    data = payload.get('data', {})
    prev = payload.get('previous', {})
    meta = payload.get('meta', {})
    person_id = data.get('id')
    
    print(f"[DEBUG] Processing person {person_id}")
    print(f"[DEBUG] All custom fields: {list(data.get('custom_fields', {}).keys())}")
    print(f"[DEBUG] Looking for fields: {BUY_SIDES_KEY}, {BUY_VOLUME_KEY}")
    
    if not person_id or meta.get('change_source') == 'api':
        return

    # Check if any relevant field changed
    buy_sides_changed = False
    buy_volume_changed = False
    
    # Check if buy sides field changed
    cf_prev = prev.get('custom_fields', {})
    cf_data = data.get('custom_fields', {})
    
    if BUY_SIDES_KEY in cf_data:
        prev_buy_sides = cf_prev.get(BUY_SIDES_KEY)
        current_buy_sides = cf_data.get(BUY_SIDES_KEY)
        prev_buy_sides_val = prev_buy_sides.get('value') if isinstance(prev_buy_sides, dict) else prev_buy_sides
        current_buy_sides_val = current_buy_sides.get('value') if isinstance(current_buy_sides, dict) else current_buy_sides
        if prev_buy_sides is None or prev_buy_sides_val != current_buy_sides_val:
            buy_sides_changed = True
            print(f"[→] Buy sides changed ({prev_buy_sides_val}→{current_buy_sides_val})")
    
    # Check if buy volume field changed
    if BUY_VOLUME_KEY in cf_data:
        prev_buy_volume = cf_prev.get(BUY_VOLUME_KEY)
        current_buy_volume = cf_data.get(BUY_VOLUME_KEY)
        prev_buy_volume_val = prev_buy_volume.get('value') if isinstance(prev_buy_volume, dict) else prev_buy_volume
        current_buy_volume_val = current_buy_volume.get('value') if isinstance(current_buy_volume, dict) else current_buy_volume
        if prev_buy_volume is None or prev_buy_volume_val != current_buy_volume_val:
            buy_volume_changed = True
            print(f"[→] Buy volume changed ({prev_buy_volume_val}→{current_buy_volume_val})")
    
    # Only proceed if one of these fields changed
    if not (buy_sides_changed or buy_volume_changed):
        return
    
    # Get current values for calculation
    buy_sides_field = cf_data.get(BUY_SIDES_KEY)
    buy_volume_field = cf_data.get(BUY_VOLUME_KEY)
    
    # Parse buy sides value
    if isinstance(buy_sides_field, dict):
        buy_sides = buy_sides_field.get('value')
    else:
        buy_sides = buy_sides_field
    
    # Parse buy volume value
    if isinstance(buy_volume_field, dict):
        buy_volume = buy_volume_field.get('value')
    else:
        buy_volume = buy_volume_field
    
    # Convert to numbers, defaulting to 0 if not present
    try:
        buy_sides_num = float(buy_sides) if buy_sides is not None else 0
        buy_volume_num = float(buy_volume) if buy_volume is not None else 0
    except (ValueError, TypeError):
        print(f"[⚠] Invalid numeric values: buy_sides={buy_sides}, buy_volume={buy_volume}")
        return
    
    # Calculate average buy volume
    if buy_sides_num > 0:
        average_buy_volume = buy_volume_num / buy_sides_num
        print(f"[→] Calculated average buy volume: ${buy_volume_num:,.2f} ÷ {buy_sides_num} = ${average_buy_volume:,.2f}")
    else:
        average_buy_volume = 0
        print(f"[→] Buy sides is 0 or negative, setting average buy volume to 0")
    
    # Avoid loops by checking existing value
    existing_avg = cf_data.get(AVERAGE_BUY_VOLUME_KEY)
    if existing_avg:
        existing_avg_str = existing_avg.get('value') if isinstance(existing_avg, dict) else existing_avg
        try:
            if float(existing_avg_str) == average_buy_volume:
                print(f"[✓] Average buy volume already {average_buy_volume:,.2f}, skipping")
                return
        except:
            pass
    
    print(f"[→] Average buy volume → ${average_buy_volume:,.2f} for Person {person_id}")
    update_person_custom_field(person_id, AVERAGE_BUY_VOLUME_KEY, average_buy_volume)
