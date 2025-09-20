#!/usr/bin/env python3
"""
Batch Outbound Caller for Real Estate AI Voice Assistant

This script fetches contacts from FollowUpBoss with call_action='call' 
and makes outbound calls to them automatically.

Usage:
    python batch_outbound_caller.py [--dry-run] [--limit N] [--realtor-id ID]
"""

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from twilio.rest import Client
import requests
import base64
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from database_operations import create_new_lead, get_realtor_by_phone
from call_logger import get_call_logger

# Load environment variables
load_dotenv('.env.docker')

class BatchOutboundCaller:
    def __init__(self, ngrok_url=None):
        self.logger = get_call_logger()
        
        # Twilio setup
        self.twilio_client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        self.from_number = os.getenv('TWILIO_FROM_NUMBER')
        
        # FollowUpBoss setup
        self.fub_api_key = os.getenv('FOLLOWUPBOSS_API_KEY')
        self.fub_base_url = 'https://api.followupboss.com/v1'
        
        # Configuration
        self.ngrok_url = ngrok_url or os.getenv('NGROK_URL')
        self.default_realtor_id = 1
        
        # Call rate limiting (respect business hours and avoid spam)
        self.call_delay_seconds = 30  # 30 seconds between calls
        self.max_calls_per_hour = 20  # Conservative rate limit
        self.business_hours = (9, 18)  # 9 AM to 6 PM
        
        if not all([self.twilio_client, self.fub_api_key]):
            raise ValueError("Missing required environment variables: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or FOLLOWUPBOSS_API_KEY")
    
    def _get_fub_headers(self):
        """Get FollowUpBoss API headers"""
        credentials = base64.b64encode(f'{self.fub_api_key}:'.encode()).decode()
        return {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json'
        }
    
    def fetch_contacts_to_call(self, limit=50):
        """Fetch contacts from FollowUpBoss that need to be called"""
        try:
            # FollowUpBoss API to get people with custom field call_action='call'
            url = f'{self.fub_base_url}/people'
            params = {
                'limit': limit,
                'offset': 0
            }
            
            response = requests.get(url, headers=self._get_fub_headers(), params=params)
            
            if response.status_code != 200:
                self.logger.error(f"Failed to fetch contacts: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            people = data.get('people', [])
            
            # Filter for contacts that need calling
            contacts_to_call = []
            for person in people:
                # Check if person has call_action field set to 'call'
                if self._should_call_contact(person):
                    contacts_to_call.append(person)
            
            self.logger.info(f"Found {len(contacts_to_call)} contacts to call out of {len(people)} total")
            return contacts_to_call
            
        except Exception as e:
            self.logger.error(f"Error fetching contacts: {e}")
            return []
    
    def _should_call_contact(self, person):
        """Determine if a contact should be called based on call_action only"""
        call_action = person.get('customCallAction', '')
        
        # Skip if marked as do not call
        if call_action == 'do_not_call':
            return False
        
        # Manual control: call if explicitly marked for calling
        if call_action == 'call':
            return True
        
        # Fallback: Check tags for manual marking
        tags = person.get('tags', [])
        if any(tag.lower() in ['call needed', 'follow up call', 'call back'] for tag in tags):
            return True
        
        return False
    
    def _is_business_hours(self):
        """Check if it's currently business hours"""
        current_hour = datetime.now().hour
        return self.business_hours[0] <= current_hour < self.business_hours[1]
    
    def make_outbound_call(self, contact, realtor_id=None, existing_lead_id=None):
        """Make an outbound call to a specific contact"""
        try:
            # Get phone number
            phones = contact.get('phones', [])
            if not phones:
                self.logger.warning(f"No phone number for contact {contact.get('id')}")
                return False
            
            phone_number = phones[0].get('value', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not phone_number.startswith('+'):
                phone_number = '+1' + phone_number  # Assume North American number
            
            # Use existing lead_id or create new one
            if existing_lead_id:
                lead_id = existing_lead_id
                self.logger.info(f"Using existing lead_id: {lead_id}")
            else:
                realtor_id = realtor_id or self.default_realtor_id
                lead_id = create_new_lead(phone_number, realtor_id)
                
                if not lead_id:
                    self.logger.error(f"Failed to create lead for {phone_number}")
                    return False
            
            self.logger.info(f"Making outbound call to {contact.get('name', 'Unknown')} at {phone_number}")
            
            # Make the call
            call = self.twilio_client.calls.create(
                to=phone_number,
                from_=self.from_number,
                url=f"{self.ngrok_url}/voice-call?lead_id={lead_id}",
                method='POST',
                status_callback=f"{self.ngrok_url}/call-status?lead_id={lead_id}",
                status_callback_event=['initiated', 'ringing', 'answered', 'completed',
                                     'no-answer', 'busy', 'failed', 'canceled'],
                status_callback_method='POST',
                timeout=20
            )
            
            self.logger.info(f"✅ Call initiated: {call.sid} to {contact.get('name', 'Unknown')}")
            
            # Update FollowUpBoss contact to mark as called
            self._mark_contact_as_called(contact['id'])
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to call {contact.get('name', 'Unknown')}: {e}")
            return False
    
    def _mark_contact_as_called(self, person_id):
        """Mark contact in FollowUpBoss as having been called"""
        try:
            # Update the person's fields with correct FollowUpBoss field names
            url = f'{self.fub_base_url}/people/{person_id}'
            
            update_data = {
                'customCallAction': 'called',  # Use correct custom field name
                'tags': ['outbound_call_initiated', 'AI_call_in_progress']  # Add tags for tracking
            }
            
            # Send PUT request to update the contact
            update_response = requests.put(url, headers=self._get_fub_headers(), json=update_data)
            
            if update_response.status_code == 200:
                self.logger.info(f"✅ Updated contact {person_id}: customCallAction = 'called', added tags")
            else:
                self.logger.warning(f"Failed to update contact: {update_response.status_code} - {update_response.text}")
            
            # Add a note about the call for timeline tracking
            note_data = {
                'personId': person_id,
                'body': f'Outbound AI call initiated on {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\nCall placed via batch outbound calling system. Full conversation and results will be logged automatically upon call completion.\n\nFollow-up scheduling managed by FollowUpBoss Action Plans.',
                'subject': 'Batch Outbound Call - AI Assistant',
                'type': 'Call'
            }
            
            # Create note
            note_url = f'{self.fub_base_url}/notes'
            note_response = requests.post(note_url, headers=self._get_fub_headers(), json=note_data)
            
            if note_response.status_code == 201:
                self.logger.info(f"✅ Added call note to contact {person_id} timeline")
            else:
                self.logger.warning(f"Failed to add call note: {note_response.status_code} - {note_response.text}")
            
        except Exception as e:
            self.logger.error(f"Failed to mark contact as called: {e}")
    
    def run_batch_calls(self, limit=10, dry_run=False, realtor_id=None):
        """Run batch outbound calling process"""
        self.logger.info(f"Starting batch outbound calling {'(DRY RUN)' if dry_run else ''}")
        
        if not self._is_business_hours():
            self.logger.warning("Outside business hours - skipping batch calls")
            return
        
        # Fetch contacts to call
        contacts = self.fetch_contacts_to_call(limit=limit * 2)  # Fetch extra in case some are filtered out
        
        if not contacts:
            self.logger.info("No contacts found that need calling")
            return
        
        # Limit to requested number
        contacts = contacts[:limit]
        
        self.logger.info(f"Processing {len(contacts)} contacts for outbound calling")
        
        successful_calls = 0
        failed_calls = 0
        
        for i, contact in enumerate(contacts):
            contact_name = contact.get('name', f"Contact {contact.get('id')}")
            
            if dry_run:
                self.logger.info(f"[DRY RUN] Would call: {contact_name}")
                continue
            
            self.logger.info(f"Processing contact {i+1}/{len(contacts)}: {contact_name}")
            
            # Make the call
            success = self.make_outbound_call(contact, realtor_id)
            
            if success:
                successful_calls += 1
            else:
                failed_calls += 1
            
            # Rate limiting - wait between calls
            if i < len(contacts) - 1:  # Don't wait after the last call
                self.logger.info(f"Waiting {self.call_delay_seconds} seconds before next call...")
                time.sleep(self.call_delay_seconds)
        
        # Summary
        self.logger.info(f"Batch calling completed:")
        self.logger.info(f"  ✅ Successful calls: {successful_calls}")
        self.logger.info(f"  ❌ Failed calls: {failed_calls}")
        self.logger.info(f"  📞 Total processed: {len(contacts)}")

def main():
    parser = argparse.ArgumentParser(description='Batch Outbound Caller for Real Estate AI')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be called without making actual calls')
    parser.add_argument('--limit', type=int, default=10, help='Maximum number of calls to make (default: 10)')
    parser.add_argument('--realtor-id', type=int, help='Specific realtor ID to assign calls to')
    
    args = parser.parse_args()
    
    try:
        caller = BatchOutboundCaller()
        caller.run_batch_calls(
            limit=args.limit,
            dry_run=args.dry_run,
            realtor_id=args.realtor_id
        )
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()