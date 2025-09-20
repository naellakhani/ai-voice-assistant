"""
Text extraction utilities for parsing conversation transcripts.
These functions provide fallback extraction capabilities when Gemini extraction is unavailable.
"""
import re
import spacy
from spacy.matcher import Matcher

nlp = spacy.load("en_core_web_sm")
matcher = Matcher(nlp.vocab)

def extract_data(text):
    """Extract basic information from conversation transcript."""
    data = {
        'name': None,
        'first_name': None,
        'last_name': None,
        'email': None,
        'phone': None,
        'company': None,
        'reason_for_call': None
    }

    # Split transcript into turns
    turns = text.split('\n') if isinstance(text, str) else text
    conversation_turns = []
    for turn in turns:
        if ': ' in turn:
            speaker, message = turn.split(': ', 1)
            conversation_turns.append((speaker.strip(), message.strip()))
    
    data['reason_for_call'] = extract_reason(conversation_turns)
    
    verified_data = extract_verified_spellings(conversation_turns)

    for key in ['first_name', 'last_name', 'name', 'email', 'phone']:
        if verified_data.get(key):
            data[key] = verified_data.get(key)
    
    company_found = False
    for i, (speaker, message) in enumerate(conversation_turns):
        if speaker == "AI":
            next_turn = conversation_turns[i + 1] if i + 1 < len(conversation_turns) else None
            if not next_turn or next_turn[0] != "Lead":
                continue
                
            lead_response = next_turn[1]
            
            # Company extraction
            if "company" in message.lower() or "institution" in message.lower():
                cleaned = lead_response.lower()
                # Skip responses that are likely not actual company names
                if cleaned in ['no', 'none', 'na', 'n/a', 'not applicable', 
                               'uh', 'um', 'well', 'no company', 'no institution']:
                    continue
                    
                for filler in ['uh', 'um', 'well', 'like', 'you know']:
                    cleaned = cleaned.replace(filler, '')
                cleaned = cleaned.strip()
                
                if cleaned and len(cleaned) > 1:
                    data['company'] = cleaned.title()
                    company_found = True
                    break

    if data.get('email'):
        # Fix common email issues
        email = data['email']
        # Replace spelled-out @ and . if needed
        email = email.replace(" at ", "@").replace("at", "@") if "@" not in email else email
        email = email.replace(" dot ", ".").replace("dot", ".") if "dot" in email.lower() and "." not in email else email
        # Remove spaces
        email = ''.join(email.split())
        # Basic validation - must have @ and at least one . after @
        if '@' in email and '.' in email.split('@')[1]:
            data['email'] = email
        else:
            data['email'] = "Unknown"
    
    # Ensure name is properly formatted
    if data.get('first_name') and data.get('last_name') and not data.get('name'):
        data['name'] = f"{data['first_name']} {data['last_name']}"
    elif data.get('name') and not data.get('first_name') and not data.get('last_name'):
        # Try to split the name
        parts = data['name'].split()
        if len(parts) >= 2:
            data['first_name'] = parts[0]
            data['last_name'] = ' '.join(parts[1:])
    
    # Set default for any missing fields
    for key in data:
        if not data[key]:
            data[key] = "Unknown"
    
    print("Final extracted data:", data)
    return data
            
def extract_verified_spellings(conversation_turns):
    # Dictionary to store our extracted data
    verified_data = {
        'first_name': None,
        'last_name': None,
        'email': None,
        'phone': None,
        'name': None  # Will be combined from first_name and last_name
    }
    
    current_context = None  # What we're currently verifying
    
    # Go through each turn in conversation
    for i, (speaker, message) in enumerate(conversation_turns):
        if speaker != "AI":
            continue
            
        # Determine what's being verified
        if "first name" in message.lower():
            current_context = "first_name"
        elif "last name" in message.lower():
            current_context = "last_name"
        elif "email" in message.lower():
            current_context = "email"
        elif "phone number" in message.lower():
            current_context = "phone"
            
        # Look for spelling verification pattern
        if "so that's" in message.lower() and "correct?" in message.lower():
            # Extract the spelled content
            spelled_content = message.lower().split("so that's")[1].split("correct?")[0].strip()
            
            # Check if Lead confirms in next turn
            if i + 1 < len(conversation_turns) and conversation_turns[i + 1][0] == "Lead":
                lead_response = conversation_turns[i + 1][1].lower()
                
                # If Lead confirms
                if any(confirm in lead_response for confirm in ["yes", "correct", "yeah", "yep", "that's right"]):
                    # Store the extracted content based on context
                    if current_context:
                        if current_context in ["first_name", "last_name"]:
                            # Remove spaces to get the actual name
                            clean_name = ''.join(spelled_content.split())
                            verified_data[current_context] = clean_name.title()
                        elif current_context == "phone":
                            # Remove spaces and non-digits for phone
                            clean_phone = ''.join(c for c in spelled_content if c.isdigit())
                            verified_data[current_context] = clean_phone
        
        # Special case for email verification which has different format
        elif "let me confirm that" in message.lower() and "correct?" in message.lower():
            # Extract the spelled email
            spelled_email = message.lower().split("let me confirm that -")[1].split("correct?")[0].strip()
            
            # Check if Lead confirms in next turn
            if i + 1 < len(conversation_turns) and conversation_turns[i + 1][0] == "Lead":
                lead_response = conversation_turns[i + 1][1].lower()
                
                # If Lead confirms
                if any(confirm in lead_response for confirm in ["yes", "correct", "yeah", "yep", "that's right"]):
                    # Format email properly
                    clean_email = spelled_email.replace(" at ", "@").replace(" dot ", ".")
                    # Remove any remaining spaces
                    clean_email = ''.join(clean_email.split())
                    verified_data['email'] = clean_email
    
    # Combine first and last name if both are present
    if verified_data['first_name'] and verified_data['last_name']:
        verified_data['name'] = f"{verified_data['first_name']} {verified_data['last_name']}"
    
    return verified_data

