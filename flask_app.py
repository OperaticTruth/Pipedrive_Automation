import os
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify, Response
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
from workflows.salesforce_sync.salesforce_client import SalesforceClient
from workflows.salesforce_sync.sync_deal import sync_deal_from_loan

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

@app.route('/webhook/salesforce/cdc', methods=['POST', 'GET'])
def handle_salesforce_cdc():
    """
    Handle Change Data Capture events from Salesforce.
    
    This endpoint receives real-time updates from Salesforce when
    Loan records are created or updated.
    
    GET requests are used by Salesforce for webhook verification/challenge.
    """
    if request.method == 'GET':
        # Salesforce CDC may send GET requests for verification/challenge
        # Return 200 OK to acknowledge
        return jsonify({"status": "ok", "message": "CDC webhook endpoint is active"}), 200
    
    try:
        event_data = request.get_json()
        result = handle_cdc_event(event_data)
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/webhook/salesforce/outbound', methods=['POST'])
def handle_salesforce_outbound():
    """
    Handle Salesforce Outbound Messages (SOAP/XML format).
    
    This endpoint receives SOAP XML messages from Salesforce Workflow
    Outbound Messages when Loan records are created or updated.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Parse SOAP XML
        xml_data = request.data
        logger.info(f"Received outbound message. Content-Type: {request.content_type}, Data length: {len(xml_data)}")
        logger.debug(f"Raw XML data: {xml_data.decode('utf-8')[:500]}")  # Log first 500 chars
        
        root = ET.fromstring(xml_data)
        
        # Extract namespace (Salesforce SOAP uses namespaces)
        namespaces = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'notifications': 'http://soap.sforce.com/2005/09/outbound'
        }
        
        # Find the notification body
        body = root.find('.//soapenv:Body', namespaces)
        if body is None:
            # Try without namespace
            body = root.find('.//Body')
        
        if body is None:
            logger.error("Could not find SOAP Body element")
            soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
            return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
        
        # Find notifications element
        notifications = body.find('.//notifications:notifications', namespaces)
        if notifications is None:
            # Try without namespace
            notifications = body.find('.//notifications')
        
        if notifications is None:
            logger.error("Could not find notifications element")
            soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
            return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
        
        # Extract Loan ID from the notification
        # Try multiple ways to find the Id field
        loan_id = None
        
        # Method 1: Look for Notification > sObject > Id
        notification = notifications.find('.//notifications:Notification', namespaces)
        if notification is None:
            notification = notifications.find('.//Notification')
        
        if notification is not None:
            logger.debug(f"Found notification element: {ET.tostring(notification, encoding='unicode')[:200]}")
            
            # Try to find sObject
            s_object = notification.find('.//sObject', namespaces)
            if s_object is None:
                s_object = notification.find('.//sObject')
            if s_object is None:
                # Maybe sObject is directly in notification with namespace
                for prefix, uri in namespaces.items():
                    s_object = notification.find(f'.//{{{uri}}}sObject')
                    if s_object is not None:
                        break
            
            if s_object is not None:
                logger.debug(f"Found sObject element: {ET.tostring(s_object, encoding='unicode')[:200]}")
                loan_id_elem = s_object.find('.//Id', namespaces)
                if loan_id_elem is None:
                    loan_id_elem = s_object.find('.//Id')
                if loan_id_elem is None:
                    # Try with namespace
                    for prefix, uri in namespaces.items():
                        loan_id_elem = s_object.find(f'.//{{{uri}}}Id')
                        if loan_id_elem is not None:
                            break
                
                if loan_id_elem is not None and loan_id_elem.text:
                    loan_id = loan_id_elem.text
                    logger.info(f"Found Loan ID via sObject: {loan_id}")
        
        # Method 2: Search for Id anywhere in the notification
        if not loan_id and notification is not None:
            # Search for any Id element in notification
            for elem in notification.iter():
                if elem.tag.endswith('Id') or elem.tag == 'Id':
                    if elem.text and elem.text.startswith('a0'):
                        loan_id = elem.text
                        logger.info(f"Found Loan ID via direct search: {loan_id}")
                        break
        
        # Method 3: Search entire body for Id
        if not loan_id:
            for elem in body.iter():
                if elem.tag.endswith('Id') or elem.tag == 'Id':
                    if elem.text and elem.text.startswith('a0'):
                        loan_id = elem.text
                        logger.info(f"Found Loan ID via body search: {loan_id}")
                        break
        
        if not loan_id:
            logger.error("Could not find Loan ID in XML. Full XML structure:")
            logger.error(ET.tostring(root, encoding='unicode')[:2000])
            soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
            return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
        logger.info(f"Extracted Loan ID: {loan_id}")
        
        # Fetch the full loan record from Salesforce
        sf_client = SalesforceClient()
        loan = sf_client.get_loan_by_id(loan_id)
        
        if not loan:
            logger.error(f"Could not fetch Loan {loan_id} from Salesforce")
            soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
            return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
        
        logger.info(f"Fetched loan {loan_id}, syncing to Pipedrive...")
        # Sync the loan to Pipedrive
        deal_id = sync_deal_from_loan(loan)
        
        if deal_id:
            logger.info(f"Successfully synced Loan {loan_id} to Deal {deal_id}")
            # Return success SOAP response with correct Content-Type
            soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>true</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
            return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
        else:
            logger.warning(f"Sync returned None for Loan {loan_id}")
            soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
            return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
            
    except ET.ParseError as e:
        logger.error(f"XML parsing error: {e}")
        logger.error(f"XML data: {request.data.decode('utf-8', errors='ignore')[:1000]}")
        # Return error SOAP response
        soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
        return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200
    except Exception as e:
        logger.error(f"Error processing outbound message: {e}", exc_info=True)
        # Return error SOAP response
        soap_response = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body><notifications:notificationsResponse xmlns:notifications="http://soap.sforce.com/2005/09/outbound"><notifications:Ack>false</notifications:Ack></notifications:notificationsResponse></soapenv:Body></soapenv:Envelope>'
        return Response(soap_response, mimetype='text/xml; charset=utf-8'), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
