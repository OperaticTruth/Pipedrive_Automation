from datetime import datetime, timedelta
from config import FIRST_PAYMENT_DATE_KEY, TWOHUNDREDTEN_DAYS_KEY
from workflows.utils import update_deal_custom_field

def calculate_210_days(payload):
    data = payload.get('data', {})
    meta = payload.get('meta', {})
    deal_id = data.get('id')
    if not deal_id or meta.get('change_source') == 'api':
        return
    fpd_field = data.get('custom_fields', {}).get(FIRST_PAYMENT_DATE_KEY)
    print(f"[…] Raw first payment date field: {fpd_field}")
    if not fpd_field:
        return
    if isinstance(fpd_field, dict):
        fpd_str = fpd_field.get('value')
    else:
        fpd_str = fpd_field
    if not isinstance(fpd_str, str):
        print(f"[✗] Unexpected first payment date type: {fpd_field}")
        return
    try:
        date_fpd = datetime.strptime(fpd_str, '%Y-%m-%d').date()
    except Exception as e:
        print(f"[✗] Could not parse first payment date '{fpd_str}': {e}")
        return
    new_date = date_fpd + timedelta(days=210)
    # check existing to avoid loop
    existing_210 = data.get('custom_fields', {}).get(TWOHUNDREDTEN_DAYS_KEY)
    if existing_210:
        existing_210_str = existing_210.get('value') if isinstance(existing_210, dict) else existing_210
        if existing_210_str == new_date.isoformat():
            print(f"[✓] 210-day date already {existing_210_str}, skipping")
            return
    print(f"[→] 210 days date → {new_date} for Deal {deal_id}")
    update_deal_custom_field(deal_id, TWOHUNDREDTEN_DAYS_KEY, new_date.isoformat()) 