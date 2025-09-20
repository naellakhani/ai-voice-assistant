# ===========================================

# This module manages AI-powered responses using Google's Gemini 1.5 flashmodel with a detailed prompt script.
#
# Key Responsibilities:
# - Load and manage conversation prompt templates
# - Handle real-time AI conversation with Gemini
# - Instruct Gemini to extract structured data from conversations during calls
# - Manage conversation modes (information collection, assistance, spelling)
# - Context-aware conversation state management
#
# Core Functions:
# - manage_conversation(): Main conversation handler with Gemini integration
# - load_prompt_template(): Dynamic prompt loading from files
# - generate_first_response(): Generate response for the first message in conversation with full prompt context
# - generate_response(): Generate response for follow-up messages using chat history
# - clean_extracted_data(): Clean extracted data by removing dashes from names and properly formatting email
#
# Conversation Flow:
# 1. Load appropriate prompt template based on lead context
# 2. Process user input through Gemini with conversation history
# 3. Generate contextually appropriate AI responses that gets sent to websocket_handler.py
# 4. Extract JSONstructured data in real-time during conversation
# 5. Store extracted data in shared_state for later processing
#
# Prompt Management:
# - Template-based prompts with dynamic variable substitution
# - Lead-specific context injection (name, source, agent, etc.)
# - Multiple prompt templates for different scenarios
#

import google.generativeai as genai
from model_managers import GeminiManager
import os
import json
from vertexai.preview import tokenization
import random
from call_logger import get_call_logger
import time

DEFAULT_PROMPT_PATH = 'prompts/real-estate-prompt.txt'

MODEL_NAME = "gemini-1.5-flash"
tokenizer = tokenization.get_tokenizer_for_model(MODEL_NAME)

def count_tokens(text):
    # Count tokens for a given piece of text using the Vertex AI tokenizer
    if not text:
        return 0
    try:
        result = tokenizer.count_tokens(text)
        return result.total_tokens
    except Exception as e:
        print(f"Error counting tokens: {e}")
        # Fallback estimation if tokenizer fails
        return len(text.split()) * 1.3  # Rough estimate


def load_prompt_template(prompt_path=None):
    logger = get_call_logger()
    file_path = prompt_path if prompt_path else DEFAULT_PROMPT_PATH
    
    # Make sure we use absolute path if provided path is relative
    if not os.path.isabs(file_path):
        file_path = os.path.join(os.path.dirname(__file__), file_path)
    
    try:
        with open(file_path, 'r') as file:
            logger.info(f"Loaded prompt template from {file_path}")
            return file.read()
    except Exception as e:
        logger.error(f"Error loading prompt template from {file_path}: {e}")
        # If custom prompt fails, try loading the default prompt
        if prompt_path and prompt_path != DEFAULT_PROMPT_PATH:
            print(f"Attempting to load default prompt instead")
            try:
                default_path = os.path.join(os.path.dirname(__file__), DEFAULT_PROMPT_PATH)
                with open(default_path, 'r') as file:
                    return file.read()
            except Exception as inner_e:
                print(f"Error loading default prompt: {inner_e}")
        
        # Fallback to a minimal prompt if all else fails
        return "You are a friendly call service agent for Default Inc."

# Load the prompt template when the module is imported
DEFAULT_PROMPT = load_prompt_template()
RETURNING_LEAD_PROMPT = """You are an AI assistant named John for {company_name}. You're speaking with {lead_name}, a returning client who has called your service before.

You already have {lead_name}'s contact information, including their email ({lead_email}), so DO NOT ask for it again.
Focus directly on understanding their current needs for this call. If they want to speak to someone specifically, then mention that you can leave a message for them. Is there anything you'd like me to include in my message?
If they ask about specific material such as spectrometer etc. then mention that you will pass all this information to the sales team and they will follow up with you shortly to answer your questions. Anything specific you'd want me to include in the message?

At the end of the call, verify the email address we have on file: "Just to confirm, this is the email we have on file: {lead_email}. is this correct or do you want to update it?"
"""

def initialize_components():
    model, chat = GeminiManager.create_chat()
    return {
        'model': model,
        'chat': chat
    }

