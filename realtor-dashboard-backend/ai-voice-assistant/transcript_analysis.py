"""
Transcript analysis utilities for processing call transcripts.
"""
def analyze_call_completion(transcript):
    """
    Analyze transcript to determine call completion status.
    
    Args:
        transcript: List of conversation lines or string with newlines
        
    Returns:
        String indicating call status: 'immediate_hangup', 'hangup', 
        'completed_positive', 'completed_negative'
    """
    messages = transcript.split('\n') if isinstance(transcript, str) else transcript
    lead_messages = [msg.split("Lead: ")[1] for msg in messages if msg.startswith("Lead:")]
    
    # 1. Immediate Hangup Check
    if not lead_messages:
        return "immediate_hangup"
    
    # 2. Voicemail Detection Check
    # Check if the conversation indicates interaction with voicemail system
    full_transcript = ' '.join(messages).lower()
    voicemail_indicators = [
        "voicemail", "voice mail", "leave a message", "after the beep",
        "unavailable to take your call", "please leave your name",
        "mailbox", "not available right now", "please hold while",
        "automated", "press 1 for", "dial 0 for operator"
    ]
    
    # If voicemail indicators are present, treat as hangup (not answered by person)
    if any(indicator in full_transcript for indicator in voicemail_indicators):
        return "hangup"
    
    # 3. Proper Closure Check
    closure_phrases = [
        "goodbye", "bye", "thank you", "thanks",
        "have a great day", "talk to you later",
        "appreciate your time"
    ]
    
    last_messages = messages[-3:]
    has_proper_closure = any(
        phrase in msg.lower() 
        for msg in last_messages 
        for phrase in closure_phrases
    )
    
    # 4. Hangup Check (Short convo + No proper ending)
    if len(lead_messages) <= 2 and not has_proper_closure:
        return "hangup"
        
    # 5. Completed Call Analysis
    if has_proper_closure:
        # Negative Completion Indicators
        negative_patterns = [
            "not interested", "not looking", 
            "not right now", "not at this time",
            "pass your information", "give them your number",
            "maybe later", "not ready"
        ]
        
        # Positive Completion Indicators
        positive_patterns = [
            "looking to buy", "looking for", "interested in",
            "bedroom", "bathroom", "budget",
            "mortgage", "send listing", "send me",
            "moving", "location", "area",
            "downtown", "condo", "house"
        ]
        
        # Convert transcript to lowercase for pattern matching
        transcript_text = ' '.join(lead_messages).lower()
        
        # Count matches
        negative_matches = sum(1 for pattern in negative_patterns if pattern in transcript_text)
        positive_matches = sum(1 for pattern in positive_patterns if pattern in transcript_text)
        
        # If there are clear negative indicators
        if any(pattern in transcript_text for pattern in negative_patterns):
            return "completed_negative"
            
        # If there are multiple positive engagement indicators
        if positive_matches >= 3:  # Requiring at least 3 positive indicators
            return "completed_positive"
            
        # Default to negative if unclear (being conservative)
        return "completed_negative"

    # Default case - no proper closure
    return "hangup"

def format_transcript_simple(transcript, shared_state):
    """
    Format transcript for readability and notifications.
    
    Args:
        transcript: List of conversation lines
        shared_state: Shared state object containing conversation context
        
    Returns:
        Formatted transcript as a string
    """
    formatted_lines = []
    
    # Check if the greeting is already included
    has_greeting = False
    if transcript and len(transcript) > 0:
        has_greeting = any("Hello" in line and "John answering" in line for line in transcript if line.startswith("AI:"))
    
    # Add the initial greeting if it's not already included and it's an inbound call
    if not has_greeting and shared_state.get_is_inbound():
        # Get company name and lead name from shared state
        company_name = shared_state.get_company_name() if hasattr(shared_state, 'get_company_name') else "our company"
        lead_info = shared_state.get_lead_info() if hasattr(shared_state, 'get_lead_info') else None
        lead_name = lead_info.get('name', 'there') if lead_info else 'there'
        
        # Add the initial greeting
        greeting = f"AI: Hello {lead_name}, this is John answering on behalf of {company_name}. How can I help you today?"
        formatted_lines.append(greeting)
    
    # Add each transcript line, ensuring proper format
    for line in transcript:
        if line.strip():  # Skip empty lines
            formatted_lines.append(line)
    
    # Simply join all lines with a single newline
    result = "\n".join(formatted_lines)
    
    return result