def extract_reason(conversation_turns):
    initial_reason = None
    additional_reason = []
    
    # Initial assistance question patterns
    assistance_patterns = [
        "how can we assist",
        "how can i help",
        "what brings you",
        "how may i help",
        "what can i help",
        "how can i assist"  # Added pattern
    ]
    
    # Additional patterns for when leads volunteer info
    volunteer_patterns = [
        "i'm calling",
        "i am calling",
        "i called",
        "calling about",
        "calling for",
        "like to",
        "would like to",
        "trying to",
        "want to",
        "calling from",
        "work at",
        "sell",
        "buy",
        "purchase"
    ]
    
    # Product/service related keywords
    product_keywords = [
        "spectrometers", "spectroscopy", "equipment", "technology", 
        "products", "services", "inventory", "purchase", "meeting", 
        "information", "alternatives", "measurements"
    ]
    
    # Additional questions patterns
    additional_patterns = [
        "additional questions",
        "anything else",
        "other questions"
    ]
    
    # Negative response patterns
    negative_patterns = [
        "no",
        "not right now",
        "that's it",
        "thats it",
        "nothing else",
        "not at the moment",
        "no that's it",
        "no thats it",
        "nope",
        "no thanks",
        "that's all",
        "thats all",
        "no that's all",
        "no thats all"
    ]

    core_negative_starts = [
        "no",
        "nope",
        "nothing",
        "not",
        "thats all",
        "that's all",
        "thats it",
        "that's it"
    ]    
    
    # First pass: look for direct responses to assistance questions
    for i, (speaker, message) in enumerate(conversation_turns):
        # Skip if not enough turns left to check response
        if i + 1 >= len(conversation_turns):
            continue
            
        # Get the next turn
        next_speaker, next_message = conversation_turns[i + 1]
        
        # Only process AI messages with Lead responses
        if speaker != "AI" or next_speaker != "Lead":
            continue
            
        # Check for initial assistance question
        if not initial_reason and any(pattern in message.lower() for pattern in assistance_patterns):
            initial_reason = next_message.strip()
            continue
            
        # Check for additional questions
        if any(pattern in message.lower() for pattern in additional_patterns):
            response = next_message.lower().strip()
            # Enhanced negative response check - combines both exact matches and starts-with checks
            if not (response in negative_patterns or any(response.startswith(neg) for neg in core_negative_starts)):
                additional_reason.append(next_message.strip())
    
    # Second pass: If no reason found, look for volunteered information from the lead
    if not initial_reason:
        for speaker, message in conversation_turns:
            if speaker != "Lead":
                continue
                
            # Check if lead is volunteering a reason
            message_lower = message.lower()
            if any(pattern in message_lower for pattern in volunteer_patterns):
                # Check for product keywords for more context
                product_mentioned = any(keyword in message_lower for keyword in product_keywords)
                if product_mentioned:
                    # Found a meaningful statement about their reason for calling
                    return message.strip()
                # Even without product keywords, if they're clearly stating why they're calling
                if any(f"i'm calling {p}" in message_lower or f"i am calling {p}" in message_lower 
                       for p in ["about", "for", "to", "because"]):
                    return message.strip()
    
    # Combine reasons if both exist
    if initial_reason and additional_reason:
        return f"{initial_reason}. {', '.join(additional_reason)}"
    elif initial_reason:
        return initial_reason
    elif additional_reason:
        return ', '.join(additional_reason)
    
    return "Unknown"

