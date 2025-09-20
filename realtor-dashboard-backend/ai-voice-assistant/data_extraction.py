
# This module processes completed call transcripts and extracts structured data for storage in the database and integration with CRM systems.
#
# Main Function:
# - process_full_transcript(): Primary entry point for post-call processing
#
# Processing Flow:
# 1. Receive raw transcript from websocket_handler
# 2. Analyze call completion status (completed_positive, hangup, etc.)
# 3. Extract structured data using Gemini AI (from shared_state)
# 4. Fallback to traditional text extraction if needed
# 5. Add call timing and metadata (SID, duration, etc.)
# 6. Update lead record in database via database_operations
# 7. Push to primary CRM system based on PRIMARY_CRM setting
# 8. Send email notification to realtor
#

import datetime
from database_operations import update_lead_info
from datetime import datetime
from text_extractors import extract_data
from transcript_analysis import analyze_call_completion, format_transcript_simple
from notification_service import send_after_hours_notification
from database_operations import get_db, update_lead_info
from crm_integrations.base_crm import push_to_crm
import os


def process_full_transcript(transcript, lead_id, shared_state, chat=None):
    if lead_id is None:
        print("Error: No lead ID provided. Cannot process transcript.")
        return

    try:
        db = get_db()
        if not db.check_connection_health():
            print("Database connection was restored before transcript processing")
        full_text = '\n'.join(transcript)
        print("Full transcript:")
        print(full_text)
        
        formatted_transcript = format_transcript_simple(transcript, shared_state)

        detailed_status = analyze_call_completion(transcript)
        print(f"Analyzed call completion status: {detailed_status}")

       
        extracted_data = shared_state.get_extracted_lead_data()
        
        if not extracted_data:
            print("No extracted data found, falling back to traditional extraction")
            # Fall back to traditional extraction if no structured data is available
            extracted_data = extract_data(full_text)
        else:
            print(f"Using structured data extracted by Gemini: {extracted_data}")

        extracted_data["created_at"] = datetime.now()
        extracted_data["transcript"] = full_text
        extracted_data['call_status'] = detailed_status
        extracted_data['call_sid'] = shared_state.get_call_sid()

        # Add call timing information
        extracted_data['call_start_time'] = shared_state.get_call_start_time()
        extracted_data['call_end_time'] = shared_state.get_call_end_time()
        extracted_data['call_duration'] = shared_state.get_call_duration()

        #extracted_data['next_call_timestamp'] = next_call_timestamp

        # Use SharedState to get additional lead info
        lead_info = shared_state.get_lead_info()
        if lead_info:
            extracted_data["name"] = extracted_data.get("name", lead_info.get('name', "Unknown"))
            extracted_data["email"] = extracted_data.get("email", lead_info.get('email', "unknown@example.com"))
            extracted_data["phone"] = extracted_data.get("phone", lead_info.get('phone', ""))
            
            # Include FollowUpBoss person ID if available (for updating existing records)
            if lead_info.get('followupboss_person_id'):
                extracted_data["followupboss_person_id"] = lead_info['followupboss_person_id']
                print(f"ðŸ”— Found FollowUpBoss person ID: {lead_info['followupboss_person_id']}")

        # Send email notification
        send_after_hours_notification(
            extracted_data.get("name", lead_info.get('name', "Unknown")),
            extracted_data.get("phone", lead_info.get('phone', "")),
            extracted_data.get("email", lead_info.get('email', "unknown@example.com")),
            extracted_data.get("reason_for_call", "Not specified"),
            extracted_data.get("company", "Not specified"),
            formatted_transcript
        )

        # CRM Integration - uses PRIMARY_CRM environment variable
        crm_enabled = os.getenv('CRM_ENABLED', 'true').lower() == 'true'
        if crm_enabled:
            try:
                print("CRM integration is enabled, pushing data to primary CRM...")
                success = push_to_crm(extracted_data)
                if success:
                    print("âœ… Successfully pushed data to CRM")
                else:
                    print("âŒ Failed to push data to CRM")
            except Exception as e:
                print(f"CRM integration failed: {e}")
        else:
            print("CRM integration is disabled (CRM_ENABLED=false)")
        
        
        if not db.check_connection_health():
            print("Database connection was restored before lead update")
        modified_count = update_lead_info(lead_id, extracted_data)

        print(f"Updated document for lead ID: {lead_id}")
        print(f"Modified count: {modified_count}")
        
        if modified_count == 0:
            print(f"Warning: Document for lead ID {lead_id} was not modified. This could mean the data didn't change.")

    except Exception as e:
        print(f"An error occurred while processing transcript for lead {lead_id}: {e}")