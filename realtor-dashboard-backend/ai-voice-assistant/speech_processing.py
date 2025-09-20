# Real-time speech processing engine for bidirectional voice conversations.
#
# TTS Processing: Streams audio chunks via WebSocket using multiple providers (Google, ElevenLabs, Cartesia)
# with provider failover and dynamic voice selection. Handles audio buffering, chunking, and real-time delivery.
#
# Speech-to-Text: Continuous transcription using Google Speech API with streaming recognition,
# buffering partial results and detecting speech boundaries for natural conversation flow.
#
# WebRTC Integration: Manages bidirectional audio streams over WebSocket connections, handles
# Twilio media streams, audio format conversion (mulaw/PCM), and real-time audio synchronization.
#
# Interruption System: Detects user speech during AI responses, implements voice activity detection,
# and manages conversation turn-taking with silence detection and audio queue management.

import os
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
from google.oauth2 import service_account
import base64
import queue
import threading
import json
import time
import google.api_core.exceptions
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from elevenlabs import stream
import audioop
from cartesia import Cartesia
import webrtcvad


# Import speech contexts to reduce duplication
from speech_contexts import (
    create_base_speech_contexts,
    create_spelling_mode_contexts,
    create_assistance_mode_contexts,
    create_first_response_contexts
)

class TTSProvider:
    GOOGLE = "google"
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"

