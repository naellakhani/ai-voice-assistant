#!/usr/bin/env python3
"""
FollowUpBoss Webhook Lead Detector

Listens for FollowUpBoss webhooks when new leads are created and automatically
triggers outbound calls to new leads using the batch calling system.

This prevents duplicate contacts by tracking FollowUpBoss person IDs and ensures
all conversation data is properly linked back to the original FollowUpBoss record.
"""

import os
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from database_operations import create_new_lead_with_fub_id, get_lead_by_fub_person_id
from .batch_outbound_caller import BatchOutboundCaller
from call_logger import get_call_logger

load_dotenv('.env.docker')

# OLD CLASS REMOVED - Using CRM interface instead

# Global ngrok URL for webhook routes
global_ngrok_url = None

def init_webhook_routes(app, ngrok_url=None):
    """Initialize webhook routes with the Flask app"""
    global global_ngrok_url
    global_ngrok_url = ngrok_url
    logger = get_call_logger()
    logger.info("Initializing FollowUpBoss webhook routes")
    
    @app.route('/webhook/new-lead', methods=['POST'])
    def handle_followupboss_webhook():
        """Handle FollowUpBoss webhook for new leads"""
        try:
            # Verify request is JSON
            if not request.is_json:
                logger.warning("Received non-JSON webhook request")
                return jsonify({'error': 'Content-Type must be application/json'}), 400
            
            # Get webhook data
            webhook_data = request.get_json()
            
            # Log webhook for debugging
            logger.info(f"🔔 WEBHOOK RECEIVED from FollowUpBoss")
            logger.info(f"📋 Webhook data: {webhook_data}")
            
            event_type = webhook_data.get('event', 'unknown')
            print(f"🔔 [DEBUG] FollowUpBoss webhook received!")
            print(f"📋 [DEBUG] Event type: {event_type}")
            print(f"👤 [DEBUG] Person data present: {bool(webhook_data.get('data', {}).get('person'))}")
            
            if event_type == 'peopleCreated':
                print(f"🆕 [DEBUG] This is a NEW person creation webhook")
            elif event_type == 'peopleUpdated':
                print(f"🔄 [DEBUG] This is an EXISTING person update webhook")
            else:
                print(f"❓ [DEBUG] Unknown webhook event type")
            
            # Use CRM interface for webhook processing
            try:
                from crm_integrations.base_crm import get_crm
                crm = get_crm("FollowUpBoss")  # Get FollowUpBoss CRM specifically
                
                if not crm:
                    logger.error("FollowUpBoss CRM not found")
                    return jsonify({'error': 'FollowUpBoss CRM not initialized'}), 500
                
                # Process webhook through CRM interface
                result = crm.handle_webhook_data(webhook_data)
                
                if result.get('status') == 'success' and result.get('should_call'):
                    # Make immediate outbound call if needed
                    logger.info("Webhook indicates outbound call needed - initiating call...")
                    person_id = result.get('person_id')
                    lead_info = result.get('lead_info')
                    
                    # Create/get lead in database
                    from database_operations import create_new_lead_with_fub_id, get_lead_by_fub_person_id
                    existing_lead = get_lead_by_fub_person_id(person_id)
                    if existing_lead:
                        lead_id = existing_lead['id']
                    else:
                        lead_id = create_new_lead_with_fub_id(
                            phone_number=lead_info.get('phone', ''),
                            realtor_id=1,
                            followupboss_person_id=person_id,
                            name=lead_info.get('name', ''),
                            email=lead_info.get('email', ''),
                            agent_name=lead_info.get('agent_name'),
                            property_address=lead_info.get('property_address'),
                            source=lead_info.get('source')
                        )
                    
                    if lead_id:
                        # Make the outbound call
                        from .batch_outbound_caller import BatchOutboundCaller
                        batch_caller = BatchOutboundCaller(ngrok_url=global_ngrok_url)
                        contact = {
                            'id': person_id,
                            'name': lead_info.get('name', 'Unknown'),
                            'phones': [{'value': lead_info.get('phone')}] if lead_info.get('phone') else [],
                            'emails': [{'value': lead_info.get('email')}] if lead_info.get('email') else []
                        }
                        success = batch_caller.make_outbound_call(contact, existing_lead_id=lead_id)
                        result['call_initiated'] = success
                
            except Exception as e:
                logger.error(f"Error processing webhook through CRM interface: {e}")
                return jsonify({'error': 'Webhook processing failed', 'details': str(e)}), 500
            
            # Return appropriate response
            if result['status'] == 'success':
                return jsonify(result), 200
            elif result['status'] == 'exists':
                return jsonify(result), 200
            elif result['status'] == 'ignored':
                return jsonify(result), 200
            else:
                return jsonify(result), 400
                
        except Exception as e:
            logger.error(f"Error in webhook handler: {e}")
            return jsonify({'error': 'Internal server error', 'details': str(e)}), 500
    
    @app.route('/webhook/test', methods=['GET', 'POST'])
    def test_webhook():
        """Test endpoint for webhook functionality"""
        logger.info("Test webhook endpoint called")
        
        # Sample webhook data for testing
        test_data = {
            "event": {
                "type": "person.created",
                "timestamp": datetime.now().isoformat()
            },
            "data": {
                "person": {
                    "id": "test-person-123",
                    "firstName": "John",
                    "lastName": "Doe",
                    "phones": [{"value": "+1234567890", "type": "Mobile"}],
                    "emails": [{"value": "john.doe@example.com", "type": "Work"}],
                    "source": "Test Webhook",
                    "tags": ["Test Lead"]
                }
            }
        }
        
        # Use CRM interface for test webhook processing  
        try:
            from crm_integrations.base_crm import get_crm
            crm = get_crm("FollowUpBoss")
            
            if not crm:
                return jsonify({'error': 'FollowUpBoss CRM not initialized'}), 500
                
            result = crm.handle_webhook_data(test_data)
        except Exception as e:
            result = {'status': 'error', 'reason': str(e)}
        return jsonify({'test_result': result}), 200
    
    logger.info("✅ FollowUpBoss webhook routes initialized")
    logger.info("   📍 POST /webhook/new-lead - Main webhook endpoint")
    logger.info("   📍 GET/POST /webhook/test - Test endpoint")




# Standalone Flask app for testing
if __name__ == "__main__":
    app = Flask(__name__)
    init_webhook_routes(app)
    
    port = int(os.getenv('WEBHOOK_PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)