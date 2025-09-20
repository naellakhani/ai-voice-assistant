# Thread-safe shared state management for voice call sessions.
# Stores conversation context, lead info, call status, and AI state across websocket connections and call processing.

from threading import Lock
from model_managers import SpacyManager

class StateManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls)
            cls._instance.states = {}
            cls._instance.lock = Lock()
        return cls._instance
    
    def get_state(self, call_id):
        with self.lock:
            if call_id not in self.states:
                self.states[call_id] = SharedState()
            return self.states[call_id]
    
    def remove_state(self, call_id):
        with self.lock:
            if call_id in self.states:
                del self.states[call_id]

class SharedState:

    def __init__(self):
        self.full_transcript = []
        self.conversation_step = 0
        self.stream_sid = None
        self.lead_id = None
        self.lock = Lock()
        self.is_inbound = False
        self.phone_number = None
        self.lead_info = None
        self.ngrok_url = None,
        self.temp_lead_data = {}
        self.transcript_processed = False
        self.call_sid = None
        self.call_ended = False
        self._notify_call_completed = False
        self.buffered_transcription = ""
        self.pending_timer = None
        self.last_transcription_time = None
        self.is_automated = False
        self.spelling_mode = False
        self.assistance_mode = False
        self.interrupt_ai = False
        self.ai_is_speaking = False

        # Initialize NLP components using managers
        self.nlp = SpacyManager.get_nlp()
        self.matcher = SpacyManager.get_matcher()

    def update_transcript(self, message):
        with self.lock:
            self.full_transcript.append(message)
            print(f"Transcript updated. Current length: {len(self.full_transcript)}")

    def get_transcript(self):
        with self.lock:
            print(f"Retrieving transcript. Current length: {len(self.full_transcript)}")
            return self.full_transcript
    
    def set_transcript_processed(self, processed):
        with self.lock:
            self.transcript_processed = processed

    def get_transcript_processed(self):
        with self.lock:
            return self.transcript_processed

    def increment_step(self):
        with self.lock:
            self.conversation_step += 1
            return self.conversation_step

    def get_step(self):
        with self.lock:
            return self.conversation_step

    def set_stream_sid(self, sid):
        with self.lock:
            self.stream_sid = sid

    def get_stream_sid(self):
        with self.lock:
            return self.stream_sid

    def set_lead_id(self, lead_id):
        with self.lock:
            self.lead_id = lead_id
            print(f"Setting lead_id to: {lead_id}")  # Add this debug print

    def get_lead_id(self):
        with self.lock:
            print(f"Getting lead_id: {self.lead_id}")  # Add this debug print
            return self.lead_id
    
    def set_is_inbound(self, is_inbound):
        with self.lock:
            self.is_inbound = is_inbound

    def get_is_inbound(self):
        with self.lock:
            return self.is_inbound
    
    def set_phone_number(self, phone_number):
        with self.lock:
            self.phone_number = phone_number

    def get_phone_number(self):
        with self.lock:
            return self.phone_number
    
    def set_lead_info(self, lead_info):
        with self.lock:
            self.lead_info = lead_info

    def get_lead_info(self):
        with self.lock:
            return self.lead_info
    
    def set_ngrok_url(self, url):
        with self.lock:
            self.ngrok_url = url
    
    def set_call_sid(self, sid):
        with self.lock:
            self.call_sid = sid  # Use a standard naming convention
            print(f"[DEBUG] Call SID {sid} set in shared state")

    def get_call_sid(self):
        with self.lock:
            if not hasattr(self, 'call_sid') or self.call_sid is None:
                print("[WARNING] Attempted to get call_sid but it's not set!")
            return getattr(self, 'call_sid', None)
    
    def get_ngrok_url(self):
        with self.lock:
            return getattr(self, 'ngrok_url', None)
    
    def update_temp_lead_data(self, key, value):
        with self.lock:
            self.temp_lead_data[key] = value

    def get_temp_lead_data(self):
        with self.lock:
            return self.temp_lead_data.copy()  # Return a copy to avoid external modifications

    def clear_temp_lead_data(self):
        with self.lock:
            self.temp_lead_data = {}
    
    def set_call_ended(self, ended):
        with self.lock:
            print(f"Setting call_ended to {ended}")
            self.call_ended = ended

    def get_call_ended(self):
        with self.lock:
            return getattr(self, 'call_ended', False)
    
    def set_notify_call_completed(self, notify):
        with self.lock:
            self._notify_call_completed = notify

    def get_notify_call_completed(self):
        with self.lock:
            return getattr(self, '_notify_call_completed', False)

    def set_automated(self, automated):
        with self.lock:
            self.is_automated = automated

    def is_automated(self):
        with self.lock:
            return self.is_automated
        
    def set_buffered_transcription(self, transcription):
        with self.lock:
            self.buffered_transcription = transcription
            
    def get_buffered_transcription(self):
        with self.lock:
            return self.buffered_transcription
            
    def clear_buffered_transcription(self):
        with self.lock:
            self.buffered_transcription = ""
            
    def set_pending_timer(self, timer):
        with self.lock:
            # Cancel any existing timer before setting a new one
            if self.pending_timer is not None:
                print(f"[DEBUG] Cancelling existing timer in set_pending_timer")
                self.pending_timer.cancel()
            self.pending_timer = timer
            print(f"[DEBUG] New timer set")

    def cancel_pending_timer(self):
        with self.lock:
            if self.pending_timer is not None:
                print(f"[DEBUG] Cancelling timer in cancel_pending_timer")
                self.pending_timer.cancel()
                self.pending_timer = None
                print(f"[DEBUG] Timer cancelled and set to None")
            else:
                print(f"[DEBUG] No timer to cancel in cancel_pending_timer")

    def set_spelling_mode(self, is_spelling):
        with self.lock:
            self.spelling_mode = is_spelling
            
    def is_spelling_mode(self):
        with self.lock:
            return self.spelling_mode
    
    def set_assistance_mode(self, is_assistance):
        with self.lock:
            self.assistance_mode = is_assistance
            
    def is_assistance_mode(self):
        with self.lock:
            return getattr(self, 'assistance_mode', False)
    
    def set_conversation_prompt(self, prompt):
        self.company_prompt = prompt
        
    def get_conversation_prompt(self):
        return getattr(self, 'company_prompt', None)
    
    def set_realtor_name(self, name):
        """Set the realtor name for this conversation"""
        self.realtor_name = name

    def get_realtor_name(self):
        """Get the realtor name for this conversation"""
        return getattr(self, 'realtor_name', 'John Doe')
    
    def set_is_returning_lead(self, value):
        with self.lock:
            self.is_returning_lead = value

    def get_is_returning_lead(self):
        with self.lock:
            return getattr(self, 'is_returning_lead', False)
    
    def set_call_start_time(self, start_time):
        self.call_start_time = start_time

    def get_call_start_time(self):
        return getattr(self, 'call_start_time', None)

    def set_call_end_time(self, end_time):
        self.call_end_time = end_time

    def get_call_end_time(self):
        return getattr(self, 'call_end_time', None)

    def set_call_duration(self, duration):
        self.call_duration = duration

    def get_call_duration(self):
        return getattr(self, 'call_duration', None)
    
    def set_extracted_lead_data(self, data):
        with self.lock:
            self.extracted_lead_data = data

    def get_extracted_lead_data(self):
        with self.lock:
            return getattr(self, 'extracted_lead_data', None)
    
    def set_prompt_selected(self, prompt):
        """Store the selected prompt for this conversation"""
        with self.lock:
            self.prompt_selected = prompt
            print(f"[shared_state] Prompt cached for conversation with lead_id: {self.lead_id}")

    def get_prompt_selected(self):
        """Get the cached prompt for this conversation"""
        with self.lock:
            return getattr(self, 'prompt_selected', None)
    
    def set_spelling_type(self, spelling_type):
        with self.lock:
            self.spelling_type = spelling_type
            
    def get_spelling_type(self):
        with self.lock:
            return getattr(self, 'spelling_type', None)
    
    def set_phonetic_extraction(self, extraction):
        with self.lock:
            self.phonetic_extraction = extraction
            print(f"[shared_state] Set phonetic extraction: {extraction}")

    def get_phonetic_extraction(self):
        with self.lock:
            return getattr(self, 'phonetic_extraction', None)
    
    def clear_phonetic_extraction(self):
        with self.lock:
            if hasattr(self, 'phonetic_extraction'):
                del self.phonetic_extraction
                print("[shared_state] Cleared phonetic extraction")
    
    def set_last_spelling_processed_time(self, timestamp):
        with self.lock:
            self.last_spelling_processed_time = timestamp
            
    def get_last_spelling_processed_time(self):
        with self.lock:
            return getattr(self, 'last_spelling_processed_time', None)
    
    def set_last_assistance_processed_time(self, timestamp):
        with self.lock:
            self.last_assistance_processed_time = timestamp
            
    def get_last_assistance_processed_time(self):
        with self.lock:
            return getattr(self, 'last_assistance_processed_time', None)
    
    def set_preformatted_prompt(self, prompt):
        """Store a pre-formatted prompt to use for faster first response"""
        with self.lock:
            self.preformatted_prompt = prompt

    def get_preformatted_prompt(self):
        """Get the pre-formatted prompt if available"""
        with self.lock:
            return getattr(self, 'preformatted_prompt', None)
        
    def set_interrupt_ai(self, interrupt):
        with self.lock:
            self.interrupt_ai = interrupt
            
    def should_interrupt_ai(self):
        with self.lock:
            return self.interrupt_ai
    
    def set_ai_speaking(self, speaking):
        with self.lock:
            self.ai_is_speaking = speaking
            if speaking:
                print(f"[DEBUG] AI started speaking")
            else:
                print(f"[DEBUG] AI stopped speaking")
            
    def is_ai_speaking(self):
        with self.lock:
            return self.ai_is_speaking
    
    def set_clear_command_sent(self, sent):
        with self.lock:
            self.clear_command_sent = sent

    def is_clear_command_sent(self):
        with self.lock:
            return getattr(self, 'clear_command_sent', False)
    
    def set_user_is_speaking(self, is_speaking):
        with self.lock:
            self.user_is_speaking = is_speaking

    def get_user_is_speaking(self):
        with self.lock:
            return getattr(self, 'user_is_speaking', False)

    def set_user_silence_detected(self, silence_detected):
        with self.lock:
            self.user_silence_detected = silence_detected

    def get_user_silence_detected(self):
        with self.lock:
            return getattr(self, 'user_silence_detected', False)
    
    
    def set_followupboss_data(self, fub_data):
        """Store FollowUpBoss webhook data for prompt formatting"""
        with self.lock:
            self.followupboss_data = fub_data
            print(f"[shared_state] Stored FollowUpBoss data: {fub_data}")

    def get_followupboss_data(self):
        """Get stored FollowUpBoss webhook data"""
        with self.lock:
            return getattr(self, 'followupboss_data', None)

    def clear_followupboss_data(self):
        """Clear stored FollowUpBoss webhook data"""
        with self.lock:
            if hasattr(self, 'followupboss_data'):
                del self.followupboss_data
                print("[shared_state] Cleared FollowUpBoss data")
    
    def set_property_inquiry_info(self, property_info):
        """Store property inquiry information (agent name and property address)"""
        with self.lock:
            self.property_inquiry_info = property_info
            print(f"[shared_state] Stored property inquiry info: {property_info}")

    def get_property_inquiry_info(self):
        """Get stored property inquiry information"""
        with self.lock:
            return getattr(self, 'property_inquiry_info', None)

    def clear_property_inquiry_info(self):
        """Clear stored property inquiry information"""
        with self.lock:
            if hasattr(self, 'property_inquiry_info'):
                del self.property_inquiry_info
                print("[shared_state] Cleared property inquiry info")
