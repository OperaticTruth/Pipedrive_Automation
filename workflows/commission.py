from config import COMMISSION_KEY, SELF_SOURCED_KEY, BRANCH_PRICING_KEY, COMPANY_LEAD_KEY, LOAN_AMOUNT_KEY
from workflows.utils import update_deal_custom_field
import pprint

def calculate_commission(payload):
    data = payload.get('data', {})
    prev = payload.get('previous', {})
    meta = payload.get('meta', {})
    deal_id = data.get('id')
    
    if not deal_id or meta.get('change_source') == 'api':
        return

    # Check if any relevant field changed
    value_changed = False
    loan_amount_changed = False
    self_sourced_changed = False
    branch_pricing_changed = False
    company_lead_changed = False
    
    # Check if value field changed
    if 'value' in prev:
        prev_value = prev['value']
        current_value = data.get('value', 0)
        if prev_value != current_value:
            value_changed = True
            print(f"[→] Value changed ({prev_value}→{current_value})")
    
    # Check if loan amount field changed
    cf_prev = prev.get('custom_fields', {})
    cf_data = data.get('custom_fields', {})
    if LOAN_AMOUNT_KEY in cf_data:
        prev_loan = cf_prev.get(LOAN_AMOUNT_KEY)
        current_loan = cf_data.get(LOAN_AMOUNT_KEY)
        prev_loan_val = prev_loan.get('value') if isinstance(prev_loan, dict) else prev_loan
        current_loan_val = current_loan.get('value') if isinstance(current_loan, dict) else current_loan
        if prev_loan is None or prev_loan_val != current_loan_val:
            loan_amount_changed = True
            print(f"[→] Loan amount changed ({prev_loan_val}→{current_loan_val})")
    
    # Check if self_sourced changed
    if SELF_SOURCED_KEY in cf_data:
        prev_ss = cf_prev.get(SELF_SOURCED_KEY)
        current_ss = cf_data.get(SELF_SOURCED_KEY)
        prev_ss_id = prev_ss.get('id') if isinstance(prev_ss, dict) else prev_ss
        current_ss_id = current_ss.get('id') if isinstance(current_ss, dict) else current_ss
        if prev_ss is None or prev_ss_id != current_ss_id:
            self_sourced_changed = True
            print(f"[→] Self-sourced changed ({prev_ss_id}→{current_ss_id})")
    
    # Check if branch_pricing changed
    if BRANCH_PRICING_KEY in cf_data:
        prev_bp = cf_prev.get(BRANCH_PRICING_KEY)
        current_bp = cf_data.get(BRANCH_PRICING_KEY)
        prev_bp_id = prev_bp.get('id') if isinstance(prev_bp, dict) else prev_bp
        current_bp_id = current_bp.get('id') if isinstance(current_bp, dict) else current_bp
        if prev_bp is None or prev_bp_id != current_bp_id:
            branch_pricing_changed = True
            print(f"[→] Branch pricing changed ({prev_bp_id}→{current_bp_id})")
    
    # Check if company_lead changed
    if COMPANY_LEAD_KEY in cf_data:
        prev_cl = cf_prev.get(COMPANY_LEAD_KEY)
        current_cl = cf_data.get(COMPANY_LEAD_KEY)
        prev_cl_id = prev_cl.get('id') if isinstance(prev_cl, dict) else prev_cl
        current_cl_id = current_cl.get('id') if isinstance(current_cl, dict) else current_cl
        if prev_cl is None or prev_cl_id != current_cl_id:
            company_lead_changed = True
            print(f"[→] Company lead changed ({prev_cl_id}→{current_cl_id})")
    
    # Only proceed if one of these fields changed
    if not (value_changed or loan_amount_changed or self_sourced_changed or branch_pricing_changed or company_lead_changed):
        return
    
    # Get the amount to calculate commission on
    # If loan amount changed in this webhook, use the NEW loan amount value
    # instead of the old value field to avoid race condition
    if loan_amount_changed and LOAN_AMOUNT_KEY in cf_data:
        current_loan = cf_data.get(LOAN_AMOUNT_KEY)
        current_loan_val = current_loan.get('value') if isinstance(current_loan, dict) else current_loan
        amount = current_loan_val or 0
        print(f"[→] Using updated loan amount {amount} for commission calculation (avoiding race condition)")
    else:
        # Use value field as before
        amount = data.get('value', 0) or 0
        print(f"[→] Using value field {amount} for commission calculation")
    
    # Debug prints for enum values
    ss_field = cf_data.get(SELF_SOURCED_KEY)
    bp_field = cf_data.get(BRANCH_PRICING_KEY)
    cl_field = cf_data.get(COMPANY_LEAD_KEY)
    
    print(f"[DEBUG] Self-sourced field: {ss_field}")
    print(f"[DEBUG] Branch pricing field: {bp_field}")
    print(f"[DEBUG] Company lead field: {cl_field}")
    
    # Parse self-sourced (ID 91 = Yes)
    if isinstance(ss_field, dict):
        self_sourced_id = ss_field.get('id')
    else:
        self_sourced_id = None
    is_self_sourced = (self_sourced_id == 91)
    print(f"[DEBUG] Self-sourced ID: {self_sourced_id} -> is_self_sourced: {is_self_sourced}")
    
    # Parse branch pricing (ID 137 = Yes)
    if isinstance(bp_field, dict):
        branch_pricing_id = bp_field.get('id')
    else:
        branch_pricing_id = None
    is_branch_pricing = (branch_pricing_id == 137)
    print(f"[DEBUG] Branch pricing ID: {branch_pricing_id} -> is_branch_pricing: {is_branch_pricing}")
    
    # Parse company lead (ID 139 = Yes)
    if isinstance(cl_field, dict):
        company_lead_id = cl_field.get('id')
    else:
        company_lead_id = None
    is_company_lead = (company_lead_id == 139)
    print(f"[DEBUG] Company lead ID: {company_lead_id} -> is_company_lead: {is_company_lead}")
    
    # Calculate commission based on rules
    if is_company_lead:
        # Company lead = yes: always $250
        commission = 250
        print(f"[→] Company lead is Yes, commission = $250")
    else:
        # Base rate calculation
        if is_self_sourced:
            base_rate = 0.008  # 80bps
            print(f"[→] Self-sourced is Yes, base rate = 80bps")
        else:
            base_rate = 0.004  # 40bps
            print(f"[→] Self-sourced is No, base rate = 40bps")
        
        # Apply branch pricing reduction
        if is_branch_pricing:
            base_rate = base_rate / 2  # Cut in half
            print(f"[→] Branch pricing is Yes, rate reduced to {base_rate*100}bps")
        
        # Calculate commission
        commission = round(amount * base_rate, 2)
        print(f"[→] Calculated commission = ${commission} (amount: ${amount}, rate: {base_rate*100}bps)")
        
        # Apply caps
        if is_self_sourced and not is_branch_pricing:
            cap = 7619.05
        elif is_self_sourced and is_branch_pricing:
            cap = 3809.52
        elif not is_self_sourced and not is_branch_pricing:
            cap = 3200
        elif not is_self_sourced and is_branch_pricing:
            cap = 1600
        else:
            cap = float('inf')  # No cap
        
        if commission > cap:
            commission = cap
            print(f"[→] Commission capped at ${cap}")
    
    # Avoid loops by checking existing value
    existing_comm = cf_data.get(COMMISSION_KEY)
    if existing_comm:
        existing_comm_str = existing_comm.get('value') if isinstance(existing_comm, dict) else existing_comm
        try:
            if float(existing_comm_str) == commission:
                print(f"[✓] Commission already {commission}, skipping")
                return
        except:
            pass
    
    print(f"[→] Commission → ${commission} for Deal {deal_id}")
    update_deal_custom_field(deal_id, COMMISSION_KEY, commission) 