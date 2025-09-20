
# This module handles the complete post-call data processing pipeline, from transcript analysis to pushing to CRM. 
#
# Key Responsibilities:
# - Receive and process Twilio call status webhooks ('completed', 'failed', etc.)
# - Trigger transcript processing and store data extraction from gemini
# - Coordinate database updates and CRM synchronization
# - Handle call completion cleanup and state management
# - Graceful handling of missing transcripts or lead data

#
# Webhook Processing Flow:
# 1. Twilio sends call status update to /call-status endpoint
# 2. Extract call metadata (SID, status, duration, lead_id)
# 3. Retrieve call transcript from shared state manager
# 4. Trigger data_extraction.process_full_transcript()
# 5. Update lead database with extracted information
# 6. Push data to configured CRM system via crm_integrations.base_crm.push_to_crm()
# 7. Send email notifications to realtor via notification_service.send_after_hours_notification()
# 8. Clean up call state and resources via state_manager.remove_state()
#
# Call Status Types Handled:
# - 'completed': Successful call completion
# - 'no-answer': Call not answered by lead
# - 'busy': Lead's line was busy
# - 'failed': Call failed to connect
# - 'canceled': Call was canceled before completion
#
# Integration Points:
# - Receives webhooks from Twilio via call_handling.py setup
# - Uses shared_state via state_manager for transcript retrieval
# - Triggers data_extraction.py for transcript processing
# - Coordinates with database_operations.py for data storage
# - Connects to CRM systems via crm_integrations
#

from flask import request, Response
from datetime import datetime
import os
import json
from data_extraction import process_full_transcript
from call_logger import get_call_logger

# Global variables that will be initialized by newmain.py
state_manager = None
chat = None

def init_status_handler(app, _state_manager, _chat):
    # Initialize the call status handler with the required global variables. 
    global state_manager, chat
    state_manager = _state_manager
    chat = _chat
    
    # Register routes with the Flask app
    app.route('/call-status', methods=['POST'])(handle_call_status)


