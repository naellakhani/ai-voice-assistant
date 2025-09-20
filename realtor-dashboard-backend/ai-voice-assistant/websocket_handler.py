
# This module handles real-time WebSocket connections for voice calls via Twilio.
#
# Flow Overview:
# 1. WebSocket connects with Twilio Media Streams → Load lead info & pre-format AI prompt
# 2. Audio chunks received → Google Speech-to-text conversion with context-aware processing
# 3. Text processed → AI generates response via Gemini (with interrupt handling)
# 4. AI response → Multi-provider text-to-speech → Audio sent back
# 5. Call completion → Transcript processing and push to CRM.
#

import json
import requests
import base64
import threading
from speech_processing import SpeechClientBridge, get_streaming_config, text_to_speech, TTSProvider
from conversation_manager import manage_conversation
from initialization import InitializationManager
import requests
import os
import re
import time
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
from google.oauth2 import service_account
from call_logger import get_call_logger
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from cartesia import Cartesia

def select_appropriate_prompt(shared_state, logger):
    # Load conversation prompt from cache or default file
    try:
        # Check for cached prompt first
        cached_prompt = shared_state.get_conversation_prompt()
        if cached_prompt:
            logger.info("[websocket_handler] Using cached conversation prompt")
            return cached_prompt
        
        # Load default prompt
        from conversation_manager import load_prompt_template, DEFAULT_PROMPT_PATH
        prompt = load_prompt_template(DEFAULT_PROMPT_PATH)
        shared_state.set_conversation_prompt(prompt)
        logger.info("[websocket_handler] Loaded default conversation prompt")
        return prompt
        
    except Exception as e:
        logger.error(f"[websocket_handler] Error loading prompt: {e}")
        return None

