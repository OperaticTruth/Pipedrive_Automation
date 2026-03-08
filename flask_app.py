import os
import logging
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
from workflows.loan_amount_sync import loan_amount_sync
from workflows.first_payment_date import calculate_first_payment_date
from workflows.calculate_210_days import calculate_210_days
from workflows.commission import calculate_commission
from workflows.comprehensive_stage_labels import comprehensive_stage_labels
from workflows.loan_number_extract import extract_loan_number
from workflows.birth_month_extract import extract_birth_month
from workflows.average_buy_volume import calculate_average_buy_volume
from workflows.agent_stage_labels import agent_stage_labels

# Salesforce sync imports
from workflows.salesforce_sync import run_polling_sync, handle_cdc_event, run_initial_sync

# Dialpad integration
from workflows.dialpad import (
    handle_call_event,
    handle_sms_event,
    handle_dialpad_contact_event,
    run_dialpad_contact_sync,
    resolve_pending_names,
)
from workflows.dialpad.utils import decode_dialpad_webhook
from config import DIALPAD_WEBHOOK_SECRET

app = Flask(__name__)

# --- Existing Pipedrive Webhook Routes ---
@app.route('/webhook/changedeal', methods=['POST'])
def handle_changed_deal():
    pl = request.get_json()
    loan_amount_sync(pl)
    extract_loan_number(pl)
    calculate_first_payment_date(pl)
    calculate_210_days(pl)
    calculate_commission(pl)
    comprehensive_stage_labels(pl)
    agent_stage_labels(pl)
    return '', 200

@app.route('/webhook/changeperson', methods=['POST'])
def handle_changed_person():
    pl = request.get_json()
    extract_birth_month(pl)
    calculate_average_buy_volume(pl)
    return '', 200

# --- Salesforce Sync Routes ---
@app.route('/sync/poll', methods=['POST', 'GET'])
def sync_poll():
    """
    Trigger a polling sync manually.
    
    Query params:
        hours_back: Number of hours to look back (default: 24)
    """
    try:
        hours_back = int(request.args.get('hours_back', 24))
        result = run_polling_sync(hours_back=hours_back)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/sync/initial', methods=['POST', 'GET'])
def sync_initial():
    """
    Run an initial full sync (all loans, no time filter).
    
    Query params:
        limit: Maximum number of loans to sync (default: 1000)
    """
    try:
        limit = int(request.args.get('limit', 1000))
        result = run_initial_sync(limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def _dialpad_payload():
    """Decode Dialpad webhook body: JSON or JWT."""
    data = request.get_json(silent=True)
    if data is not None:
        return data
    raw = request.get_data(as_text=True)
    return decode_dialpad_webhook(raw, DIALPAD_WEBHOOK_SECRET)

@app.route('/webhook/dialpad/call', methods=['POST'])
def handle_dialpad_call():
    try:
        event_data = _dialpad_payload()
        logging.debug("DIALPAD CALL PAYLOAD: %s", event_data)
        result = handle_call_event(event_data)
        logging.debug("DIALPAD CALL RESULT: %s", result)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        logging.exception("Error in handle_dialpad_call")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/webhook/dialpad/sms', methods=['POST'])
def handle_dialpad_sms():
    try:
        event_data = _dialpad_payload()
        result = handle_sms_event(event_data)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/webhook/dialpad/contact', methods=['POST'])
def handle_dialpad_contact():
    try:
        event_data = _dialpad_payload()
        result = handle_dialpad_contact_event(event_data)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/sync/dialpad/contacts', methods=['POST', 'GET'])
def sync_dialpad_contacts():
    """Manually trigger Pipedrive → Dialpad contact sync."""
    try:
        result = run_dialpad_contact_sync()
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/sync/dialpad/resolve-pending', methods=['POST', 'GET'])
def sync_resolve_pending():
    """Check Dialpad for real names on PD placeholder contacts and update PD."""
    try:
        result = resolve_pending_names()
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/webhook/salesforce/cdc', methods=['POST'])
def handle_salesforce_cdc():
    """
    Handle Change Data Capture events from Salesforce.
    
    This endpoint receives real-time updates from Salesforce when
    Loan records are created or updated.
    """
    try:
        event_data = request.get_json()
        result = handle_cdc_event(event_data)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
