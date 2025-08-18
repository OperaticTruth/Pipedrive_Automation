import os
from flask import Flask, request
from workflows.loan_amount_sync import loan_amount_sync
from workflows.first_payment_date import calculate_first_payment_date
from workflows.calculate_210_days import calculate_210_days
from workflows.commission import calculate_commission
from workflows.comprehensive_stage_labels import comprehensive_stage_labels
from workflows.loan_number_extract import extract_loan_number
from workflows.birth_month_extract import extract_birth_month
from workflows.average_buy_volume import calculate_average_buy_volume
from workflows.agent_stage_labels import agent_stage_labels

app = Flask(__name__)

# --- Routes ---
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