def handle_call_status():
    # Handle Twilio call status updates
    try:
        print("\n=== Entered handle_call_status function ===")
        
        raw_data = request.get_data().decode('utf-8')
        print(f"Raw request data: {raw_data}")
        
        params = dict(param.split('=') for param in raw_data.split('&'))
        call_sid = params.get('CallSid')
        call_status = params.get('CallStatus')
        
        # Get lead_id from URL parameters (for webhook-triggered calls) or shared_state (for regular calls)
        lead_id = request.args.get('lead_id')  # URL parameter
        if not lead_id:
            # Fallback to shared_state for regular inbound calls
            shared_state = state_manager.get_state(call_sid)
            if shared_state:
                lead_id = shared_state.get_lead_id()
        
        # Always try to get shared_state (might be None for outbound calls)
        shared_state = state_manager.get_state(call_sid)
        
        print(f"Getting lead_id: {lead_id}")
        print(f"From URL params: {request.args.get('lead_id')}")
        print(f"From shared_state: {shared_state.get_lead_id() if shared_state else 'None'}")
    
        # Set up logging for this call
        logger = get_call_logger(call_sid, lead_id)
        print(f"Call SID: {call_sid}, Call Status: {call_status}, Lead ID: {lead_id}")
        
        if not call_sid or not call_status:
            logger.error("Error: Missing CallSid or CallStatus in request!")
            return Response("Missing required parameters", status=400)
        # once call is completed, process transcript and store in DB
        if call_status == 'completed':
            logger.info(f"[{datetime.now()}] Call completed, starting transcript processing...")
            
            # For webhook-triggered outbound calls, shared_state might be None
            transcript = ''
            if shared_state:
                shared_state.set_call_ended(True)
                shared_state.set_call_sid(call_sid)
                transcript = shared_state.get_transcript() or ''
                if transcript:
                    logger.info(f"Full transcript: {transcript}")
                else:
                    logger.info("No transcript available from shared_state")
            else:
                logger.info("No shared_state (outbound call) - using empty transcript")

            call_start_time = params.get('StartTime')
            call_end_time = params.get('EndTime')
            call_duration = params.get('CallDuration')

            if call_start_time:
                # Convert string timestamps to datetime objects if needed
                call_start_time = datetime.fromisoformat(call_start_time.replace('Z', '+00:00'))
            if call_end_time:
                call_end_time = datetime.fromisoformat(call_end_time.replace('Z', '+00:00'))
            if call_duration:
                call_duration = int(call_duration)
            
            logger.info(f"Retrieved data:")
            logger.info(f"  lead_id: {lead_id}")
            logger.info(f"  transcript length: {len(transcript) if transcript else 0}")
            logger.info(f"  transcript (first 100 chars): {transcript[:100] if transcript else 'None'}")
            
            if lead_id:
                logger.info("All required data is present, processing transcript...")
                
                # Create minimal shared_state for outbound calls if needed
                if not shared_state and lead_id:
                    from shared_state import SharedState
                    shared_state = SharedState()
                    shared_state.set_lead_id(int(lead_id))
                
                # Add timing data to the shared state if available
                if shared_state:
                    shared_state.set_call_start_time(call_start_time)
                    shared_state.set_call_end_time(call_end_time)
                    shared_state.set_call_duration(call_duration)
                
                if shared_state:
                    process_full_transcript(transcript, lead_id, shared_state, chat)
                    shared_state.set_transcript_processed(True)
                    logger.info(f"[{datetime.now()}] Transcript processing finished")
                    shared_state.set_notify_call_completed(True)
                else:
                    logger.error("Cannot process transcript: missing shared_state")
                
                # Only remove from state_manager if it was originally there
                if state_manager.get_state(call_sid):
                    state_manager.remove_state(call_sid)
            else:
                logger.error("Warning: Missing data for processing")
                logger.error(f"lead_id: {lead_id} , transcript length: {len(transcript) if transcript else 0}")
        elif call_status in ['no-answer', 'busy', 'failed', 'canceled']:
            logger.info(f"Call was not connected. Status: {call_status}")
            
            # Create minimal shared_state for outbound calls if needed
            if not shared_state and lead_id:
                from shared_state import SharedState
                shared_state = SharedState()
                shared_state.set_lead_id(int(lead_id))
            
            # Use the same efficient flow as completed calls - process_full_transcript handles everything
            if shared_state:
                shared_state.set_call_ended(True)
                shared_state.set_call_start_time(params.get('StartTime'))
                shared_state.set_call_end_time(params.get('EndTime'))
                shared_state.set_call_duration(params.get('CallDuration'))
            
            # Empty transcript for failed calls, but process_full_transcript will still handle CRM updates
            transcript = ''
            
            if lead_id and shared_state:
                logger.info(f"Processing failed call through standard flow for lead_id: {lead_id}")
                process_full_transcript(transcript, lead_id, shared_state, chat)
                shared_state.set_transcript_processed(True)
                logger.info(f"Failed call processing finished - CRM updated via standard flow")
                shared_state.set_notify_call_completed(True)
                
                # Only remove from state_manager if it was originally there
                if state_manager.get_state(call_sid):
                    state_manager.remove_state(call_sid)
            else:
                logger.error("Warning: Missing lead_id or shared_state for failed call processing")

            # Notify server.js about call completion
            notification = json.dumps({
                "action": "call_ended",
                "data": {
                    "event": "call_completed",
                    "call_sid": call_sid
                }
            })
            logger.info(notification)
        else:
            logger.info(f"Call status update: {call_status}")
        
        return Response("<Response></Response>", mimetype='text/xml'), 200
    except Exception as e:
        print(f"Error in handle_call_status: {e}")
        return Response("<Internal Server Error", status=500)

def set_twilio_webhook(twilio_client, ngrok_public_url):
    # Configure Twilio webhooks
    from_number = os.getenv('TWILIO_FROM_NUMBER')
    incoming_phone_number = twilio_client.incoming_phone_numbers.list(phone_number=from_number)[0]

    inbound_webhook_url = f"{ngrok_public_url}/inbound-call"
    outbound_webhook_url = f"{ngrok_public_url}/voice-call"
    status_callback_url = f"{ngrok_public_url}/call-status"  # New status callback URL

    result = incoming_phone_number.update(
        voice_url=inbound_webhook_url,
        voice_method='POST',
        status_callback=status_callback_url,  # Use the new status callback URL
        status_callback_method='POST',
        #status_callback_event=['initiated', 'ringing', 'answered', 'completed',
                 #          'no-answer', 'busy', 'failed', 'canceled']
    )
    print(f"Updated Twilio webhooks:")
    print(f"Inbound call webhook: {result.voice_url}")
    print(f"Status callback: {result.status_callback}")