# Initialization manager that is called by newmain.py during the startup of the program to initialize most tools.
# These tools initialized include database connection pools, twilio client, ngrok tunnels, google text and speech APIs and spacy/gemini (large tools that need to be loaded up beforehand)
import os
from twilio.rest import Client
from dotenv import load_dotenv
from speech_processing import initialize_speech_clients
from model_managers import SpacyManager, GeminiManager
from db_connection import initialize_db

class InitializationManager:
    _instance = None
    _initialized = False
    _resources = None

    @classmethod
    def initialize_resources(cls, db_url=None, ngrok_url=None):
        if cls._initialized:
            print("[InitializationManager] Resources already initialized, returning existing instance")
            return cls._resources

        print("[InitializationManager] Starting first-time initialization...")
        load_dotenv(dotenv_path='.env.docker')

        try:
            # Initialize NLP components (will use singleton pattern internally)
            print("[InitializationManager] Initializing NLP components...")
            nlp = SpacyManager.get_nlp(force_load=True)
            matcher = SpacyManager.get_matcher()
            
            # Configure Gemini API (will use singleton pattern internally)
            print("[InitializationManager] Configuring Gemini API...")
            GeminiManager.configure_api(force_configure=True)
            
            print("[InitializationManager] Initializing speech clients...")
            speech_client, text_client, voice, audio_config, elevenlabs_client, elevenlabs_voice_id, elevenlabs_settings, cartesia_client, cartesia_voice_id = initialize_speech_clients()
            #elevenlabs_client

            print("[InitializationManager] Initializing database...")
            db_client, db = initialize_db(connection_string=db_url)
            

            # Ngrok URL (from external ngrok process)
            if ngrok_url:
                print(f"[InitializationManager] Using provided ngrok URL: {ngrok_url}")
                ngrok_public_url = ngrok_url
            else:
                # Get ngrok URL from environment variable (set by simple_scheduler.sh)
                ngrok_public_url = os.getenv('NGROK_APP1_URL')
                if not ngrok_public_url:
                    # Fallback to generic env var
                    ngrok_public_url = os.getenv('NGROK_PUBLIC_URL')
                    if not ngrok_public_url:
                        raise ValueError("NGROK_APP1_URL or NGROK_PUBLIC_URL not set - ensure ngrok is started externally")
                print(f"[InitializationManager] Using ngrok URL from environment: {ngrok_public_url}")
            
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            twilio_client = Client(account_sid, auth_token)
            
            # Store all resources
            cls._resources = {
                'nlp': nlp,
                'matcher': matcher,
                'speech_clients': (speech_client, text_client, voice, audio_config, elevenlabs_client, elevenlabs_voice_id, elevenlabs_settings,cartesia_client, cartesia_voice_id ), #elevenlabs_client),
                'db': db,
                'ngrok_public_url': ngrok_public_url,
                'twilio_client': twilio_client,
            }
            
            cls._initialized = True
            print("[InitializationManager] Initialization completed successfully")
            return cls._resources

        except Exception as e:
            print(f"[InitializationManager] Error during initialization: {e}")
            raise

def initialize_resources(db_url=None, ngrok_url=None):
    return InitializationManager.initialize_resources(db_url=db_url, ngrok_url=ngrok_url)