def generate_first_response(chat, user_input, lead_info, shared_state, is_inbound=False, max_tokens=150):
    # Generate response for the first message in conversation with full prompt context"""
    call_sid = shared_state.get_call_sid() if hasattr(shared_state, 'get_call_sid') else None
    lead_id = shared_state.get_lead_id() if hasattr(shared_state, 'get_lead_id') else None
    logger = get_call_logger(call_sid, lead_id)
    
    # Check if we have a pre-formatted prompt
    if hasattr(shared_state, 'get_preformatted_prompt') and shared_state.get_preformatted_prompt():
        # Fast path: just append user input to pre-formatted prompt
        user_input_with_context = user_input
        formatted_prompt = shared_state.get_preformatted_prompt() + f"\n\nUser: {user_input_with_context}\nAI:"
        logger.info("[conversation_manager] Using pre-formatted prompt for faster response")
    else:
        # Slow path: format the prompt from scratch
        logger.info("[conversation_manager] No pre-formatted prompt found, formatting from scratch")
        lead_name = lead_info.get('name', 'there') if isinstance(lead_info, dict) else 'there'
        lead_email = lead_info.get('email', 'no email on file') if isinstance(lead_info, dict) else 'no email on file'
        agent_name = lead_info.get('agent_name', 'John Doe') if isinstance(lead_info, dict) else 'John Doe'
        caller_phone = lead_info.get('phone') if isinstance(lead_info, dict) else None or shared_state.get_phone_number() or "the phone number you called from"
    
        prompt = shared_state.get_conversation_prompt()
        if not prompt:  
            prompt = DEFAULT_PROMPT
    
        # Get additional context for prompt formatting
        lead_source = lead_info.get('source') or 'None'
        lead_tags = lead_info.get('tags', [])
        tags_text = ", ".join(lead_tags) if lead_tags else "None"
        
        
        # Send formatted prompt to model
        formatted_prompt = prompt.format(
            lead_name=lead_name, 
            lead_email=lead_email, 
            lead_source=lead_source,
            lead_tags=tags_text,
            agent_name=agent_name, 
            caller_phone=caller_phone,
            is_inbound="Yes" if is_inbound else "No",
            ontario_cities="Toronto, Mississauga, Brampton, Oakville, Burlington, Milton, Georgetown, Vaughan, Richmond Hill, Markham, Ajax, Pickering, Whitby, Oshawa"
        )
        
        # Format prompt with user input
        user_input_with_context = user_input
        formatted_prompt += f"\n\nUser: {user_input_with_context}\nAI:"
    
    generation_config = genai.GenerationConfig(
        max_output_tokens=max_tokens,
        temperature=0.25,
        top_p=0.7
    )
    
    # Get response from model
    response = chat.send_message(formatted_prompt, generation_config=generation_config)
    
    return response.text