def initialize_speech_clients():
    speech_credentials = service_account.Credentials.from_service_account_file(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_SPEECH'))
    text_credentials = service_account.Credentials.from_service_account_file(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_TEXT'))

    speech_client = speech.SpeechClient(credentials=speech_credentials)
    text_client = texttospeech.TextToSpeechClient(credentials=text_credentials)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Neural2-D")
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MULAW, sample_rate_hertz=8000)

    elevenlabs_client = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
    elevenlabs_voice_id = os.getenv('ELEVENLABS_VOICE_ID')
    elevenlabs_settings = VoiceSettings(
        stability=0.4,
        similarity_boost=0.82,
        style=0.0,
        use_speaker_boost=True
    )

    cartesia_client = Cartesia(api_key=os.getenv('CARTESIA_API_KEY'))
    cartesia_voice_id = os.getenv('CARTESIA_VOICE_ID')

    return speech_client, text_client, voice, audio_config, elevenlabs_client, elevenlabs_voice_id, elevenlabs_settings, cartesia_client, cartesia_voice_id

class WebRTCVADProcessor:
    # WebRTC VAD processor for real-time voice activity detection
    
    def __init__(self, aggressiveness=0, sample_rate=8000, frame_duration_ms=30):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        
        # Calculate frame size in samples
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        # Each sample is 2 bytes (16-bit PCM)
        self.frame_bytes = self.frame_size * 2
        
        # Buffer for accumulating audio data
        self.audio_buffer = b""
        
        # Simple smoothing: require 2 consecutive voice frames
        self.last_frame_was_voice = False
        
        print(f"[WebRTC VAD] Initialized with aggressiveness={aggressiveness}, "
              f"sample_rate={sample_rate}, frame_duration={frame_duration_ms}ms, "
              f"frame_size={self.frame_size} samples ({self.frame_bytes} bytes)")
    
    def process_audio(self, mulaw_data):
        # Process incoming μ-law audio data and return voice activity decision
        try:
            # Convert μ-law to linear PCM (8kHz, 16-bit) - no resampling needed!
            linear_pcm = audioop.ulaw2lin(mulaw_data, 2)
            
            # Add to buffer
            self.audio_buffer += linear_pcm
            
            # Process complete frames
            voice_detected = False
            while len(self.audio_buffer) >= self.frame_bytes:
                # Extract one frame
                frame = self.audio_buffer[:self.frame_bytes]
                self.audio_buffer = self.audio_buffer[self.frame_bytes:]
                
                # Run VAD on this frame
                is_voice = self.vad.is_speech(frame, self.sample_rate)
                
                if not hasattr(self, 'voice_frame_count'):
                    self.voice_frame_count = 0
                
                if is_voice:
                    self.voice_frame_count += 1
                else:
                   self.voice_frame_count = 0
                
                # Require 3 consecutive voice frames to trigger
                voice_detected = self.voice_frame_count >= 3
            
            return voice_detected
            
        except Exception as e:
            print(f"[WebRTC VAD] Error processing audio: {e}")
            return False
    
    def set_aggressiveness(self, level):
        # Update VAD aggressiveness level (0-3)
        try:
            self.vad.set_mode(level)
            print(f"[WebRTC VAD] Aggressiveness set to {level}")
        except Exception as e:
            print(f"[WebRTC VAD] Error setting aggressiveness: {e}")

class SpeechClientBridge:
    def __init__(self, client, streaming_config, callback, ws, lead_id, lead_name, lead_email, shared_state):
        self.client = client
        self.streaming_config = streaming_config
        self.callback = callback
        self.ws = ws
        self.lead_id = lead_id
        self.lead_name = lead_name
        self.lead_email = lead_email
        self.queue = queue.Queue()
        self.closed = threading.Event()
        self.ended = False
        self.shared_state = shared_state
        self.call_sid = shared_state.get_call_sid()
        print(f"[DEBUG] Created bridge for call SID: {self.call_sid}")

        # Audio processing time tracking
        self.total_audio_seconds = 0
        self.chunk_start_time = None
        self.is_processing_audio = False
        self.voice_activity_detected = False
        self.voice_activity_durations = []
        self.should_restart = False
        self.restart_in_progress = False
        self.audio_buffer = queue.Queue()  # Buffer to store audio during restart
        self.last_vad_interrupt_time = 0  # Prevent rapid-fire interrupts
        self.vad_interrupt_cooldown = 2.0  # Minimum seconds between VAD interrupts

        self.webrtc_vad = WebRTCVADProcessor(
            aggressiveness=2,  # Start with level 1
            sample_rate=8000,  # Use native 8kHz - no resampling needed!
            frame_duration_ms=30  # 30ms frames as requested
        )
        
        print(f"[WebRTC VAD] Initialized for call {self.call_sid}")
        
        self.last_user_vad_state = False
        self.user_silence_timer = None
        self.process_transcription_callback = None
    
    def set_process_transcription_callback(self, callback):
        # Set the callback function for direct processing
        self.process_transcription_callback = callback

    def process_universal_vad(self, buffer):
        # Universal WebRTC VAD for both interrupts and turn-taking
        try:
            # Calculate audio level
            linear_pcm = audioop.ulaw2lin(buffer, 2)
            import struct
            samples = struct.unpack('<' + 'h' * (len(linear_pcm) // 2), linear_pcm)
            rms = (sum(s*s for s in samples) / len(samples)) ** 0.5
            
            voice_detected = False
            MINIMUM_AUDIO_LEVEL = 1200
            
            if rms > MINIMUM_AUDIO_LEVEL:
                voice_detected = self.webrtc_vad.process_audio(buffer)
            
            # BRANCH 1: AI IS SPEAKING - Handle Interrupts
            if self.shared_state.is_ai_speaking():
                if voice_detected and not self.shared_state.should_interrupt_ai():
                    current_time = time.time()
                    
                    # Apply cooldown to prevent rapid-fire interrupts
                    if (current_time - self.last_vad_interrupt_time) > self.vad_interrupt_cooldown:
                        print(f"[Universal VAD] Voice detected - interrupting AI")
                        
                        self.shared_state.set_interrupt_ai(True)
                        self.last_vad_interrupt_time = current_time
                        
                        # Send clear command to Twilio
                        try:
                            stream_sid = self.shared_state.get_stream_sid()
                            if stream_sid:
                                self.ws.send(json.dumps({
                                    "event": "clear",
                                    "streamSid": stream_sid
                                }))
                                self.shared_state.set_clear_command_sent(True)
                                print("[Universal VAD] Clear command sent")
                        except Exception as e:
                            print(f"[Universal VAD] Error sending clear: {e}")
            
            # BRANCH 2: AI NOT SPEAKING - Handle Turn-Taking
            else:
                if voice_detected != self.last_user_vad_state:
                    if voice_detected:
                        # User started speaking
                        print(f"[Universal VAD] User started speaking")
                        self.shared_state.set_user_is_speaking(True)
                        self.shared_state.set_user_silence_detected(False)
                        
                        # Cancel any existing silence timer
                        if self.user_silence_timer:
                            self.user_silence_timer.cancel()
                            self.user_silence_timer = None
                            
                    else:
                        # User stopped speaking - start silence timer
                        print(f"[Universal VAD] User stopped speaking - starting silence timer")
                        self.shared_state.set_user_is_speaking(False)
                        
                        def on_silence_timeout():
                            if self.process_transcription_callback:
                                final_text = self.shared_state.get_buffered_transcription()
                                if final_text and final_text.strip():
                                    print(f"[Universal VAD] Processing after silence: '{final_text[:50]}...'")
                                    self.shared_state.clear_buffered_transcription()
                                    self.process_transcription_callback(final_text)
                        
                        self.user_silence_timer = threading.Timer(1.2, on_silence_timeout)
                        self.user_silence_timer.daemon = True
                        self.user_silence_timer.start()
                
                # Update last state for turn-taking
                self.last_user_vad_state = voice_detected
                
        except Exception as e:
            print(f"[Universal VAD] Error: {e}")

    def start(self):
        restart_timer = threading.Timer(120, self.prepare_restart)
        restart_timer.daemon = True
        restart_timer.start()

        stream = self.generator()
        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in stream
        )
        responses = self.client.streaming_recognize(self.streaming_config, requests)
        self.process_responses_loop(responses)
    
    def prepare_restart(self):
        if not self.ended:
            print("Preparing to restart stream before hitting limit...")
            self.should_restart = True
            # Start a short buffer collection period
            self.restart_in_progress = True
            
            # Start a new stream in a separate thread
            threading.Thread(target=self.start_new_stream).start()
    
    def start_new_stream(self):
        # Small delay to ensure we have some buffer
        time.sleep(0.5)
        
        # Create a new stream with the same parameters
        stream = self.generator(use_buffer=True)  # Use audio buffer during restart
        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in stream
        )
        
        try:
            # Start new recognition session
            responses = self.client.streaming_recognize(self.streaming_config, requests)
            
            # Complete the restart process
            self.should_restart = False
            self.restart_in_progress = False
            
            # Process responses from the new stream
            self.process_responses_loop(responses)
        except Exception as e:
            print(f"Error in new stream: {e}")
            self.restart_in_progress = False
            
            # If restarting failed, try again after a brief delay
            if not self.ended:
                time.sleep(2)
                threading.Thread(target=self.start_new_stream).start()
    
    def terminate(self):
        self.ended = True
        self.queue.put(None)
        self.shared_state.set_call_ended(True)
        if hasattr(self, 'user_silence_timer') and self.user_silence_timer:
            self.user_silence_timer.cancel()
            self.user_silence_timer = None
            print("[Universal VAD] Cleaned up silence timer")
    
    def add_request(self, buffer):
        # Start tracking time when we receive audio
        if not self.is_processing_audio:
            self.is_processing_audio = True
            self.chunk_start_time = time.time()
        
        # Universal VAD processing
        self.process_universal_vad(buffer)
        
        if self.restart_in_progress:
            self.audio_buffer.put(bytes(buffer), block=False)
            
        self.queue.put(bytes(buffer), block=False)

    def process_responses_loop(self, responses):
        try:
            for response in responses:
                if self.ended:
                    break
                
                # Check for voice activity events
                if response.speech_event_type == speech.StreamingRecognizeResponse.SpeechEventType.SPEECH_ACTIVITY_BEGIN:
                    # Reset the chunk start time when speech activity begins
                    self.chunk_start_time = time.time()
                    self.voice_activity_detected = True
                    
                
                elif response.speech_event_type == speech.StreamingRecognizeResponse.SpeechEventType.SPEECH_ACTIVITY_END:
                    if self.voice_activity_detected:
                        self.voice_activity_detected = False
                        # Only update time if we're processing and voice activity was detected
                        if self.is_processing_audio and self.chunk_start_time is not None:
                            self.is_processing_audio = False
                            self.chunk_start_time = None
                            
                if response.results and response.results[0].alternatives:
                    transcription = response.results[0].alternatives[0].transcript
                    if transcription.strip():  # Only process non-empty transcriptions
                        self.callback(response)
                else:
                    pass
        except google.api_core.exceptions.OutOfRange as e:
            if "Exceeded maximum allowed stream duration" in str(e) and not self.ended:
                print("Stream duration limit reached unexpectedly")
                if not self.restart_in_progress:
                    # Trigger emergency restart
                    threading.Thread(target=self.prepare_restart).start()
            else:
                pass
                print(f"Stream ended: {e}")
        except Exception as e:
            print(f"Error in process_responses_loop: {e}")   

    def generator(self, use_buffer=False):
        queue_to_use = self.audio_buffer if use_buffer else self.queue
        while not self.ended:
            try:
                chunk = queue_to_use.get(timeout=1.5)  # Short timeout for responsiveness
            except queue.Empty:
                if use_buffer and not self.restart_in_progress:
                    # If using buffer and restart is complete, switch to main queue
                    return self.generator(use_buffer=False)
                continue

            if chunk is None:
                print("Received None chunk, ending generator")
                return
            data = [chunk]
            while True:
                try:
                    chunk = self.queue.get(block=False)
                    if chunk is None:
                        print("Received None chunk, ending generator")
                        return
                    data.append(chunk)
                except queue.Empty:
                    break
            yield b"".join(data)

def get_streaming_config():
    speech_contexts = create_base_speech_contexts()
    
    return speech.StreamingRecognitionConfig(
        config=speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            language_code="en-CA",
            model="phone_call",
            use_enhanced=True,
            enable_automatic_punctuation=False,
            diarization_config=speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=2,
                max_speaker_count=2
            ),
            speech_contexts=speech_contexts,
            profanity_filter=False,
            audio_channel_count=1,
            enable_word_time_offsets=True,
            enable_word_confidence=False, 
        ),
        interim_results=True,
        single_utterance=False,
        enable_voice_activity_events=True
    )

