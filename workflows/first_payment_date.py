from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from config import FUNDED_DATE_KEY, FIRST_PAYMENT_DATE_KEY, TWOHUNDREDTEN_DAYS_KEY
from workflows.utils import update_deal_custom_field

def calculate_first_payment_date(payload):
    data = payload.get('data', {})
    meta = payload.get('meta', {})
    deal_id = data.get('id')
    if not deal_id or meta.get('change_source') == 'api':
        return
    # fetch raw funded date field, may be string or dict
    funded_date_field = data.get('custom_fields', {}).get(FUNDED_DATE_KEY)
    print(f"[…] Raw funded date field: {funded_date_field}")
    if not funded_date_field:
        return
    # extract string value
    if isinstance(funded_date_field, dict):
        funding_str = funded_date_field.get('value')
    else:
        funding_str = funded_date_field
    if not isinstance(funding_str, str):
        print(f"[✗] Unexpected funded date type: {funded_date_field}")
        return
    # parse ISO datetime or date
    try:
        if 'T' in funding_str:
            dt_fund = datetime.fromisoformat(funding_str.replace('Z', ''))
        else:
            dt_fund = datetime.strptime(funding_str, '%Y-%m-%d')
        date_fund = dt_fund.date()
    except Exception as e:
        print(f"[✗] Could not parse funded date '{funding_str}': {e}")
        return
    
    # compute first payment date: add 1 month, then goto 1st of next month
    tmp = date_fund + relativedelta(months=1)
    first_pd = tmp.replace(day=1) + relativedelta(months=1)
    # check existing to avoid loop
    existing = data.get('custom_fields', {}).get(FIRST_PAYMENT_DATE_KEY)
    if existing:
        existing_str = existing.get('value') if isinstance(existing, dict) else existing
        if existing_str == first_pd.isoformat():
            print(f"[✓] First payment date already {existing_str}, skipping")
            # Still update 210-day field even if first payment date is unchanged
            auto_210 = first_pd + timedelta(days=210)
            print(f"[→] 210-day date (auto) → {auto_210} for Deal {deal_id}")
            update_deal_custom_field(deal_id, TWOHUNDREDTEN_DAYS_KEY, auto_210.isoformat())
            return
    print(f"[→] First payment date → {first_pd} for Deal {deal_id}")
    update_deal_custom_field(deal_id, FIRST_PAYMENT_DATE_KEY, first_pd.isoformat())
    # Always update 210-day date based on new first payment date
    auto_210 = first_pd + timedelta(days=210)
    print(f"[→] 210-day date (auto) → {auto_210} for Deal {deal_id}")
    update_deal_custom_field(deal_id, TWOHUNDREDTEN_DAYS_KEY, auto_210.isoformat()) 