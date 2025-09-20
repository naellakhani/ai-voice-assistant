# ===========================================
# Main Application Entry Point - AI Voice Agent System
# ===========================================
#
# This is the primary entry point for the AI Voice Agent real estate system. It orchestrates the complete application startup. 
#
# System Architecture Overview:
# 1. Environment & Configuration Loading (.env.docker)
# 2. Resource Initialization (twilio voice api, google speech to text, multiple tts providers, gemini flash, postgresql database)
# 3. Flask Application Setup with WebSocket support
# 4. Route Registration (inbound/outbound calls, webhooks, status)
# 5. Ngrok Tunnel Creation for public webhook endpoints
# 6. CRM Integration Initialization (FollowUpBoss, HubSpot, Zoho)
# 7. Health Check Endpoints for monitoring
# 8. State Manager for concurrent call handling
#
# Startup Sequence:
# 1. Load environment variables and validate configuration
# 2. Initialize database connection and run health checks
# 3. Initialize AI models and speech processing clients
# 4. Setup Flask routes for call handling and webhooks
# 5. Create Ngrok tunnel for public webhook access
# 6. Initialize CRM integrations and webhook registration
# 7. Start Flask application with WebSocket support
#

from flask import Flask, request
from flask_sock import Sock
import os
from pyngrok import ngrok
from dotenv import load_dotenv
import sys
from initialization import initialize_resources
from shared_state import StateManager
from call_routes import init_routes
from call_status import init_status_handler, set_twilio_webhook
from crm_integrations.followupboss.webhook_lead_detector import init_webhook_routes
from websocket_handler import websocket_endpoint
from flask import jsonify
import datetime
from database_operations import get_db
from model_managers import GeminiManager
import time
from call_logger import get_call_logger

load_dotenv(dotenv_path='.env.docker')
ENABLE_OUTBOUND = os.getenv('ENABLE_OUTBOUND', 'false').lower() == 'true'
logger= get_call_logger()

app = Flask(__name__)
sock = Sock(app)
process_start_time = time.time()


# Global variables
model, chat, nlp, matcher = None, None, None, None
speech_client, text_client, voice, audio_config = None, None, None, None
elevenlabs_client, elevenlabs_voice_id, elevenlabs_settings = None, None, None
cartesia_client, cartesia_voice_id = None, None 
db_client, db = None, None
ngrok_public_url = None
state_manager = StateManager()
twilio_client = None
ngrok_public_url = None
global_transcript = []

def get_database_url():
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        logger.info(f"Using database URL from environment: {db_url}")
        return db_url

def setup_ngrok():
    try:
        ngrok_auth_token = os.getenv('NGROK_AUTH_TOKEN')
        if ngrok_auth_token:
            ngrok.set_auth_token(ngrok_auth_token)
        
        # Connect to ngrok
        ngrok_tunnel = ngrok.connect(5000, bind_tls=True)
        ngrok_url = ngrok_tunnel.public_url
        logger.info(f"Ngrok URL: {ngrok_url}")
        
        # Set the NGROK_URL environment variable for other scripts to use
        os.environ['NGROK_URL'] = ngrok_url
        logger.info(f"Set NGROK_URL environment variable: {ngrok_url}")
        
        return ngrok_url
    except Exception as e:
        logger.info(f"Error setting up ngrok: {e}")
        sys.exit(1)

