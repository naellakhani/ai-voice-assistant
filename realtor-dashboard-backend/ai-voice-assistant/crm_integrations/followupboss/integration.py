"""
FollowUpBoss CRM Integration

This implements the BaseCRMIntegration interface for FollowUpBoss.
All existing logic is preserved - this just wraps it in the standard interface.
"""

import os
import requests
from datetime import datetime
import time
import base64
from dotenv import load_dotenv
from call_logger import get_call_logger
from crm_integrations.base_crm import BaseCRMIntegration

load_dotenv()


class FollowUpBossIntegration(BaseCRMIntegration):
    """FollowUpBoss implementation of the CRM interface"""
    
    def __init__(self):
        super().__init__()
        self.api_key = os.getenv('FOLLOWUPBOSS_API_KEY')
        self.base_url = 'https://api.followupboss.com/v1'
        self.logger = get_call_logger()
        
        if not self.api_key:
            raise ValueError("FOLLOWUPBOSS_API_KEY not found in environment variables")
    
    def get_crm_name(self) -> str:
        """Return the name of this CRM"""
        return "FollowUpBoss"
    
    def _get_headers(self):
        """Get authentication headers for FollowUpBoss API"""
        # FollowUpBoss uses HTTP Basic Auth with api_key:blank_password
        credentials = base64.b64encode(f'{self.api_key}:'.encode()).decode()
        
        return {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json'
        }
    
    def search_person_by_phone(self, phone_number):
        """Search for existing person by phone number"""
        try:
            url = f'{self.base_url}/people'
            params = {
                'phone': phone_number,
                'limit': 5
            }
            
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                people = data.get('people', [])
                
                if people:
                    person = people[0]
                    person_id = person.get('id')
                    self.logger.info(f"Found existing person: {person.get('name', 'No name')} ({person_id})")
                    return True, person_id, person
                else:
                    self.logger.info("No existing person found")
                    return False, None, None
            else:
                self.logger.error(f"Search failed: {response.status_code} - {response.text}")
                return False, None, None
                
        except Exception as e:
            self.logger.error(f"Error searching for person: {e}")
            return False, None, None
    
    def create_person(self, extracted_data):
        """Create a new person/lead in FollowUpBoss from extracted call data"""
        try:
            person_data = self._prepare_person_data(extracted_data)
            
            url = f'{self.base_url}/people'
            response = requests.post(url, headers=self._get_headers(), json=person_data, timeout=10)
            
            if response.status_code == 201:
                person_info = response.json()
                person_id = person_info.get('id')
                self.logger.info(f"✅ FollowUpBoss person created successfully: {person_id}")
                return True, person_id, "Person created successfully"
            else:
                error_msg = f"FollowUpBoss API error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Failed to create FollowUpBoss person: {str(e)}"
            self.logger.error(error_msg)
            return False, None, error_msg
    
    def update_existing_person(self, person_id, extracted_data):
        """Update an existing person in FollowUpBoss with new data from call"""
        try:
            person_data = self._prepare_person_update_data(extracted_data)
            
            url = f'{self.base_url}/people/{person_id}'
            response = requests.put(url, headers=self._get_headers(), json=person_data, timeout=10)
            
            if response.status_code == 200:
                self.logger.info(f"✅ FollowUpBoss person updated successfully: {person_id}")
                return True
            else:
                error_msg = f"FollowUpBoss update error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Failed to update FollowUpBoss person: {str(e)}"
            self.logger.error(error_msg)
            return False
    
    def create_note_with_transcript(self, person_id, extracted_data):
        """Create a note with call transcript in FollowUpBoss timeline"""
        try:
            # Format the call transcript and details
            transcript = extracted_data.get('transcript', '')
            reason = extracted_data.get('reason_for_call', 'General inquiry')
            
            # Build formatted note body
            note_body = f"AI Call Transcript - After Hours Inquiry\n\n"
            
            if transcript:
                note_body += f"{transcript}\n\n"
            
            note_body += "---\n"
            note_body += f"Call Status: {extracted_data.get('call_status', 'completed')}\n"
            
            if extracted_data.get('call_duration'):
                duration = extracted_data.get('call_duration')
                if isinstance(duration, (int, float)):
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    note_body += f"Call Duration: {minutes}m {seconds}s\n"
            
            if extracted_data.get('company'):
                note_body += f"Lead Company: {extracted_data['company']}\n"
                
            note_body += f"Reason for Call: {reason}\n"
            note_body += f"Source: AI Voice Assistant - After Hours"
            
            note_data = {
                "personId": person_id,
                "body": note_body,
                "subject": f"AI Voice Assistant Call - {reason[:30]}...",
                "type": "Call"
            }
            
            url = f'{self.base_url}/notes'
            response = requests.post(url, headers=self._get_headers(), json=note_data, timeout=10)
            
            if response.status_code == 201:
                note_info = response.json()
                note_id = note_info.get('id')
                self.logger.info(f"✅ Call transcript logged successfully: {note_id}")
                return True, note_id
            else:
                self.logger.error(f"Failed to create note: {response.status_code} - {response.text}")
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error creating note: {e}")
            return False, None
    
    def create_person_with_call_log(self, extracted_data):
        """Create person, log call transcript, and create follow-up task"""
        try:
            # Check if we have a FollowUpBoss person ID (from webhook)
            followupboss_person_id = extracted_data.get('followupboss_person_id')
            
            if followupboss_person_id:
                # Update existing FollowUpBoss record
                self.logger.info(f"Updating existing FollowUpBoss person: {followupboss_person_id}")
                success = self.update_existing_person(followupboss_person_id, extracted_data)
                if success:
                    person_id = followupboss_person_id
                    created_new = False
                else:
                    self.logger.error(f"Failed to update existing person {followupboss_person_id}")
                    return False, None, None, None, "Failed to update existing person"
            else:
                # Original logic for phone-based search
                phone = extracted_data.get('phone', '')
                if phone:
                    exists, existing_id, existing_person = self.search_person_by_phone(phone)
                    if exists:
                        self.logger.info(f"Updating existing person: {existing_id}")
                        success = self.update_existing_person(existing_id, extracted_data)
                        if success:
                            person_id = existing_id
                            created_new = False
                        else:
                            self.logger.error(f"Failed to update existing person {existing_id}")
                            return False, None, None, None, "Failed to update existing person"
                    else:
                        # Create new person
                        success, person_id, message = self.create_person(extracted_data)
                        if not success:
                            return False, None, None, None, message
                        created_new = True
                else:
                    # No phone number, create new person
                    success, person_id, message = self.create_person(extracted_data)
                    if not success:
                        return False, None, None, None, message
                    created_new = True
            
            # Log the call transcript
            note_logged, note_id = self.create_note_with_transcript(person_id, extracted_data)
            
            # Determine success status
            if note_logged:
                status_msg = f"Complete: Person {'created' if created_new else 'updated'}, call transcript logged"
                self.logger.info(f"✅ {status_msg}")
                return True, person_id, note_id, None, status_msg
            else:
                status_msg = f"Partial: Person {'created' if created_new else 'updated'}, but call logging failed"
                self.logger.warning(f"⚠️ {status_msg}")
                return True, person_id, None, None, status_msg
            
        except Exception as e:
            error_msg = f"Failed to create person with call log: {str(e)}"
            self.logger.error(error_msg)
            return False, None, None, None, error_msg
    
    # Webhook Support Methods
    def supports_webhooks(self) -> bool:
        """FollowUpBoss supports webhooks"""
        return True
    
    def register_webhooks(self, webhook_url: str) -> bool:
        """Register webhooks with FollowUpBoss API for both peopleCreated and peopleUpdated"""
        try:
            # Get environment variables
            x_system = os.getenv('FOLLOWUPBOSS_X_SYSTEM')
            x_system_key = os.getenv('FOLLOWUPBOSS_X_SYSTEM_KEY')
            
            # Prepare headers
            headers = self._get_headers()
            
            # Add X-System headers if provided
            if x_system:
                headers['X-System'] = x_system
            if x_system_key:
                headers['X-System-Key'] = x_system_key
            
            # Register both peopleCreated and peopleUpdated webhooks
            events_to_register = ['peopleCreated', 'peopleUpdated']
            success_count = 0
            
            self.logger.info("Checking for existing FollowUpBoss webhooks...")
            list_response = requests.get(
                f'{self.base_url}/webhooks',
                headers=headers,
                timeout=10
            )
            
            existing_webhooks = []
            if list_response.status_code == 200:
                existing_webhooks = list_response.json().get('webhooks', [])
                self.logger.info(f"Found {len(existing_webhooks)} existing webhooks")
            
            for event_name in events_to_register:
                # Check if webhook already exists for this event
                existing_event_webhooks = [w for w in existing_webhooks if w.get('event') == event_name]
                webhook_exists = any(w.get('url') == webhook_url for w in existing_event_webhooks)
                
                if webhook_exists:
                    self.logger.info(f"✅ {event_name} webhook already exists for our URL")
                    success_count += 1
                    continue
                
                # Clean up old webhooks for this event if any exist
                if existing_event_webhooks:
                    self.logger.info(f"Cleaning up {len(existing_event_webhooks)} old {event_name} webhooks...")
                    for webhook in existing_event_webhooks:
                        webhook_id = webhook.get('id')
                        delete_url = f"{self.base_url}/webhooks/{webhook_id}"
                        delete_response = requests.delete(delete_url, headers=headers, timeout=10)
                        
                        if delete_response.status_code == 204:
                            self.logger.info(f"🗑️ Deleted old {event_name} webhook: {webhook.get('url', 'Unknown URL')}")
                        else:
                            self.logger.warning(f"Failed to delete {event_name} webhook {webhook_id}: {delete_response.status_code}")
                
                # Register the webhook
                webhook_data = {
                    'url': webhook_url,
                    'event': event_name
                }
                
                self.logger.info(f"Registering FollowUpBoss webhook for {event_name}: {webhook_url}")
                
                response = requests.post(
                    f'{self.base_url}/webhooks',
                    headers=headers,
                    json=webhook_data,
                    timeout=10
                )
                
                if response.status_code == 201:
                    webhook_info = response.json()
                    webhook_id = webhook_info.get('id')
                    self.logger.info(f"✅ {event_name} webhook registered successfully!")
                    self.logger.info(f"   🔗 Webhook ID: {webhook_id}")
                    self.logger.info(f"   📍 URL: {webhook_url}")
                    success_count += 1
                elif response.status_code == 409:
                    self.logger.info(f"⚠️ {event_name} webhook already exists: {webhook_url}")
                    success_count += 1  # Consider this success since webhook exists
                else:
                    self.logger.error(f"Failed to register {event_name} webhook: {response.status_code}")
                    self.logger.error(f"Response: {response.text}")
            
            # Return success if we registered or confirmed both webhooks
            if success_count == len(events_to_register):
                self.logger.info(f"✅ All FollowUpBoss webhooks registered successfully!")
                self.logger.info(f"   📋 Events: {', '.join(events_to_register)}")
                self.logger.info(f"   📍 URL: {webhook_url}")
                return True
            else:
                self.logger.error(f"❌ Failed to register all webhooks. Success: {success_count}/{len(events_to_register)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error registering FollowUpBoss webhook: {e}")
            return False
    
    def handle_webhook_data(self, webhook_data):
        """Process incoming FollowUpBoss webhook data"""
        try:
            # Extract webhook event type - FollowUpBoss format
            event_type = webhook_data.get('event')
            if event_type not in ['peopleCreated', 'peopleUpdated']:
                return {'status': 'ignored', 'reason': f'Event type {event_type} not handled'}
            
            # FollowUpBoss webhook format: get person ID from resourceIds
            resource_ids = webhook_data.get('resourceIds', [])
            if not resource_ids:
                return {'status': 'error', 'reason': 'No resource IDs in webhook'}
            
            # Get the first person ID
            followupboss_person_id = str(resource_ids[0])
            
            # Fetch person data from FollowUpBoss API
            person_data = self.fetch_person_from_api(followupboss_person_id)
            if not person_data:
                return {'status': 'error', 'reason': 'Failed to fetch person data from API'}
            
            # Extract contact information
            lead_info = self._extract_lead_info_from_webhook(person_data)
            
            custom_call_action = person_data.get('customCallAction', '')
            person_tags = person_data.get('tags', [])
            
            # Trigger call if customCallAction = 'call' OR if schedule_call_2 tag is present
            should_call = (lead_info.get('phone') and 
                          (custom_call_action == 'call' or 'schedule_call_2' in person_tags))

            # Check if should make outbound call
            #if event_type == 'peopleCreated':
                # For new leads, always call if they have a phone number
             #   should_call = bool(lead_info.get('phone'))
            #else:
                # For updates, check manual triggers only
            #    custom_call_action = person_data.get('customCallAction', '')
            #    person_tags = person_data.get('tags', [])
            #    should_call = (lead_info.get('phone') and 
            #                  (custom_call_action == 'call' or 'schedule_call_2' in person_tags))
            
            return {
                'status': 'success',
                'event_type': 'person_created' if event_type == 'peopleCreated' else 'person_updated',
                'person_id': followupboss_person_id,
                'person_data': person_data,
                'should_call': should_call,
                'lead_info': lead_info
            }
            
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}
    
    def fetch_person_from_api(self, person_id):
        """Fetch person data from FollowUpBoss API using person ID"""
        try:
            # Fetch person data with custom fields
            url = f'{self.base_url}/people/{person_id}'
            params = {
                'fields': 'allFields'  # Request all fields including custom fields
            }
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=10)
            
            if response.status_code == 200:
                person_data = response.json()
                self.logger.info(f"✅ Fetched person data from API for ID: {person_id}")
                return person_data
            else:
                self.logger.error(f"Failed to fetch person data: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error fetching person from API: {e}")
            return None
    
    # Outbound Calling Support Methods
    def supports_outbound_calling(self) -> bool:
        """FollowUpBoss supports outbound calling via customCallAction field"""
        return True
    
    def fetch_contacts_to_call(self, limit=50):
        """Fetch contacts from FollowUpBoss that need outbound calls"""
        try:
            url = f'{self.base_url}/people'
            params = {
                'fields': 'allFields',
                'customCallAction': 'call',  # Only get contacts marked for calling
                'limit': limit
            }
            
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                people = data.get('people', [])
                
                # Filter contacts that should be called
                contacts_to_call = []
                for person in people:
                    if self._should_call_contact(person):
                        contacts_to_call.append(person)
                
                self.logger.info(f"Found {len(contacts_to_call)} contacts to call from FollowUpBoss")
                return contacts_to_call
            else:
                self.logger.error(f"Failed to fetch contacts: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error fetching contacts to call: {e}")
            return []
    
    def _should_call_contact(self, person):
        """Determine if a contact should be called based on FollowUpBoss business rules"""
        # Check if has phone number
        phones = person.get('phones', [])
        if not phones:
            return False
        
        # Check if customCallAction is 'call'
        if person.get('customCallAction') != 'call':
            return False
        
        # Add any other business logic here (e.g., not called recently, business hours, etc.)
        
        return True
    
    def mark_contact_as_called(self, person_id):
        """Mark contact in FollowUpBoss as having been called"""
        try:
            # Update the person's fields with correct FollowUpBoss field names
            url = f'{self.base_url}/people/{person_id}'
            
            update_data = {
                'customCallAction': 'called',  # Use correct custom field name
                'tags': ['outbound_call_initiated', 'AI_call_in_progress']  # Add tags for tracking
            }
            
            # Send PUT request to update the contact
            update_response = requests.put(url, headers=self._get_headers(), json=update_data)
            
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
            note_url = f'{self.base_url}/notes'
            note_response = requests.post(note_url, headers=self._get_headers(), json=note_data)
            
            if note_response.status_code == 201:
                self.logger.info(f"✅ Added call note to contact {person_id} timeline")
                return True
            else:
                self.logger.warning(f"Failed to add call note: {note_response.status_code} - {note_response.text}")
                return False
            
        except Exception as e:
            self.logger.error(f"Failed to mark contact as called: {e}")
            return False
    
    # Helper Methods (existing logic preserved)
    def _extract_lead_info_from_webhook(self, person_data):
        """Extract lead information from FollowUpBoss webhook person data"""
        lead_info = {}
        
        # Name components
        first_name = person_data.get('firstName', '')
        last_name = person_data.get('lastName', '')
        if first_name or last_name:
            lead_info['name'] = f"{first_name} {last_name}".strip()
        lead_info['first_name'] = first_name
        lead_info['last_name'] = last_name
        
        # Phone number
        phones = person_data.get('phones', [])
        if phones:
            # Get first phone number
            phone = phones[0].get('value', '').strip()
            if phone:
                lead_info['phone'] = phone
        
        # Email
        emails = person_data.get('emails', [])
        if emails:
            # Get first email
            email = emails[0].get('value', '').strip()
            if email:
                lead_info['email'] = email
        
        # Source information - parse the source field properly
        source = person_data.get('source', 'FollowUpBoss Webhook')
        lead_info['source'] = source
        lead_info['lead_source'] = source  # Also store as lead_source for compatibility
        
        # Tags - ensure it's a list
        tags = person_data.get('tags', [])
        if isinstance(tags, str):
            tags = [tags]  # Convert single tag to list
        lead_info['tags'] = tags
        
        # Extract agent name from collaborators
        agent_name = None
        collaborators = person_data.get('collaborators', [])
        print(f"🔍 [DEBUG] Collaborators found: {collaborators}")
        print(f"🔍 [DEBUG] Collaborators type: {type(collaborators)}")
        print(f"🔍 [DEBUG] Collaborators length: {len(collaborators) if collaborators else 0}")
        
        if collaborators:
            # Find the assigned collaborator
            for i, collab in enumerate(collaborators):
                print(f"🔍 [DEBUG] Collaborator {i}: {collab}")
                if collab.get('assigned', False):
                    agent_name = collab.get('name', '').strip()
                    print(f"🔍 [DEBUG] Found assigned collaborator: {agent_name}")
                    break
            # If no assigned collaborator, take the first one
            if not agent_name and collaborators:
                agent_name = collaborators[0].get('name', '').strip()
                print(f"🔍 [DEBUG] Using first collaborator: {agent_name}")
        else:
            print(f"🔍 [DEBUG] No collaborators found in person_data")
        
        # Extract property address from tags - assume first tag is the address
        property_address = None
        if tags:
            property_address = tags[0].strip()
        
        lead_info['agent_name'] = agent_name
        lead_info['property_address'] = property_address
        
        print(f"🔍 [DEBUG] Final extracted values:")
        print(f"   🏷️ Tags: {tags}")
        print(f"   👤 Agent name: '{agent_name}'")
        print(f"   🏠 Property address: '{property_address}'")
        
        # Add FollowUpBoss person ID for reference
        lead_info['followupboss_person_id'] = person_data.get('id', '')
        
        # Extract any custom fields that might be useful for prompt formatting
        custom_fields = {}
        for key, value in person_data.items():
            if key.startswith('custom') and value:
                custom_fields[key] = value
        lead_info['custom_fields'] = custom_fields
        
        return lead_info
    
    def _prepare_person_update_data(self, extracted_data):
        """Prepare data for updating existing FollowUpBoss person (only update non-empty fields)"""
        person_data = {}
        
        # Only update fields that have values
        if extracted_data.get('first_name'):
            person_data['firstName'] = extracted_data['first_name']
        if extracted_data.get('last_name'):
            person_data['lastName'] = extracted_data['last_name']
        
        # Email array format (only if new email provided)
        if extracted_data.get('email'):
            email = extracted_data['email']
            # Handle unknown/invalid emails for failed calls - don't update if unknown
            if email.lower() not in ['unknown', 'not provided', 'none', '', 'unknown@example.com']:
                person_data['emails'] = [
                    {
                        "value": email,
                        "type": "Work"
                    }
                ]
        
        # Real estate specific fields (using FollowUpBoss custom field naming)
        if extracted_data.get('bedrooms'):
            person_data['customBedrooms'] = int(extracted_data['bedrooms']) if extracted_data['bedrooms'].isdigit() else extracted_data['bedrooms']
        if extracted_data.get('bathrooms'):
            person_data['customBathrooms'] = int(extracted_data['bathrooms']) if extracted_data['bathrooms'].isdigit() else extracted_data['bathrooms']
        if extracted_data.get('property_type'):
            person_data['customPropertyType'] = extracted_data['property_type']
        if extracted_data.get('parking'):
            person_data['customParking'] = extracted_data['parking']
        if extracted_data.get('budget'):
            person_data['customBudget'] = extracted_data['budget']
        if extracted_data.get('pre_approval'):
            person_data['customPreApproval'] = extracted_data['pre_approval']
        if extracted_data.get('timeline'):
            person_data['customTimeline'] = extracted_data['timeline']
        if extracted_data.get('realtor_status'):
            person_data['customRealtorStatus'] = extracted_data['realtor_status']
        if extracted_data.get('lead_status'):
            person_data['customLeadStatus'] = extracted_data['lead_status']
        
        # Lead stage - push to regular FollowUpBoss 'stage' field
        call_status = extracted_data.get('call_status', '')
        if call_status in ['immediate_hangup', 'hangup']:
            # For calls that didn't connect, keep stage as "Lead"
            person_data['stage'] = 'Lead'
        elif extracted_data.get('lead_stage'):
            # For completed calls, use the AI-evaluated lead stage
            person_data['stage'] = extracted_data['lead_stage']
        
        # IMPORTANT: Mark call as completed to prevent webhook loops
        person_data['customCallAction'] = 'completed'
        
        # Add tags (merge with existing)
        new_tags = ["AI Call Update"]
        
        # Add call status tags for Action Plan triggers
        call_status = extracted_data.get('call_status', '')
        if call_status in ['immediate_hangup', 'hangup']:
            new_tags.append("call_did_not_pick_up")
        elif call_status in ['completed_negative', 'completed_positive']:
            new_tags.append("call_completed")
        
        person_data['tags'] = new_tags
        
        self.logger.info(f"Prepared FollowUpBoss update data: {person_data}")
        return person_data
    
    def _prepare_person_data(self, extracted_data):
        """Convert extracted data to FollowUpBoss person format"""
        person_data = {}
        
        # Core fields - note: no "name" field, FollowUpBoss builds it from firstName + lastName
        if extracted_data.get('first_name'):
            person_data['firstName'] = extracted_data['first_name']
        if extracted_data.get('last_name'):
            person_data['lastName'] = extracted_data['last_name']
        
        # Email array format
        if extracted_data.get('email'):
            email = extracted_data['email']
            # Handle unknown/invalid emails for failed calls
            if email.lower() in ['unknown', 'not provided', 'none', '']:
                email = 'unknown@example.com'
            person_data['emails'] = [
                {
                    "value": email,
                    "type": "Work"
                }
            ]
        
        # Phone array format
        if extracted_data.get('phone'):
            person_data['phones'] = [
                {
                    "value": extracted_data['phone'],
                    "type": "Mobile"
                }
            ]
        
        # Real estate specific fields (using FollowUpBoss custom field naming)
        if extracted_data.get('bedrooms'):
            person_data['customBedrooms'] = int(extracted_data['bedrooms']) if extracted_data['bedrooms'].isdigit() else extracted_data['bedrooms']
        if extracted_data.get('bathrooms'):
            person_data['customBathrooms'] = int(extracted_data['bathrooms']) if extracted_data['bathrooms'].isdigit() else extracted_data['bathrooms']
        if extracted_data.get('property_type'):
            person_data['customPropertyType'] = extracted_data['property_type']
        if extracted_data.get('parking'):
            person_data['customParking'] = extracted_data['parking']
        if extracted_data.get('budget'):
            person_data['customBudget'] = extracted_data['budget']
        if extracted_data.get('pre_approval'):
            person_data['customPreApproval'] = extracted_data['pre_approval']
        if extracted_data.get('timeline'):
            person_data['customTimeline'] = extracted_data['timeline']
        if extracted_data.get('realtor_status'):
            person_data['customRealtorStatus'] = extracted_data['realtor_status']
        if extracted_data.get('lead_status'):
            person_data['customLeadStatus'] = extracted_data['lead_status']
        
        # FollowUpBoss specific fields
        person_data['source'] = "AI Voice Assistant - After Hours Call"
        
        # Lead stage - handle different call outcomes
        call_status = extracted_data.get('call_status', '')
        if call_status in ['immediate_hangup', 'hangup']:
            # For calls that didn't connect, keep stage as "Lead"
            person_data['stage'] = 'Lead'
        elif extracted_data.get('lead_stage'):
            # For completed calls, use the AI-evaluated lead stage
            person_data['stage'] = extracted_data['lead_stage']
        else:
            # Default for new leads
            person_data['stage'] = "New Lead"
        
        # IMPORTANT: Mark call as completed to prevent webhook loops
        person_data['customCallAction'] = 'completed'
        
        # Tags for categorization
        tags = ["AI Generated", "After Hours"]
        
        # Add call status tags for Action Plan triggers
        call_status = extracted_data.get('call_status', '')
        if call_status in ['immediate_hangup', 'hangup']:
            tags.append("call_did_not_pick_up")
        elif call_status in ['completed_negative', 'completed_positive']:
            tags.append("call_completed")
        
        person_data['tags'] = tags
        
        self.logger.info(f"Prepared FollowUpBoss person data: {person_data}")
        return person_data


# Convenience function to maintain backwards compatibility
def push_to_followupboss(extracted_data):
    """Main function to push contact + call activity to FollowUpBoss"""
    try:
        fub = FollowUpBossIntegration()
        success, person_id, note_id, task_id, message = fub.create_person_with_call_log(extracted_data)
        
        if success:
            print(f"✅ FollowUpBoss integration successful:")
            print(f"   👤 Person ID: {person_id}")
            if note_id:
                print(f"   📝 Call Note ID: {note_id}")
                print(f"   📞 Transcript logged to timeline")
            if task_id:
                print(f"   📋 Follow-up Task ID: {task_id}")
                print(f"   🎯 Task assigned for sales team")
            print(f"   🏷️ Tagged as after-hours AI call")
        else:
            print(f"❌ FollowUpBoss integration failed: {message}")
            
        return success
        
    except Exception as e:
        print(f"❌ FollowUpBoss integration error: {e}")
        return False