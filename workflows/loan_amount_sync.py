from config import LOAN_AMOUNT_KEY
from .utils import update_deal_field, update_deal_custom_field

def loan_amount_sync(payload):
    data     = payload.get("data", {})
    prev     = payload.get("previous", {})
    meta     = payload.get("meta", {})
    deal_id  = data.get("id")

    # safety: missing ID or self-generated event
    if not deal_id or meta.get("change_source") == "api":
        return

    # extract current values
    current_value = data.get("value")
    cf            = data.get("custom_fields", {}).get(LOAN_AMOUNT_KEY) or {}
    current_loan  = cf.get("value")

    # did the custom field change?
    cf_prev = prev.get("custom_fields", {})
    if LOAN_AMOUNT_KEY in cf_prev:
        prev_loan = cf_prev[LOAN_AMOUNT_KEY].get("value")
        if current_loan != prev_loan:
            print(f"[→] Loan amount changed ({prev_loan}→{current_loan}), syncing to value field")
            update_deal_field(deal_id, "value", current_loan)
            return

    # did the native value field change?
    if "value" in prev:
        prev_value = prev["value"]
        if current_value != prev_value:
            print(f"[→] Deal value changed ({prev_value}→{current_value}), syncing to loan field")
            update_deal_custom_field(deal_id, LOAN_AMOUNT_KEY, current_value)
            return 