def generate_response(chat, user_input, max_tokens=150):
    # Simplified function toGenerate response for follow-up messages using gemini's built-in chat history
    generation_config = genai.GenerationConfig(
        max_output_tokens=max_tokens,
        temperature=0.25,
        top_p=0.7
    )
    
    user_input_with_context = user_input

    # Implement retries if google's api is timed out or rate limited
    max_retries = 3
    base_delay = 1  # second
    
    for attempt in range(max_retries):
        try:
            # Send the user input
            response = chat.send_message(user_input_with_context, generation_config=generation_config)
            return response.text
        except google.api_core.exceptions.ResourceExhausted as e:
            error_msg = str(e).lower()
            if "quota" in error_msg:
                # Handle quota exceeded errors
                print(f"[conversation_manager] API quota exceeded (attempt {attempt+1}/{max_retries}): {e}")
                # Log this critical error for monitoring alerts
                if attempt == max_retries - 1:  # Last attempt
                    return "I'm sorry, but I'm having trouble processing your request right now. Let me take your information and have someone call you back shortly."
            elif "rate" in error_msg:
                # Handle rate limit errors with backoff
                delay = base_delay * (2 ** attempt) + (random.random() * 0.5)  # Add jitter
                print(f"[conversation_manager] API rate limited, retrying in {delay:.2f}s (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(delay)
            else:
                # Other resource exhausted errors
                print(f"[conversation_manager] API resource exhausted (attempt {attempt+1}/{max_retries}): {e}")
                delay = base_delay * (1.5 ** attempt)  # Less aggressive backoff
                time.sleep(delay)
                if attempt == max_retries - 1:  # Last attempt
                    return "I'm having trouble understanding you right now. Could you please repeat that?"
        except (google.api_core.exceptions.ServiceUnavailable, 
                google.api_core.exceptions.ServerError,
                google.api_core.exceptions.DeadlineExceeded) as e:
            # Service unavailable/timeout - backoff and retry
            delay = base_delay * (2 ** attempt) + (random.random() * 0.5)  # Add jitter
            print(f"[conversation_manager] API service issue, retrying in {delay:.2f}s (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(delay)
            if attempt == max_retries - 1:  # Last attempt
                return "I apologize, but our service is temporarily unavailable. Let me take your information and have someone call you back as soon as possible."
        except Exception as e:
            # Unexpected errors
            print(f"[conversation_manager] Unexpected error (attempt {attempt+1}/{max_retries}): {e}")
            # Don't retry immediately for unknown errors to avoid making things worse
            time.sleep(base_delay)
            if attempt == max_retries - 1:  # Last attempt
                return "I apologize for the inconvenience, but I'm experiencing a technical issue. Let me collect your contact information so we can follow up with you directly."
    
    # If we get here, all retries failed
    return "I apologize, but I'm having technical difficulties at the moment. Please leave your name and number, and someone from our team will call you back promptly."

def clean_extracted_data(data):
    # Clean extracted data by removing dashes from names and properly formatting email
    logger = get_call_logger()
    if not data:
        return data
    
    # Create a new dictionary to avoid modifying the original during iteration
    cleaned_data = {}
    
    for key, value in data.items():
        if key in ['first_name', 'last_name'] and isinstance(value, str):
            # Remove dashes from names
            cleaned_data[key] = value.replace('-', '').replace(' ', '')
        elif key == 'email' and isinstance(value, str):
            # For email, perform comprehensive cleaning:
            # 1. Replace " at " with "@"
            # 2. Replace " dot " with "."
            # 3. Remove all spaces
            # 4. Remove any dashes
            cleaned_value = value.replace(' at ', '@').replace(' dot ', '.')
            cleaned_value = cleaned_value.replace(' AT ', '@').replace(' DOT ', '.')
            cleaned_value = cleaned_value.replace('at ', '@').replace('dot ', '.')
            cleaned_value = cleaned_value.replace(' at', '@').replace(' dot', '.')
            
            # Handle case where there's no space between "at" and surrounding text
            if '@' not in cleaned_value and 'at' in cleaned_value:
                parts = cleaned_value.split('at')
                if len(parts) == 2:
                    cleaned_value = f"{parts[0]}@{parts[1]}"
            
            # Handle case where there's no space between "dot" and surrounding text
            if 'dot' in cleaned_value:
                parts = cleaned_value.split('dot')
                cleaned_value = '.'.join(parts)
            
            # Remove all spaces and dashes
            cleaned_value = cleaned_value.replace(' ', '')
            
            cleaned_data[key] = cleaned_value
        else:
            # Keep other fields as they are
            cleaned_data[key] = value
    
    # Combine first_name and last_name into name field
    if 'first_name' in cleaned_data and 'last_name' in cleaned_data:
        cleaned_data['name'] = f"{cleaned_data['first_name']} {cleaned_data['last_name']}".strip()
        logger.info(f"[conversation_manager] Combined name: {cleaned_data['name']}")
    elif 'first_name' in cleaned_data and not cleaned_data.get('name'):
        cleaned_data['name'] = cleaned_data['first_name']
    elif 'last_name' in cleaned_data and not cleaned_data.get('name'):
        cleaned_data['name'] = cleaned_data['last_name']
    
    logger.info(f"[conversation_manager] Cleaned extracted data: {cleaned_data}")
    return cleaned_data

def manage_conversation(chat, user_input, shared_state, lead_info):
    call_sid = shared_state.get_call_sid() if hasattr(shared_state, 'get_call_sid') else None
    lead_id = shared_state.get_lead_id() if hasattr(shared_state, 'get_lead_id') else None
    logger = get_call_logger(call_sid, lead_id)

    logger.info(f"[conversation_manager] Received lead_info: {lead_info}")
    lead_name = lead_info.get('name', 'there')
    lead_email = lead_info.get('email', 'unknown@example.com')
    is_inbound = lead_info.get('is_inbound', False)
    is_returning_lead = shared_state.get_is_returning_lead() if hasattr(shared_state, 'get_is_returning_lead') else False

    logger.info(f"[conversation_manager] Processing - Name: {lead_name}, Email: {lead_email}, Is Inbound: {is_inbound}")

    current_step = shared_state.get_step()
    
    # Choose the appropriate response generation method
    if current_step == 0:
        logger.info("[conversation_manager] First message - using full context prompt")
        response = generate_first_response(chat, user_input, lead_info, shared_state, is_inbound)
    else:
        response = generate_response(chat, user_input)
    
    # Extract JSON data if present
    extracted_data = None
    response_for_user = response
    
    if "<data_extract>" in response:
        # Split the response at the data_extract tag and only keep the first part
        response_for_user = response.split("<data_extract>")[0].strip()
        
        # Extract the JSON data for internal use
        try:
            # Check if closing tag exists
            if "</data_extract>" in response:
                json_str = response.split("<data_extract>")[1].split("</data_extract>")[0].strip()
                extracted_data = json.loads(json_str)
                logger.info(f"[conversation_manager] Successfully extracted data: {extracted_data}")
                
                cleaned_data = clean_extracted_data(extracted_data)
                # Store the extracted data in shared state for later use
                shared_state.extracted_lead_data = cleaned_data

                try:
                    import requests
                    requests.post('http://transcript-viewer:3001/call-summary', json=cleaned_data)
                    logger.info(f"[conversation_manager] Sent extracted data to demo server")
                except Exception as e:
                    logger.debug(f"[conversation_manager] Demo server not available: {e}")
                    pass
            else:
                # Handle case where closing tag is missing
                logger.warning("[conversation_manager] Warning: data_extract closing tag missing")
                json_str = response.split("<data_extract>")[1].strip()
                # Try to parse anyway in case it's valid JSON
                try:
                    extracted_data = json.loads(json_str)
                    cleaned_data = clean_extracted_data(extracted_data)
                    shared_state.extracted_lead_data = cleaned_data
                    print(f"[conversation_manager] Recovered data despite missing tag: {extracted_data}")
                except:
                    print("[conversation_manager] Could not parse incomplete JSON data")
        except Exception as e:
            print(f"[conversation_manager] Error processing data_extract: {e}")
    else:
        # No data extract block found
        response_for_user = response
    
   # turning spelling mode ON
    response_lower = response_for_user.lower()
    if "can i get your full name" in response_lower or "what's your name" in response_lower or "first name" in response_lower or "last name" in response_lower:
        shared_state.set_spelling_mode(True)
        shared_state.set_spelling_type("name_collection")
        shared_state.set_assistance_mode(False)
        logger.info("[conversation_manager] Setting spelling mode ON for NAME_COLLECTION based on AI response")
    elif (("email" in response_lower or "@" in response_lower) and 
         ("spell" in response_lower or "spelling" in response_lower or 
            "could you spell" in response_lower or "spell that" in response_lower)):
         shared_state.set_spelling_mode(True)
         shared_state.set_spelling_type("email")
         logger.info("[conversation_manager] Setting spelling mode ON for EMAIL based on AI response")
    elif any(phrase in response_lower for phrase in [
        "phone number", "best phone number", "reach you at", "call you at", 
        "phone", "number to reach", "number to contact"
    ]):
        shared_state.set_spelling_mode(True)
        shared_state.set_spelling_type("phone")
        logger.info("[conversation_manager] Setting spelling mode ON for PHONE based on AI response")
    elif ("thank you" in response_lower and 
            "got it" in response_lower and 
            not ("spell" in response_lower or "spelling" in response_lower)):
        
        current_spelling_type = shared_state.get_spelling_type()
        shared_state.set_spelling_mode(False)
        shared_state.set_spelling_type(None)
        logger.info("[conversation_manager] Setting spelling mode OFF")
      # Enhanced assistance phrase detection
    assistance_phrases = [
         # More specific phrases about including information in messages
        "is there anything specific you'd like me to include",
        "is there anything else",
        "is there anything specific",
        "can you tell me a little more",
        "can you tell me more",
        "could you share more",
        "could you give me more information about what's happening",
        "could you give me more information about",
        "could you provide more details",
        "could you provide more information"
        "give me more information about what's happening", 
        "give me more information about",
        "more information about what's happening",
        "tell me more about what's happening",
        "could you tell me more about what's happening",
        "can you give me more details about what's happening",
        "can you tell me more about what's happening",
        "anything specific you'd like me to mention",
        "would you like me to include any other details", 
        "anything else you'd like me to mention", 
        "any other details you want me to pass along",
        "anything else I should tell them",
        "any specific requirements you'd like me to note",
        "what else would you like me to add",
        "any additional information you want included",
        "any particular details that are important",
        "to include in my message to",
        # Clear message-taking phrases
        "regarding your request about",
        "regarding your inquiry",  # More general than the existing "regarding your inquiry about"
        "regarding your request",
        "what message would you like me to pass along",
        "message you'd like me to deliver",
        "regarding your inquiry about",
        "regarding your question about spectrometers",
        "specifics of your request",
        "details of your inquiry",
        "what specific information are you looking for",
        "what information are you looking for", 
        "what details are you looking for",
        "what exactly are you interested in",
        "what are you specifically looking for",
        "what would you like to know about",
        "how can I help with your request",
        "more details about your needs",
        "what are your requirements",
    ]

      # Turning assistance mode logic ON.
    if any(phrase in response_lower for phrase in assistance_phrases):
        if shared_state.is_spelling_mode():
            shared_state.set_spelling_mode(False)
            shared_state.set_spelling_type(None)

            logger.info("[conversation_manager] Exiting spelling mode as conversation moved to assistance")
    
        # Enter assistance mode
        shared_state.set_assistance_mode(True)
        logger.info("[conversation_manager] Setting assistance mode ON based on AI response")
            
    return response_for_user