def websocket_endpoint(ws, shared_state, state_manager=None):
    call_sid = None
    lead_id = shared_state.get_lead_id()
    
    # Get call_sid if available
    if hasattr(shared_state, 'get_call_sid'):
        call_sid = shared_state.get_call_sid()
    
    # Set up logging for this call
    logger = get_call_logger(call_sid, lead_id)
    logger.info("[websocket_handler] WebSocket connection opened")
    
    resources = InitializationManager._resources
    active_calls = len(state_manager.states) if state_manager else 1
    
    # for concurrent calls: give each call its own speech and text client to avoid conversation interruption.
    if active_calls <= 1:
        # Use the global clients if this is the only active call
        speech_client = resources['speech_clients'][0]
        text_client = resources['speech_clients'][1]
        voice = resources['speech_clients'][2]
        audio_config = resources['speech_clients'][3]
        elevenlabs_client = resources['speech_clients'][4]
        elevenlabs_voice_id = resources['speech_clients'][5]
        elevenlabs_settings = resources['speech_clients'][6]
        cartesia_client = resources['speech_clients'][7]
        cartesia_voice_id = resources['speech_clients'][8]
        logger.info("[websocket_handler] Using global speech clients for single call")
    else:
        #print(f"[websocket_handler] Creating new speech clients for concurrent call {active_calls}")
        speech_credentials = service_account.Credentials.from_service_account_file(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_SPEECH'))
        text_credentials = service_account.Credentials.from_service_account_file(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_TEXT'))
        
        # Create new client instances for this call
        speech_client = speech.SpeechClient(credentials=speech_credentials)
        text_client = texttospeech.TextToSpeechClient(credentials=text_credentials)
        
        # Reuse the same voice and audio config parameters as they're just configuration objects
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Neural2-D")
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MULAW, sample_rate_hertz=8000)

        elevenlabs_client = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
        elevenlabs_voice_id = os.getenv('ELEVENLABS_VOICE_ID')
        elevenlabs_settings = VoiceSettings(
            stability=0.7,
            similarity_boost=0.8,
            style=0.0,
            use_speaker_boost=True
        )

        cartesia_client = Cartesia(api_key=os.getenv('CARTESIA_API_KEY'))
        cartesia_voice_id = os.getenv('CARTESIA_VOICE_ID')

    tts_provider = os.getenv('TTS_PROVIDER', TTSProvider.ELEVENLABS)
    logger.info(f"[websocket_handler] Using TTS Provider: {tts_provider}")
    
    lead_id = shared_state.get_lead_id()
    lead_info = shared_state.get_lead_info()

    # failsafe mechanism: when shared state dosen't have lead info, create temporary placeholder.
    if lead_info is None:
        lead_info = {
            'id': lead_id,
            'name': 'there',
            'email': 'unknown@example.com',
            'phone': 'unknown',
            'realtor_id': None,
            'agent_name': None,
            'property_address': None,
            'is_inbound': shared_state.get_is_inbound()
        }
        shared_state.set_lead_info(lead_info)
        logger.debug(f"[websocket_handler] Created new lead_info: {lead_info}")
   
    # Use FollowUpBoss data if available, otherwise use lead_info
    
    lead_name = lead_info.get('name', 'there')
    lead_email = lead_info.get('email', 'unknown@example.com')
    lead_source = lead_info.get('source') or 'None'
    lead_tags = lead_info.get('tags', [])
    agent_name = lead_info.get('agent_name')
    property_address = lead_info.get('property_address')
    is_inbound = shared_state.get_is_inbound()
    caller_phone = lead_info.get('phone') or shared_state.get_phone_number() or "the phone number you called from"
    
    logger.info(f"[websocket_handler] Lead data from database:")
    logger.info(f"    Name: {lead_name}")
    logger.info(f"    Email: {lead_email}")
    logger.info(f"    Agent: {agent_name}")
    logger.info(f"    Property: {property_address}")
    logger.info(f"    Phone: {caller_phone}")
    logger.info(f"    Source: {lead_source}")
    logger.info(f"    Tags: {lead_tags}")
    logger.info(f"    Inbound: {'Yes' if is_inbound else 'No'}")

    if shared_state.get_call_ended() and shared_state.get_transcript_processed():
        #print("Sending pending call_completed notification to Node.js server")
        ws.send(json.dumps({
            "event": "call_completed",
            "call_sid": shared_state.get_call_sid()
        }))
        shared_state.set_notify_call_completed(False)

    # Initialize chat if not already present
    if not hasattr(shared_state, 'chat'):
        from model_managers import GeminiManager
        import google.generativeai as genai
        
        # 1. Create the chat
        model, chat = GeminiManager.create_chat()
        shared_state.chat = chat
        
        # 2. Pre-format the prompt
        logger.info("[websocket_handler] Pre-formatting prompt")
        try:
            # Get prompt template based on lead status and scenario
            prompt = select_appropriate_prompt(shared_state, logger)
            if not prompt:
                from conversation_manager import DEFAULT_PROMPT
                prompt = DEFAULT_PROMPT
            
            
            # Pre-format the prompt with everything except the user input
            formatted_prompt = prompt.format(
                lead_name=lead_name,
                lead_email=lead_email,
                lead_source=lead_source,
                lead_tags=", ".join(lead_tags) if isinstance(lead_tags, list) else str(lead_tags) if lead_tags else "None",
                agent_name=agent_name,
                property_address=property_address,
                caller_phone=caller_phone,
                is_inbound="Yes" if is_inbound else "No",
                ontario_cities="Toronto, Mississauga, Brampton, Oakville, Burlington, Milton, Georgetown, Vaughan, Richmond Hill, Markham, Ajax, Pickering, Whitby, Oshawa"
            )
            
            
            # Store the pre-formatted prompt
            shared_state.set_preformatted_prompt(formatted_prompt)
            logger.info("[websocket_handler] Prompt pre-formatting complete")
            
            # 3. Warm up the Gemini API with a minimal request
            warmup_config = genai.GenerationConfig(
                max_output_tokens=1,
                temperature=0.0,
            )
            chat.send_message("Hello", generation_config=warmup_config)
            logger.info("[websocket_handler] Gemini warm-up complete")
        except Exception as e:
            logger.warning(f"[websocket_handler] Prompt pre-formatting or warm-up failed: {e}")
    else:
        chat = shared_state.chat

    streaming_config = get_streaming_config()

    # Helper function to process transcription 
    def process_transcription(text):
        if shared_state.is_ai_speaking():
            print(f"[INTERRUPT] Setting interrupt flag for: '{text[:50]}...'")
            shared_state.set_interrupt_ai(True)
            # Don't clear buffer here - let TTS handle it
        else:
            print(f"[NORMAL] Processing normal lead response: '{text[:50]}...'")
            shared_state.set_interrupt_ai(False)
            shared_state.set_clear_command_sent(False)

        shared_state.update_transcript(f"Lead: {text}")
        send_transcript_to_websocket(ws, shared_state.get_stream_sid(), shared_state.get_transcript())
        send_transcript_to_server('human', text)
        # Send immediate "Okay" acknowledgment
        #if shared_state.is_assistance_mode():
         #   acknowledgments = ["Okay", "Got it", "Noted", "I understand", "Understood", "Alright"]
          #  acknowledgment = random.choice(acknowledgments)
           # text_to_speech(text_client, voice, audio_config, acknowledgment, ws, 
            #            shared_state.get_stream_sid(), tts_provider=tts_provider,elevenlabs_client=elevenlabs_client, 
             #           elevenlabs_voice_id=elevenlabs_voice_id, elevenlabs_settings=elevenlabs_settings)
        
        response_text = manage_conversation(chat, text, shared_state, lead_info)

        shared_state.update_transcript(f"AI: {response_text}")
        logger.info(f"AI: {response_text}")
        send_transcript_to_websocket(ws, shared_state.get_stream_sid(), shared_state.get_transcript())
        send_transcript_to_server('ai', response_text)
        # CRITICAL: Clear interrupt flag before starting new AI response
        print(f"[DEBUG] Clearing interrupt flag before new AI response")
        shared_state.set_interrupt_ai(False)
        shared_state.set_clear_command_sent(False)
        shared_state.set_ai_speaking(True)
        
        #  CREATE TTS THREAD 
        def tts_worker():
            try:
                text_to_speech(
                    text_client, voice, audio_config, response_text, ws, 
                    shared_state.get_stream_sid(), tts_provider=tts_provider, 
                    elevenlabs_client=elevenlabs_client, 
                    elevenlabs_voice_id=elevenlabs_voice_id, 
                    elevenlabs_settings=elevenlabs_settings,
                    cartesia_client=cartesia_client, 
                    cartesia_voice_id=cartesia_voice_id, 
                    shared_state=shared_state
                )

                GRACE_PERIOD_SECONDS = 0.2 # Start with 200ms, experiment with 0.1-0.3s
                start_grace_time = time.time()
                while time.time() - start_grace_time < GRACE_PERIOD_SECONDS:
                    if shared_state.should_interrupt_ai():
                        print(f"[DEBUG] Interruption detected during grace period after TTS send.")
                        # If an interrupt is detected here, we don't need to wait the full grace period
                        break
                    time.sleep(0.01) # Short sleep to avoid busy-waiting, yields CPU
            except Exception as e:
                print(f"TTS thread error: {e}")
            finally:
                 # Always clear speaking state when done (including after grace period)
                if shared_state:
                    shared_state.set_ai_speaking(False)
                    print(f"[DEBUG] AI stopped speaking (after grace period)")
        
        # Start TTS in background - main thread continues immediately!
        tts_thread = threading.Thread(target=tts_worker, daemon=True)
        tts_thread.start()
        
        shared_state.increment_step()
    
    def is_strict_confirmation(text):
        text = text.lower().strip()
        
        # Simple exact match confirmations (these are safe to match directly)
        simple_confirmations = [
            "yes", "yep", "yeah", "correct", "right",
            "yes that's right", "yes that's correct", "sounds good",
            "yes correct", "correct yes", "that is correct", "that is right"
        ]
        
        # Check for exact matches first
        if text in simple_confirmations:
            return True
            
        # Check for starts with confirmations
        starts_with_confirmations = [
            "yes ", "yeah ", "yep ", "correct ", "that's right", "that's correct"
        ]
        if any(text.startswith(start) for start in starts_with_confirmations) and len(text) < 20:
            return True
        
        # Enhanced handling for filler words before confirmations
        filler_words = ["uh", "um", "er", "hmm", "well", "so", "like", "you know"]
        
        # Check if text starts with any filler word
        for filler in filler_words:
            # If text starts with a filler word
            if text.startswith(filler + " "):
                # Check the rest of the text for confirmation phrases
                rest_of_text = text[len(filler):].strip()
                # Recursively check if the rest of the text is a confirmation
                if is_strict_confirmation(rest_of_text):
                    return True
        
        # More comprehensive patterns for confirmations with filler words
        confirmation_patterns = [
            # Match "uh yeah" style responses
            r"^(uh|um|er|hmm|well|so|like)\s+(yes|yeah|yep|correct|right)[\s\.,!]?$",
            
            # Match "uh yeah that's correct" style responses
            r"^(uh|um|er|hmm|well|so|like)\s+(yes|yeah|yep|correct|right)[\s,]+that\'s[\s]*(correct|right)[\s\.,!]?$",
            
            # Match "uh that's correct" style responses
            r"^(uh|um|er|hmm|well|so|like)\s+that\'s[\s]*(correct|right)[\s\.,!]?$",
            
            # Basic confirmation patterns
            r"^(yes|yeah|yep|correct)[\.,!]?$",  # Just the word with optional punctuation
            r"^(yes|yeah|yep|correct),?\s+(it is|that's right|that's correct)[\s\.,!]?$",
            r"^that's\s+(correct|right)[\s\.,!]?$",  # That's correct/right
            r"^that\s+is\s+(correct|right)[\s\.,!]?$",  # That is correct/right
            r"^(yes|yeah|yep),?\s+that's\s+(correct|right)[\s\.,!]?$",  # Yes that's correct/right
            
            # Match "yeah that's" style partial confirmations
            r"^(yes|yeah|yep)\s+that\'s\b.*$"
        ]
        
        return any(re.match(pattern, text) for pattern in confirmation_patterns)

    def is_strict_rejection(text):
        text = text.lower().strip()
        
        # Simple exact match rejections
        simple_rejections = [
            "no", "nope", "incorrect", "wrong", 
            "that's wrong", "that's not right", "that's incorrect",
            "no that's wrong", "no that's not right", "that is not correct"
        ]
        
        # Check for exact matches first
        if text in simple_rejections:
            return True
            
        # Check for starts with rejections
        starts_with_rejections = [
            "no ", "nope ", "incorrect ", "that's wrong", "that's not", "not correct"
        ]
        if any(text.startswith(start) for start in starts_with_rejections) and len(text) < 30:
            return True
        
        # Enhanced handling for filler words before rejections
        filler_words = ["uh", "um", "er", "hmm", "well", "so", "like", "you know"]
        
        # Check if text starts with any filler word
        for filler in filler_words:
            # If text starts with a filler word
            if text.startswith(filler + " "):
                # Check the rest of the text for rejection phrases
                rest_of_text = text[len(filler):].strip()
                # Recursively check if the rest of the text is a rejection
                if is_strict_rejection(rest_of_text):
                    return True
        
        # More comprehensive patterns for rejections with filler words
        rejection_patterns = [
            # Match "uh no" style responses
            r"^(uh|um|er|hmm|well|so|like)\s+(no|nope|incorrect|wrong)[\s\.,!]?$",
            
            # Match "uh no that's wrong" style responses
            r"^(uh|um|er|hmm|well|so|like)\s+(no|nope)[\s,]+that\'s[\s]*(wrong|incorrect|not right|not correct)[\s\.,!]?$",
            
            # Match "uh that's not correct" style responses
            r"^(uh|um|er|hmm|well|so|like)\s+that\'s[\s]*(wrong|incorrect|not right|not correct)[\s\.,!]?$",
            r"^(uh|um|er|hmm|well|so|like)\s+that[\s]+is[\s]*(wrong|incorrect|not right|not correct)[\s\.,!]?$",
            r"^(uh|um|er|hmm|well|so|like)\s+that\'s[\s]+not[\s]*(right|correct)[\s\.,!]?$",
            r"^(uh|um|er|hmm|well|so|like)\s+that[\s]+is[\s]+not[\s]*(right|correct)[\s\.,!]?$",
            
            # Basic rejection patterns
            r"^(no|nope)[\.,!]?$",  # Just the word with optional punctuation
            r"^(no|nope),?\s+(that's|that is)\s+(wrong|incorrect|not right)[\s\.,!]?$",  # No that's wrong
            r"^that's\s+(wrong|incorrect|not right|not correct)[\s\.,!]?$",  # That's wrong
            r"^that\s+is\s+(wrong|incorrect|not right|not correct)[\s\.,!]?$",  # That is wrong
            r"^(no|nope),?\s+(it's|it is)\s+(wrong|incorrect|not right)[\s\.,!]?$",  # No it's wrong
            r"^that\'s\s+not\s+(right|correct)[\s\.,!]?$",  # That's not right
            r"^that\s+is\s+not\s+(right|correct)[\s\.,!]?$"  # That is not right/correct
        ]
        
        return any(re.match(pattern, text) for pattern in rejection_patterns)

    def process_spelling_mode(updated_buffer, is_confirmation, is_rejection):
        spelling_type = shared_state.get_spelling_type()
        
        # Check for recently processed transcriptions (to avoid processing duplicates)
        last_spelling_processed_time = shared_state.get_last_spelling_processed_time()
        current_time = time.time()
        if last_spelling_processed_time and (current_time - last_spelling_processed_time) < 1.0:
            return  # Skip processing this likely continuation

        # === IMMEDIATE PROCESSING CASES (no timeout) ===
        
        # Case 1: Initial name collection - always process immediately
        if spelling_type == "name_collection":
            final_text = updated_buffer
            shared_state.clear_buffered_transcription()
            process_transcription(final_text)
            shared_state.set_last_spelling_processed_time(time.time())
            return
        
        # Case 2: Confirmations - process immediately and exit spelling mode
        if is_confirmation:
            shared_state.set_spelling_mode(False)
            shared_state.set_spelling_type(None)
            final_text = updated_buffer
            shared_state.clear_buffered_transcription()
            process_transcription(final_text)
            shared_state.set_last_spelling_processed_time(time.time())
            return
        
        # Case 3: Rejections - process immediately but stay in spelling mode
        if is_rejection:
            final_text = updated_buffer
            shared_state.clear_buffered_transcription()
            process_transcription(final_text)
            shared_state.set_last_spelling_processed_time(time.time())
            return
        
        # Case 4: Email with domain completion indicators - process immediately
        if spelling_type == "email":
            email_completion_indicators = [
                "dot com", "dot us", "dot org", "dot net", "dot io", "dot edu", "dot gov", 
                "dot ca", "dot co", "dot uk", "dot au", "dot de", "dot in",
                ".com", ".us", ".org", ".net", ".io", ".edu", ".gov", ".ca", ".co", 
                ".uk", ".au", ".de", ".in", "gmail", "yahoo", "hotmail", "outlook",
                "aol", "icloud", "protonmail"
            ]
            words = updated_buffer.lower().split()
            last_chunk = " ".join(words[-5:] if len(words) >= 5 else words)
            
            if any(indicator in last_chunk for indicator in email_completion_indicators):
                final_text = updated_buffer
                shared_state.clear_buffered_transcription()
                process_transcription(final_text)
                shared_state.set_last_spelling_processed_time(time.time())
                return
        
        # === DELAYED PROCESSING CASES (with timeout) ===
        
        # 1. Cancel any existing timer first
        shared_state.cancel_pending_timer()
        
        # 2. Define the processing callback (same for all spelling types)
        def process_spelling_transcription():
            final_text = shared_state.get_buffered_transcription()
            if final_text and final_text.strip():
                shared_state.clear_buffered_transcription()
                process_transcription(final_text)
                shared_state.set_last_spelling_processed_time(time.time())
            else:
                shared_state.clear_buffered_transcription()
        
        # 3. Determine appropriate timeout based on spelling type and content
        timeout = 1.0  # Default timeout
        
        if spelling_type == "email":
            # Email: longer timeout to allow for full email address
            timeout = 6.5
            
        elif spelling_type == "phone":
            # Phone: dynamic timeout based on digit count
            digits_only = ''.join(char for char in updated_buffer if char.isdigit())
            digit_count = len(digits_only)
            
            if digit_count >= 10:  # Complete phone number detected
                timeout = 0.8  # Process quickly when we likely have a complete number
            elif is_rejection:  # User rejected but hasn't provided correction yet
                timeout = 1.0  # Short timeout after rejections
            else:  # Still collecting digits
                timeout = 1.5  # Moderate timeout while collecting
                
        elif spelling_type == "name":
            # Name: check if person is about to spell
            is_about_to_spell = any(phrase in updated_buffer.lower() for phrase in 
                                ["that would be", "that's", "it's", "spelled", "spelt"])
            if is_about_to_spell:
                timeout = 1.5  # Longer timeout when about to spell
            else:
                timeout = 0.8  # Shorter timeout for active spelling
        
        # 4. Set the timer
        timer = threading.Timer(timeout, process_spelling_transcription)
        timer.daemon = True
        shared_state.set_pending_timer(timer)
        timer.start()
    

    def on_transcription_response(response):
        if not response.results:
            return
        result = response.results[0]
        if not result.alternatives:
            return
        transcription = result.alternatives[0].transcript
        is_final = result.is_final
        confidence = getattr(result.alternatives[0], 'confidence', 0.0)


        if len(transcription.strip()) > 3:
            logger.info(f"Transcription: {transcription} (conf: {confidence:.2f}, final: {is_final})")
        
        if not is_final or not transcription.strip():
            return
        
        # Track state before processing
        previous_spelling_mode = shared_state.is_spelling_mode()
        previous_assistance_mode = shared_state.is_assistance_mode()
        
        # Check for confirmations and rejections
        is_confirmation = is_strict_confirmation(transcription)
        is_rejection = is_strict_rejection(transcription)
        
        # SELECTIVE BUFFERING - only use buffer for special modes
        # For special modes only: update the buffer
        if shared_state.is_spelling_mode() or shared_state.is_assistance_mode():
            current_buffer = shared_state.get_buffered_transcription()
            updated_buffer = f"{current_buffer} {transcription}" if current_buffer else transcription
            shared_state.set_buffered_transcription(updated_buffer)
        else:
            # For direct processing, no need to maintain a buffer
            updated_buffer = transcription
        
        # ======= HANDLE DIFFERENT MODES =======
        
        # 1. ANY SPELLING MODE (consolidated)
        if shared_state.is_spelling_mode():
            process_spelling_mode(updated_buffer, is_confirmation, is_rejection)
            return
        
        # 2. ASSISTANCE MODE
        elif shared_state.is_assistance_mode():
            # Only use artificial delays for immediate completion phrases
            completion_phrases = [
                "no that's it", "that's it", "that's all", "no thanks", 
                "nothing else", "no that's all", "that's fine", 
                "no thank you", "i'm good", "that should do it", "thanks", "thank you"
            ]
            
            is_complete = any(phrase in updated_buffer.lower() for phrase in completion_phrases) or \
                    updated_buffer.lower().strip() == "no" or \
                    updated_buffer.lower().strip() in ["thanks", "thank you"]

            if updated_buffer.lower().strip() == "yeah":
                words = updated_buffer.split()
                if len(words) == 1:
                    is_complete = True

            if is_complete:
                logger.info(f"[websocket_handler] Immediate completion: '{updated_buffer}'")
                shared_state.cancel_pending_timer()
                shared_state.set_assistance_mode(False)
                final_text = updated_buffer
                shared_state.clear_buffered_transcription()
                process_transcription(final_text)
                return
            
            # Otherwise, just buffer and let VAD handle the processing
            logger.info(f"[websocket_handler] Buffering for VAD processing: '{transcription}'")
            return
        
        # 3. DIRECT PROCESSING
        else:
            # First check if we're exiting a mode
            if previous_spelling_mode:
                shared_state.set_spelling_mode(False)
                logger.info("[websocket_handler] Exiting spelling mode - standard input detected")
                from speech_processing import update_streaming_config
                update_streaming_config(bridge, is_spelling_mode=False)
            
            # Update streaming config if spelling mode changed
            if previous_spelling_mode != shared_state.is_spelling_mode():
                from speech_processing import update_streaming_config
                update_streaming_config(bridge, is_spelling_mode=shared_state.is_spelling_mode())
            
            # Process directly without buffering or delay
            logger.info("[websocket_handler] Direct processing path")
            process_transcription(transcription)
                    
    bridge = SpeechClientBridge(speech_client, streaming_config, on_transcription_response, ws, lead_id, lead_name, lead_email, shared_state)
    bridge.set_process_transcription_callback(process_transcription)
    threading.Thread(target=bridge.start).start()
    
    while True:
        try:
            message = ws.receive(timeout=1)
            if message is None:
                if shared_state.get_notify_call_completed():
                    #print("Sending call_completed notification to Node.js server")
                    ws.send(json.dumps({
                        "event": "call_completed",
                        "call_sid": shared_state.get_call_sid()
                    }))
                    shared_state.set_notify_call_completed(False)  # Reset the flag
                    break  # Exit the loop after notifying
                continue

            data = json.loads(message)
            if data["event"] in ("connected", "start"):
                logger.info(f"Media WS: Received event '{data['event']}': {message}")
                if data["event"] == "start":
                    shared_state.set_stream_sid(data["streamSid"])
                    logger.info(f"StreamSid: {shared_state.get_stream_sid()}")
                    if shared_state.get_is_inbound():
                        # retrieve actual realtor name that was stored in call_routes
                        realtor_name = shared_state.get_realtor_name()
                        greeting = f"Hello {lead_info.get('name', 'there')}, this is John, an AI assistant answering on behalf of {realtor_name}. How can I help you today?"
                        send_transcript_to_server('ai', greeting)
                        shared_state.set_ai_speaking(True)
                        text_to_speech(
                            text_client, voice, audio_config, greeting, ws, 
                            shared_state.get_stream_sid(), 
                            tts_provider=tts_provider, elevenlabs_client=elevenlabs_client,
                            elevenlabs_voice_id=elevenlabs_voice_id, elevenlabs_settings=elevenlabs_settings,
                            cartesia_client=cartesia_client, cartesia_voice_id=cartesia_voice_id, shared_state=shared_state
                        )
                    continue
            if data["event"] == "media":
                media = data["media"]
                chunk = base64.b64decode(media["payload"])
                bridge.add_request(chunk)
            if data["event"] == "stop":
                logger.info(f"Media WS: Received event 'stop': {message}")
                bridge.terminate()
                break
        except Exception as e:
            logger.info(f"Error in WebSocket communication: {e}")
            break

    #print("WebSocket loop ended, cleaning up...")
    bridge.terminate()
    logger.info("WebSocket connection closed")

def send_transcript_to_websocket(ws, stream_sid, message):
    try:
        if isinstance(message, list):
            # If it's a list, assume it's the full transcript and get the last messages
            lead_messages = [msg for msg in message if msg.startswith("Lead:")]
            ai_messages = [msg for msg in message if msg.startswith("AI:")]
            
            last_lead_message = lead_messages[-1].split("Lead: ", 1)[1] if lead_messages else ""
            last_ai_message = ai_messages[-1].split("AI: ", 1)[1] if ai_messages else ""
        else:
            # If it's a single message, process it directly
            if message.startswith("Lead: "):
                last_lead_message = message.split("Lead: ", 1)[1]
                last_ai_message = ""
            elif message.startswith("AI: "):
                last_lead_message = ""
                last_ai_message = message.split("AI: ", 1)[1]
            else:
                last_lead_message = ""
                last_ai_message = ""
        
        ws.send(json.dumps({
            "event": "transcript",
            "streamSid": stream_sid,
            "data": {
                "lead": last_lead_message,
                "ai": last_ai_message
            }
        }))
        #lead_preview = last_lead_message[:30] + "..." if len(last_lead_message) > 30 else last_lead_message
        #ai_preview = last_ai_message[:30] + "..." if len(last_ai_message) > 30 else last_ai_message
        #print(f"Transcript update: Lead: {lead_preview}, AI: {ai_preview}")
    except Exception as e:
        print(f"Error sending transcript: {e}")

def send_transcript_to_server(speaker, text):
    try:
        print(f"[DEMO] Sending to server: {speaker}: {text}")
        response = requests.post('http://transcript-viewer:3001/transcript', 
                               json={'speaker': speaker, 'text': text})
        print(f"[DEMO] Server response: {response.status_code}")
        if response.status_code != 200:
            print(f"[DEMO] Server error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("[DEMO] Could not connect to demo server - is it running?")
    except requests.exceptions.Timeout:
        print("[DEMO] Demo server timeout")
    except Exception as e:
        print(f"[DEMO] Error sending to demo server: {e}")