def extract_name(lead_response):
    # Convert to lowercase and remove extra whitespace
    cleaned = lead_response.lower().strip()

    # First handle spelling patterns like "P for Peter"
    spelling_patterns = [
        (r'(\w)\s+for\s+\w+', r'\1'),      # "P for Peter" -> "P"
        (r'(\w)\s+as\s+in\s+\w+', r'\1'),  # "P as in Peter" -> "P"
        (r'(\w)\s+like\s+\w+', r'\1'),     # "P like Peter" -> "P"
        (r'(\w)\s+from\s+\w+', r'\1'),     # "P from Peter" -> "P"
        (r'(\w)\s*-\s*\w+', r'\1'),        # "P-Peter" or "P - Peter" -> "P"
    ]
    
    # Apply each pattern and collect spelling letters
    parts = cleaned.split()
    processed_parts = []
    
    i = 0
    while i < len(parts):
        current_chunk = ' '.join(parts[i:i+3])  # Look at chunks of 3 words for patterns
        matched = False
        
        for pattern, replacement in spelling_patterns:
            if re.search(pattern, current_chunk):
                # Extract just the spelling letter
                letter = re.sub(pattern, replacement, current_chunk)
                processed_parts.append(letter)
                matched = True
                i += len(current_chunk.split())  # Skip the whole matched pattern
                break
        
        if not matched:
            processed_parts.append(parts[i])
            i += 1
    
    # Remove filler words
    fillers = ['yeah', 'uh', 'um', 'sure', 'ok', 'well', 'like', 'just', 
               "it's", "i'm", "he's", "she's", "they're", 'its', 'the']
    for filler in fillers:
        cleaned = re.sub(rf'\b{filler}\b', '', cleaned)
    
    # Get only single letters that were spelled out
    spelled_letters = [part for part in parts if len(part) == 1 and part.isalpha()]
    
    if spelled_letters and len(spelled_letters) == len(parts):
        extracted_name = ''.join(spelled_letters)
        return extracted_name.title()
    
    # Handle mixed spelling case
    current_spelled_word = []
    name_parts = []
    
    for part in processed_parts:
        if len(part) == 1 and part.isalpha():
            current_spelled_word.append(part)
        else:
            # If we have collected spelled letters, combine them first
            if current_spelled_word:
                name_parts.append(''.join(current_spelled_word))
                current_spelled_word = []
            # Add the complete word if it's not a filler
            if len(part) > 1:
                name_parts.append(part)
    
    # Don't forget any remaining spelled letters
    if current_spelled_word:
        name_parts.append(''.join(current_spelled_word))
    
    # If we found any name parts, combine them
    if name_parts:
        return ' '.join(word.title() for word in name_parts)
        
    return None

def extract_email(lead_response):
    # Convert to lowercase and remove extra whitespace
    cleaned = lead_response.lower().strip()
    
    # Remove filler words
    fillers = ['yeah', 'uh', 'um', 'sure', 'ok', 'well', 'like', 'just', 
               "it's", "i'm", "he's", "she's", "they're", 'its', 'the']
    for filler in fillers:
        cleaned = re.sub(rf'\b{filler}\b', '', cleaned)
    
    # Split into parts
    parts = cleaned.split()
    
    # Process the email parts
    email_parts = []
    current_spelled = []
    has_at_symbol = False

    i = 0
    while i < len(parts):
        part = parts[i]
        
        # NEW: Handle numbers mixed with letters
        if part.isdigit():
            # Check if previous part exists and is a letter or next part is a letter
            if (i > 0 and len(parts[i-1]) == 1 and parts[i-1].isalpha()) or \
               (i < len(parts)-1 and len(parts[i+1]) == 1 and parts[i+1].isalpha()):
                email_parts.append(part)
            # NEW: Handle numbers at start of email
            elif i == 0 and i < len(parts)-1:
                email_parts.append(part)
        
        # Handle single spelled letters
        elif len(part) == 1 and part.isalpha():
            email_parts.append(part)
        # Handle 'at' symbol
        elif part == 'at':
            email_parts.append('@')
            has_at_symbol = True
        # Handle 'dot' or period
        elif part in ['dot', '.']:
            email_parts.append('.')
        elif part.endswith('.com') or part.endswith('.net') or part.endswith('.org') or part.endswith('.edu'):
            # If no @ symbol yet, add it before the domain
            if not has_at_symbol:
                email_parts.append('@')
            email_parts.append(part)
        # Keep domain parts (e.g., 'gmail.com') as is
        elif '.' in part:
            email_parts.append(part)
        # Handle explicitly spelled 'period' or 'point'
        elif part in ['period', 'point']:
            email_parts.append('.')
        else:
            email_parts.append(part)
        
        i += 1
    
    # Combine all parts and remove any extra dots
    email = ''.join(email_parts)
    # Clean up any duplicate dots
    email = re.sub(r'\.+', '.', email)
    
    # Basic validation - must have @ and at least one dot after @
    if '@' in email and '.' in email.split('@')[1]:
        return email
        
    return None