
# This module handles both inbound and outbound call processing using Twilio's Voice API. It provides TwiML responses for call routing and initiates outbound calls programmatically.
#
# Functions:
# - twilio_call(): Generates TwiML for connecting calls to WebSocket streams
# - inbound_call(): Handles inbound call TwiML responses and routing
# - make_call(): Initiates outbound calls with lead context (if ENABLE_OUTBOUND=true)
#
# Flow Overview (Inbound):
# 1. Twilio webhook (/inbound-call) triggers inbound_call(). Called from call_routes.py
# 2. TwiML generated with Stream element for WebSocket connection
# 3. Audio routed to websocket_handler for real-time processing
#
# Flow Overview (Outbound):
# 1. make_call() triggered from dashboard or CRM webhook (/make-call)  
# 2. Twilio call initiated with lead_id parameter in webhook URL. Called from call_routes.py
# 3. Call connects and routes to twilio_call() for TwiML generation with lead context
# 4. Status updates sent to call-status webhook (requires lead_id parameter for tracking)


from flask import Flask, Response
from twilio.twiml.voice_response import VoiceResponse, Stream
from twilio.rest import Client
import os
from dotenv import load_dotenv
from call_logger import get_call_logger

load_dotenv()

ENABLE_OUTBOUND = os.getenv('ENABLE_OUTBOUND', 'false').lower() == 'true'

app = Flask(__name__)

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
to_number = os.getenv('TWILIO_TO_NUMBER')
from_number = os.getenv('TWILIO_FROM_NUMBER')
client = Client(account_sid, auth_token)

if ENABLE_OUTBOUND:
    # initiate outbound call to lead using twilio api. 
    def make_call(ngrok_public_url, lead_id, phone_number):
        logger = get_call_logger(None, lead_id)
        try:
            logger.info(f"Attempting to make Twilio call to {phone_number} for lead {lead_id}")
            logger.debug(f"Using webhook URL: {ngrok_public_url}/voice-call?lead_id={lead_id}")
            
            call = client.calls.create(
                to=phone_number,
                from_=from_number,
                url=f"{ngrok_public_url}/voice-call?lead_id={lead_id}",
                method='POST',
                status_callback=f"{ngrok_public_url}/call-status?lead_id={lead_id}",
                status_callback_event=['initiated', 'ringing', 'answered', 'completed',
                                    'no-answer', 'busy', 'failed', 'canceled'],
                status_callback_method='POST',
                timeout=15 
            )
            
            logger.info(f"Twilio call initiated successfully. Call SID: {call.sid}")
            
            # Now that we have a call_sid, update our logger
            updated_logger = get_call_logger(call.sid, lead_id)
            updated_logger.info(f"Outbound call established for lead {lead_id}")
            
            return lead_id
        except Exception as e:
            logger.error(f"Error making Twilio call: {e}")
            return None

    # handle webhook response for outbound call
    def twilio_call(request, ngrok_public_url, lead_id, lead_info):
        try:
            call_sid = request.values.get('CallSid')
            logger = get_call_logger(call_sid, lead_id)
            logger.info(f"Handling Twilio voice call for lead: {lead_id}")
            
            # create websocket url for real-time audio streaming
            websocket_url = ngrok_public_url.replace("https", "wss") + f"/ws/{lead_id}/{call_sid}"
            logger.debug(f"WebSocket URL: {websocket_url}")

            # generate twiml response to connect twilio call to our websocket
            response = VoiceResponse()
            response.pause(length=0.2)
            
            # set up bi-directional audio streaming
            connect = response.connect()
            connect.stream(url=websocket_url, track="inbound_track")
            
            twiml = str(response).strip()
            logger.info(f"TwiML response generated successfully for call {call_sid}")
            logger.debug(f"TwiML response: {twiml}")
            return Response(twiml, mimetype='text/xml')
        except Exception as e:
            logger = get_call_logger(call_sid, lead_id)
            logger.error(f"Error handling Twilio call: {e}")
            return Response("<Response><Say>An error occurred</Say></Response>", mimetype='text/xml')
else:
    # Stub functions for when outbound calling is disabled
    def make_call(ngrok_public_url, lead_id, phone_number):
        logger = get_call_logger(None, lead_id)
        logger.info(f"Outbound calling is disabled in this configuration")
        return None

    def twilio_call(request, ngrok_public_url, lead_id, lead_info):
        call_sid = request.values.get('CallSid')
        logger = get_call_logger(call_sid, lead_id)
        logger.info(f"Outbound calling is disabled in this configuration")
        return Response("<Response><Say>Outbound calling is disabled</Say></Response>", mimetype='text/xml')

# handle incoming call to twilio number
def inbound_call(request, db, lead_info, ngrok_url):
    try:
        call_sid = request.values.get('CallSid')
        lead_id = str(lead_info['id']) if lead_info and 'id' in lead_info else None
        logger = get_call_logger(call_sid, lead_id)
        
        response = VoiceResponse()
        caller = request.values.get('From', None)
        
        logger.info(f"Received inbound call from: {caller}")

        # check if returning lead or new lead.
        if not lead_info or 'id' not in lead_info:
            logger.error("Error: Invalid lead info")
            return str(VoiceResponse())
        
        logger.info(f"Processing inbound call for lead_id: {lead_id}")
        
        # track call events we receive from twilio
        status_callback = f"{ngrok_url}/call-status?lead_id={lead_id}"        
        logger.debug(f"Setting status callback URL: {status_callback}")
        
        # create twiml response and set up websocket connection
        connect = response.connect(
            status_callback=status_callback,
            status_callback_event="initiated ringing answered completed no-answer busy failed canceled",
            status_callback_method='POST'
        )
        websocket_url = f"{ngrok_url.replace('https', 'wss')}/ws/{lead_id}/{call_sid}"
        logger.info(f"Setting WebSocket URL: {websocket_url}")  
        connect.stream(url=websocket_url)

        final_response = str(response)
        logger.debug(f"Generated TwiML: {final_response}")
        logger.info(f"Verifying TwiML contains status callback: {'statusCallback' in final_response}")
        return Response(final_response, mimetype='text/xml')
    except Exception as e:
        # In case we didn't initialize the logger earlier
        if not locals().get('logger'):
            logger = get_call_logger(call_sid, lead_id if 'lead_id' in locals() else None)
        logger.error(f"Error in inbound_call: {e}")
        return str(VoiceResponse())