def startup_routine(db_url=None, ngrok_url=None):
    try:
        # Unpack all the resources
        global model, chat, nlp, matcher, speech_client, text_client, voice, audio_config
        global db_client, db, twilio_client, ngrok_public_url
        global elevenlabs_client, elevenlabs_voice_id, elevenlabs_settings
        global cartesia_client, cartesia_voice_id
        ngrok_public_url = ngrok_url
        resources = initialize_resources(db_url=db_url, ngrok_url=ngrok_url)

        nlp = resources['nlp']
        matcher = resources['matcher']
        speech_client, text_client, voice, audio_config, elevenlabs_client, elevenlabs_voice_id, elevenlabs_settings, cartesia_client, cartesia_voice_id = resources['speech_clients']
        db = resources['db']
        #ngrok_public_url = resources['ngrok_public_url']
        twilio_client = resources['twilio_client']

        # Print ngrok URL for the Node.js server
        print(f"NGROK_URL:{ngrok_public_url}")

        logger.info(f"Outbound calling is {'ENABLED' if ENABLE_OUTBOUND else 'DISABLED'}")
        
        init_routes(app, state_manager, ngrok_public_url)
        init_status_handler(app, state_manager, chat)
        
        # Initialize CRM integrations
        crm_enabled = os.getenv('CRM_ENABLED', 'false').lower() == 'true'
        if crm_enabled:
            logger.info("Initializing CRM integrations...")
            try:
                from crm_integrations import initialize_crm_integrations
                crm_success = initialize_crm_integrations()
                if crm_success:
                    logger.info(" CRM integrations initialized successfully")
                else:
                    logger.warning(" CRM integrations failed to initialize")
            except Exception as e:
                logger.error(f" CRM initialization error: {e}")
        else:
            logger.info("CRM integrations disabled (CRM_ENABLED=false)")

        # Initialize CRM webhook routes only if CRM is enabled
        if crm_enabled:
            init_webhook_routes(app, ngrok_public_url)  # Initialize FollowUpBoss webhook routes
        
        # Register primary crm webhook
        if crm_enabled:
            try:
                from crm_integrations.base_crm import get_crm
                primary_crm = get_crm()  # Gets the primary CRM (whatever was initialized)
                if primary_crm and primary_crm.supports_webhooks():
                    webhook_url = f"{ngrok_public_url}/webhook/new-lead"
                    webhook_success = primary_crm.register_webhooks(webhook_url)
                    if webhook_success:
                        logger.info(f"{primary_crm.get_crm_name()} webhooks registered successfully via CRM interface")
                    else:
                        logger.warning(f"Failed to register {primary_crm.get_crm_name()} webhooks")
                else:
                    logger.warning("Primary CRM not available or doesn't support webhooks")
            except Exception as e:
                logger.error(f"Failed to register primary CRM webhooks: {e}")
        else:
            logger.info("CRM webhook registration skipped (CRM_ENABLED=false)")
        
        # Set up Twilio webhooks
        set_twilio_webhook(twilio_client, ngrok_public_url)
        print("Running with Python version:", sys.version)


        logger.info("Startup routine completed successfully.")
        
    except Exception as e:
        logger.info(f"Fatal error during startup: {e}")
        sys.exit(1)

@sock.route('/ws/<lead_id>/<call_sid>')
def handle_websocket(ws, lead_id, call_sid):
    
    shared_state = state_manager.get_state(call_sid)
    
    if lead_id:
        shared_state.set_lead_id(lead_id)
        print(f"[newmain] Set lead_id in shared_state: {lead_id}")
    else:
        lead_id = shared_state.get_lead_id()
        print(f"[newmain] Retrieved lead_id from shared_state: {lead_id}")

    call_logger = get_call_logger(call_sid, lead_id)
    logger.info(f"[newmain] WebSocket connected for lead_id: {lead_id}")
    
    websocket_endpoint(ws, shared_state, state_manager)

def run_flask_app():
    logger.info(f"Starting Flask application on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

@app.route('/health', methods=['GET'])
def health_check():
    """Lightweight health check for open source deployment"""
    try:
        health_status = {
            "status": "ok",
            "components": {
                "database": "ok",
                "ngrok": "ok", 
                "google_ai": "ok",
                "speech_clients": "ok",
                "twilio": "ok"
            },
            "timestamp": datetime.datetime.now().isoformat(),
            "active_calls": len(state_manager.states),
            "uptime_seconds": int(time.time() - process_start_time)
        }
        
        # Check database connection
        try:
            db = get_db()
            if not db.check_connection_health():
                health_status["components"]["database"] = "error"
                health_status["status"] = "error"
        except Exception:
            health_status["components"]["database"] = "error"
            health_status["status"] = "error"
        
        # Check ngrok URL is configured
        if not ngrok_public_url or "ngrok" not in ngrok_public_url:
            health_status["components"]["ngrok"] = "error"
            health_status["status"] = "error"
        
        # Check Google AI configuration
        if not hasattr(GeminiManager, '_api_configured') or not GeminiManager._api_configured:
            health_status["components"]["google_ai"] = "error"
            health_status["status"] = "error"
        
        # Check speech clients are initialized
        if speech_client is None or text_client is None:
            health_status["components"]["speech_clients"] = "error"
            health_status["status"] = "error"
        
        # Check Twilio client is initialized
        if twilio_client is None:
            health_status["components"]["twilio"] = "error"
            health_status["status"] = "error"
        
        status_code = 200 if health_status["status"] == "ok" else 500
        return jsonify(health_status), status_code
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Health check failed: {str(e)}"
        }), 500

# simple health check endpoint for container health check
@app.route('/simple-health', methods=['GET'])
def simple_health_check():
    """Lightweight health check just for Docker container monitoring"""
    try:
        # Only check if Flask is responsive
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':

    db_url = get_database_url()
    
    # Set up ngrok
    ngrok_public_url = setup_ngrok()
    
    startup_routine(db_url, ngrok_public_url)

    # Run Flask app on the main thread
    run_flask_app()