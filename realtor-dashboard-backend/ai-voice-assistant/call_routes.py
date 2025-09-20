
# This module defines Flask route handlers for both inbound and outbound call processing and serves as the primary entry point for all Twilio webhook requests and dashboard-initiated calls.
#
# Key Responsibilities:
# - Handle inbound call webhooks from Twilio and Process outbound call requests from dashboard/CRM
# - Lead identification or creation for new callers and Realtor assignment and conversation context setup
# - Call state initialization and routing to WebSocket handler
# - Integration with shared state management system
#
# Webhook Route Handlers:
# - /inbound-call: Processes incoming calls via Twilio webhook
# - /make-call: Initiates outbound calls (if ENABLE_OUTBOUND=true)
# - /voice-call: Handles outbound call connections
#
# Flow Overview (Inbound):
# 1. Twilio sends webhook to /inbound-call
# 2. Identify realtor by called number
# 3. Look up existing lead by caller phone
# 4. Create new lead if not found
# 5. Initialize shared state with lead context
# 6. Route to websocket_handler for conversation
#
# Flow Overview (Outbound):
# 1. Dashboard/CRM triggers /make-call
# 2. Validate lead_id and phone_number
# 3. Use call_handling.make_call() to initiate via Twilio
# 4. Twilio connects and calls /voice-call webhook
# 5. Route to websocket_handler with lead context
#
# Integration Points:
# - Uses database_operations for lead management
# - Connects to call_handling for Twilio operations
# - Initializes shared_state for conversation context
# - Routes to websocket_handler for real-time processing

from flask import request, Response, jsonify
import threading
from call_handling import make_call, twilio_call, inbound_call
from database_operations import get_lead_info, get_lead_info_by_phone, create_new_lead, get_realtor_by_phone, get_db
import os
from call_logger import get_call_logger

ENABLE_OUTBOUND = os.getenv('ENABLE_OUTBOUND', 'false').lower() == 'true'

# Global variables that will be initialized by newmain.py
state_manager = None
ngrok_public_url = None

def init_routes(app, _state_manager, _ngrok_public_url):
    #Initialize Flask routes and register call handling endpoints
    logger = get_call_logger()
    logger.info("Initializing call routes")
    
    global state_manager, ngrok_public_url
    state_manager = _state_manager
    ngrok_public_url = _ngrok_public_url
    
    app.route('/inbound-call', methods=['POST'])(handle_inbound_call)

    if ENABLE_OUTBOUND:
        # Register routes with the Flask app
        logger.info("Registering outbound call routes")
        app.route('/make-call', methods=['POST'])(make_call_route)
        app.route('/voice-call', methods=['POST'])(handle_twilio_call)
    else:
        logger.info("Outbound call routes disabled")

def handle_make_call(data, is_http_request=True):
    # Process outbound call requests with lead id and phone number validation. trigger actual process of starting outbound call.
    logger = get_call_logger()
    
    if not ENABLE_OUTBOUND:
        logger.info("Received make-call request but outbound calling is disabled")
        result = {"status": "error", "message": "Outbound calling is disabled"}
        return jsonify(result) if is_http_request else result
        
    global ngrok_public_url
    lead_id = data.get('leadId')
    phone_number = data.get('phoneNumber')
    logger.info(f"Handling make-call request for lead {lead_id} to {phone_number}")
    
    if not lead_id or not phone_number:
        logger.error("Missing leadId or phoneNumber in make-call request")
        return {"status": "error", "message": "Missing leadId or phoneNumber"}
    
    lead_info = get_lead_info(lead_id)
    if lead_info:
        if not ngrok_public_url:
            logger.error("Ngrok URL not set, cannot make outbound call")
            return {"status": "error", "message": "Ngrok URL not set"}
        
        logger.info(f"Starting thread to make outbound call to {phone_number} for lead {lead_id}")
        threading.Thread(target=make_call, args=(ngrok_public_url, lead_id, phone_number)).start()
        result = {"status": "success", "message": "Call initiated"}
    else:
        logger.error(f"Lead not found for lead_id: {lead_id}")
        result = {"status": "error", "message": "Lead not found"}
    
    if is_http_request:
        return jsonify(result)
    else:
        return result

def make_call_route():
    #HTTP route for making a call
    logger = get_call_logger()
    logger.info("Received request to /make-call endpoint")
    
    if not ENABLE_OUTBOUND:
        logger.info("Outbound calling is disabled, rejecting request")
        return jsonify({"status": "error", "message": "Outbound calling is disabled"})
    
    result = handle_make_call(request.json)
    if isinstance(result, Response):
        return result
    else:
        # If it's not already a Response object, convert it to one
        return jsonify(result)