def update_streaming_config(client_bridge, is_spelling_mode=False):
    # Updates the streaming config based on the current mode (spelling, assistance, etc.)
    
    # Set automatic punctuation (normally off for spelling mode, on otherwise)
    client_bridge.streaming_config.config.enable_automatic_punctuation = not is_spelling_mode
    
    # Determine which set of speech contexts to use based on the current mode
    if is_spelling_mode:
        spelling_type = client_bridge.shared_state.get_spelling_type()
        client_bridge.streaming_config.config.speech_contexts = create_spelling_mode_contexts(spelling_type)
    elif client_bridge.shared_state.is_assistance_mode():
        print("[speech_processing] Assistance mode detected - boosting technical term recognition")
        client_bridge.streaming_config.config.speech_contexts = create_assistance_mode_contexts()
    elif client_bridge.shared_state.is_first_response_mode():
        print("[speech_processing] First response mode detected - boosting technical recognition")
        client_bridge.streaming_config.config.speech_contexts = create_first_response_contexts()
    else:
        # Standard mode - revert to base contexts
        client_bridge.streaming_config.config.speech_contexts = create_base_speech_contexts()

def text_to_speech(text_client, voice, audio_config, text, ws, stream_sid, tts_provider=TTSProvider.GOOGLE,elevenlabs_client=None, elevenlabs_voice_id=None, elevenlabs_settings=None, cartesia_client=None, cartesia_voice_id=None, shared_state=None ):
    try:
        # CRITICAL: Clear interrupt flag at start of NEW AI speech segment
        # This ensures each TTS call starts with a clean slate
        if shared_state:
            print(f"[DEBUG] Starting TTS - clearing interrupt flag as failsafe")
            shared_state.set_interrupt_ai(False)
            shared_state.set_ai_speaking(True)

        # Early exit check (should rarely trigger now due to above reset)
        if shared_state and shared_state.should_interrupt_ai():
            print("AI speech interrupted before TTS started")
            shared_state.set_ai_speaking(False)
            return
        if tts_provider == TTSProvider.GOOGLE:
            if shared_state:
                shared_state.set_ai_speaking(True)
                print("AI started speaking with Google TTS")
            ssml_text = f"""
            <speak>
                <prosody rate="0.95" pitch="+1st" volume="+2dB">
                    {text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}
                </prosody>
            </speak>
            """
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)
            response = text_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )

            # Get the full audio content (bytes)

            audio_content = response.audio_content

            # Define a chunk size for sending over the WebSocket

            chunk_size = 320 # Larger chunk size for better throughput
            # Iterate through the audio content in chunks
            chunk_count = 0
            total_chunks = (len(audio_content) + chunk_size - 1) // chunk_size

            for i in range(0, len(audio_content), chunk_size):
                if shared_state and shared_state.should_interrupt_ai():
                    print("AI speech interrupted by lead")
                    try:
                        clear_message = {
                        "event": "clear",
                        "streamSid": stream_sid
                        }
                        ws.send(json.dumps(clear_message))
                        print("Cleared Twilio audio buffer from TTS")
                    except Exception as e:
                        print(f"Error clearing Twilio buffer: {e}")
                    shared_state.set_ai_speaking(False)
                    print("AI speaking state cleared due to interrupt")
                    return

                chunk = audio_content[i:i + chunk_size]

                # Encode the chunk in Base64

                audio_content_base64 = base64.b64encode(chunk).decode('utf-8')
                        
                # FIXED: Moved WebSocket message inside the sub-chunk loop
                ws_message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": audio_content_base64
                    }
                }
                        
                try:
                    # Send the audio chunk to the WebSocket
                    ws.send(json.dumps(ws_message))
                    chunk_count += 1
                    time.sleep(0.015)  # 2ms delay - minimal since streaming provides natural timing
                            
                except Exception as e:
                    print(f"Error sending audio chunk {chunk_count}: {e}")
            
            print(f"Sent Google Streaming TTS audio in {chunk_count} chunks")
            if shared_state:
                shared_state.set_ai_speaking(False)
                print("AI finished speaking normally with Google TTS")

        # ElevenLabs implementation commented out in the original code
        elif tts_provider == TTSProvider.ELEVENLABS:
            audio_stream = elevenlabs_client.text_to_speech.stream(
                text=text,
                voice_id=elevenlabs_voice_id,
                voice_settings=elevenlabs_settings,
                model_id="eleven_multilingual_v2",
                output_format="pcm_16000",
                optimize_streaming_latency=1  # Good balance for phone calls
            )
            
            # Buffer for collecting small chunks before sending
            chunk_buffer = b""
            target_chunk_size = 160  # ~40ms of ulaw audio at 8kHz (8000 Hz * 0.04s * 1 byte = 320 bytes)
            chunk_count = 0
            #volume_boost = 1.0
            
            for pcm_chunk in audio_stream:
                if shared_state and shared_state.should_interrupt_ai():
                    print("ElevenLabs speech interrupted by lead")
                    audio_stream.close()
                    return
                
                chunk_buffer += pcm_chunk
                
                # Send when buffer reaches target size or larger
                while len(chunk_buffer) >= target_chunk_size:
                    # CHECK FOR INTERRUPTION BEFORE SENDING EACH BUFFERED CHUNK
                    if shared_state and shared_state.should_interrupt_ai():
                        audio_stream.close()
                        print(f"ElevenLabs TTS interrupted during buffer processing at chunk {chunk_count}")
                        return
                    
                    # Extract target-sized chunk
                    chunk_to_send = chunk_buffer[:target_chunk_size]
                    chunk_buffer = chunk_buffer[target_chunk_size:]
                    
                    # Boost volume on PCM data
                    #boosted_pcm = audioop.mul(chunk_to_send, 2, volume_boost)
                    
                    # Resample from 16kHz to 8kHz for Twilio
                    resampled_pcm, _ = audioop.ratecv(chunk_to_send, 2, 1, 16000, 8000, None)
                    
                    # Convert to mulaw for Twilio
                    mulaw_chunk = audioop.lin2ulaw(resampled_pcm, 2)
                    # Encode and send
                    audio_content_base64 = base64.b64encode(mulaw_chunk).decode('utf-8')
                
                    # Use the simple format that Twilio expects
                    ws_message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": audio_content_base64
                        }
                    }
                
                    try:
                        # Send the audio chunk to the WebSocket
                        ws.send(json.dumps(ws_message))
                        chunk_count += 1   
                        time.sleep(0.002)  # 2ms delay for ~40ms chunks
                    except Exception as e:
                        print(f"Error sending audio chunk {chunk_count}: {e}")
            
            # Send any remaining buffered audio (MOVED OUTSIDE THE LOOP)
            if chunk_buffer and shared_state and not shared_state.should_interrupt_ai():
                #boosted_pcm = audioop.mul(chunk_buffer, 2, volume_boost)
                resampled_pcm, _ = audioop.ratecv(chunk_buffer, 2, 1, 16000, 8000, None)
                mulaw_chunk = audioop.lin2ulaw(resampled_pcm, 2)
                audio_content_base64 = base64.b64encode(mulaw_chunk).decode('utf-8')
                ws_message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": audio_content_base64
                    }
                }
                try:
                    ws.send(json.dumps(ws_message))
                    chunk_count += 1
                except Exception as e:
                    print(f"Error sending final audio chunk: {e}")
            
            print(f"Sent ElevenLabs audio in {chunk_count} buffered chunks")
        
        elif tts_provider == TTSProvider.CARTESIA:
            if shared_state:
                shared_state.set_ai_speaking(True)
                print("AI started speaking with Cartesia")
            
            # Generate audio using Cartesia - this returns a generator
            response = cartesia_client.tts.sse(
                model_id="sonic-2",
                transcript=text,
                voice={
                    "id": cartesia_voice_id,
                },
                language="en",
                output_format={
                    "container": "raw",
                    "encoding": "pcm_mulaw",
                    "sample_rate": 8000,
                },
            )
            
            # Buffer for collecting small chunks before sending
            chunk_buffer = b""
            target_chunk_size = 160  # ~40ms of PCM audio at 8kHz
            chunk_count = 0
            
            # Iterate through the audio generator
            for chunk in response:
                if shared_state and shared_state.should_interrupt_ai():
                    print("Cartesia speech interrupted by lead")
                    shared_state.set_ai_speaking(False)
                    return
                
                # Handle the chunk data properly
                chunk_data = chunk.data
                
                # If chunk_data is a string (base64), decode it to bytes
                if isinstance(chunk_data, str):
                    try:
                        chunk_data = base64.b64decode(chunk_data)
                    except Exception as e:
                        print(f"Error decoding base64 chunk: {e}")
                        continue
                
                chunk_buffer += chunk_data
                
                # Send when buffer reaches target size or larger
                while len(chunk_buffer) >= target_chunk_size:
                    # Extract target-sized chunk
                    if shared_state and shared_state.should_interrupt_ai():
                        print(f"Cartesia TTS interrupted during buffer processing at chunk {chunk_count}")
                        shared_state.set_ai_speaking(False)
                        return
                    
                    chunk_to_send = chunk_buffer[:target_chunk_size]
                    chunk_buffer = chunk_buffer[target_chunk_size:]
                    
                    try:
                        # Encode and send (data is already in mulaw format)
                        audio_content_base64 = base64.b64encode(chunk_to_send).decode('utf-8')
                        
                        # Use the simple format that Twilio expects
                        ws_message = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_content_base64
                            }
                        }
                        
                        # Send the audio chunk to the WebSocket
                        ws.send(json.dumps(ws_message))
                        chunk_count += 1
                        
                        # Small delay to prevent overwhelming the connection
                        time.sleep(0.002)  # 2ms delay
                        
                    except Exception as e:
                        print(f"Error processing/sending Cartesia audio chunk {chunk_count}: {e}")
                        continue
            
            # Send any remaining buffered audio
            if chunk_buffer and shared_state and not shared_state.should_interrupt_ai():
                try:
                    audio_content_base64 = base64.b64encode(chunk_buffer).decode('utf-8')
                    ws_message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": audio_content_base64
                        }
                    }
                    ws.send(json.dumps(ws_message))
                    chunk_count += 1
                except Exception as e:
                    print(f"Error sending final Cartesia audio chunk: {e}")
                            
            print(f"Sent Cartesia audio in {chunk_count} chunks")  
            if shared_state:
                shared_state.set_ai_speaking(False)
                print("AI finished speaking normally")
    except Exception as e:
        print(f"Error in text_to_speech: {e}")
        # CRITICAL: Always clear speaking state on any error
        if shared_state:
            shared_state.set_ai_speaking(False)
            print("AI speaking state cleared due to error")