def handle_twilio_call():
    # Handle Twilio webhook when outbound call connects and generate TwiML response
    lead_id = request.args.get('lead_id')
    call_sid = request.values.get('CallSid')
    logger = get_call_logger(call_sid, lead_id)
    logger.info(f"Lead ID: {lead_id}, Call SID: {call_sid}")
    
    if not ENABLE_OUTBOUND:
        logger.warning("Received voice-call webhook but outbound calling is disabled")
        return Response("<Response><Say>Outbound calling is disabled</Say></Response>", mimetype='text/xml')
    
    logger.info("Received request to /voice-call endpoint")
    logger.debug(f"Request form data: {request.form}")
    
    shared_state = state_manager.get_state(call_sid)
    
    lead_info = get_lead_info(lead_id)
    if lead_info is None:
        logger.error(f"Failed to retrieve lead info for lead_id: {lead_id}")
        return Response("<Response><Say>Error: Lead not found</Say></Response>", mimetype='text/xml'), 404
    
    logger.info(f"Successfully retrieved lead info for {lead_info.get('name', 'unknown')}")
    
    # Set the lead info in shared state
    shared_state.set_lead_info(lead_info)
    shared_state.set_lead_id(lead_id)
    
    twiml_response = twilio_call(request, ngrok_public_url, lead_id, lead_info)
    
    logger.info("TwiML response generated, sending back to Twilio")
    logger.debug(f"Final TwiML being sent to Twilio: {twiml_response.get_data(as_text=True)}")
    return twiml_response

def handle_inbound_call():
    # Handle inbound calls - single-stage process where caller dials Twilio number and we immediately generate TwiML response
    call_sid = request.form.get('CallSid')
    logger = get_call_logger(call_sid)
   
    logger.info("Handling inbound call")
    logger.debug(f"Request form: {request.form}")
    logger.debug(f"Request args: {request.args}")
    logger.info(f"CallSid: {call_sid}")
    
    shared_state = state_manager.get_state(call_sid)
    shared_state.set_call_sid(call_sid)
    call_status = request.form.get('CallStatus')
    
    forwarder = request.values.get('ForwardedFrom', None)
    caller = request.values.get('From', None)
    # Extract the called number (this is your Twilio number)
    called = request.values.get('Called', None)
    
    # Format caller number if it starts with +1 (North American)
    if caller and caller.startswith('+1'):
        # Extract just the 10 digits after +1 and format
        digits = caller[2:]  # Remove the +1
        formatted_caller = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    else:
        formatted_caller = caller
        
    # Format forwarder number if it starts with +1
    if forwarder and forwarder.startswith('+1'):
        # Extract just the 10 digits after +1 and format
        digits = forwarder[2:]  # Remove the +1
        formatted_forwarder = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    else:
        formatted_forwarder = forwarder

    logger.info(f"Inbound call from: {caller} to: {called}, forwarded from: {forwarder}")
    shared_state.set_phone_number(formatted_forwarder if forwarder else formatted_caller)
    shared_state.set_is_inbound(True)

    realtor_info = get_realtor_by_phone(forwarder if forwarder else called)
    realtor_id = None
    
    # if forwarded from number exists and is in our realtors table, then use that realtor's info
    if realtor_info:
        realtor_id = realtor_info['id']
        realtor_name = f"{realtor_info['first_name']} {realtor_info['last_name']}"
        shared_state.set_realtor_name(realtor_name)
        # Load the real estate prompt
        from conversation_manager import load_prompt_template, DEFAULT_PROMPT_PATH
        prompt = load_prompt_template(DEFAULT_PROMPT_PATH)
        shared_state.set_conversation_prompt(prompt)
        logger.info(f"Loaded real estate prompt for {realtor_name}")
    else:
        # Default to John Doe if no realtor found
        from conversation_manager import load_prompt_template, DEFAULT_PROMPT_PATH
        prompt = load_prompt_template(DEFAULT_PROMPT_PATH)
        shared_state.set_conversation_prompt(prompt)
        shared_state.set_realtor_name("John Doe")
        logger.info("Using default realtor (John Doe) for this conversation")
    
    lead_info = get_lead_info_by_phone(caller, realtor_id)
    if lead_info:
        logger.info(f"Existing lead found: {lead_info}")
        lead_info['is_inbound'] = True
        lead_info['is_returning_lead'] = True
        shared_state.set_lead_info(lead_info)
        shared_state.set_lead_id(str(lead_info['id']))
        shared_state.set_is_returning_lead(True)
        logger.info("Identified as a returning lead")
    else:
        logger.info("No existing lead found, creating new lead")
        new_lead_id = create_new_lead(caller, realtor_id)
        lead_info = get_lead_info(new_lead_id)
        if lead_info:
            if realtor_info:
                lead_info['realtor_name'] = f"{realtor_info['first_name']} {realtor_info['last_name']}"
            else:
                lead_info['realtor_name'] = "John Doe"
            lead_info['is_inbound'] = True
            lead_info['is_returning_lead'] = False
            shared_state.set_lead_info(lead_info)
            shared_state.set_lead_id(new_lead_id)
            shared_state.set_is_returning_lead(False)
        logger.info(f"New lead created: {lead_info}")
    
    twiml_response = inbound_call(request, get_db(), lead_info, ngrok_public_url)
    if isinstance(twiml_response, Response):
        logger.debug(f"Final TwiML being sent to Twilio: {twiml_response.get_data(as_text=True)}")
    else:
        logger.debug(f"Final TwiML being sent to Twilio: {twiml_response}")
        twiml_response = Response(twiml_response, mimetype='text/xml')
    return twiml_response