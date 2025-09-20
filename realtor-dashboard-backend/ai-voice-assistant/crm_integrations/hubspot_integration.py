import os
import requests
from datetime import datetime
import time
from dotenv import load_dotenv
from call_logger import get_call_logger

load_dotenv()

class HubSpotIntegration:
    def __init__(self):
        self.api_key = os.getenv('HUBSPOT_API_KEY')
        self.base_url = 'https://api.hubapi.com'
        self.logger = get_call_logger()
        
        if not self.api_key:
            raise ValueError("HUBSPOT_API_KEY not found in environment variables")
    
    def _get_headers(self):
        """Get authentication headers for HubSpot API"""
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def create_contact(self, extracted_data):
        """Create a new contact in HubSpot from extracted call data"""
        try:
            properties = self._prepare_contact_properties(extracted_data)
            contact_data = {"properties": properties}
            
            url = f'{self.base_url}/crm/v3/objects/contacts'
            response = requests.post(url, headers=self._get_headers(), json=contact_data, timeout=10)
            
            if response.status_code == 201:
                contact_info = response.json()
                contact_id = contact_info.get('id')
                self.logger.info(f"✅ HubSpot contact created successfully: {contact_id}")
                return True, contact_id, "Contact created successfully"
                
            elif response.status_code == 409:
                self.logger.info("Contact already exists, attempting to find existing...")
                return self._handle_existing_contact(extracted_data, response)
                
            else:
                error_msg = f"HubSpot API error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Failed to create HubSpot contact: {str(e)}"
            self.logger.error(error_msg)
            return False, None, error_msg
    
    def log_call_activity(self, contact_id, extracted_data):
        """Log the call as an activity in HubSpot timeline"""
        try:
            # Get timestamp from call data or use current time
            call_timestamp = extracted_data.get('call_start_time')
            if call_timestamp:
                timestamp_ms = int(call_timestamp.timestamp() * 1000)
            else:
                timestamp_ms = int(time.time() * 1000)
            
            # Format transcript for HubSpot
            transcript = extracted_data.get('transcript', '')
            if transcript:
                formatted_transcript = f"TRANSCRIPT:\n\n{transcript}"
            else:
                formatted_transcript = f"After-hours AI call - {extracted_data.get('reason_for_call', 'General inquiry')}"
            
            # Get call duration in seconds
            duration = extracted_data.get('call_duration', 0)
            if isinstance(duration, (int, float)):
                duration_seconds = int(duration)
            else:
                duration_seconds = 180  # Default 3 minutes
            
            call_properties = {
                "hs_timestamp": timestamp_ms,
                "hs_call_body": formatted_transcript,
                "hs_call_direction": "INBOUND",
                "hs_call_duration": duration_seconds,
                "hs_call_from_number": extracted_data.get('phone', ''),
                "hs_call_status": "COMPLETED",
                "hs_call_title": f"After-hours AI call - {extracted_data.get('reason_for_call', 'General inquiry')[:50]}"
            }
            
            call_data = {
                "properties": call_properties,
                "associations": [
                    {
                        "to": {"id": contact_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 194}]
                    }
                ]
            }
            
            url = f'{self.base_url}/crm/v3/objects/calls'
            response = requests.post(url, headers=self._get_headers(), json=call_data, timeout=10)
            
            if response.status_code == 201:
                call_info = response.json()
                call_id = call_info.get('id')
                self.logger.info(f"✅ Call activity logged successfully: {call_id}")
                return True, call_id
            else:
                self.logger.error(f"Failed to log call: {response.status_code} - {response.text}")
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error logging call activity: {e}")
            return False, None
    
    def create_contact_with_call_log(self, extracted_data):
        """Create contact and log the call activity"""
        try:
            # First create the contact
            success, contact_id, message = self.create_contact(extracted_data)
            
            if success and contact_id:
                # Then log the call activity
                call_logged, call_id = self.log_call_activity(contact_id, extracted_data)
                
                if call_logged:
                    self.logger.info(f"✅ Complete: Contact {contact_id} + Call {call_id}")
                    return True, contact_id, call_id, "Contact and call logged successfully"
                else:
                    self.logger.warning(f"⚠️ Contact created but call logging failed")
                    return True, contact_id, None, "Contact created, call logging failed"
            
            return False, None, None, message
            
        except Exception as e:
            error_msg = f"Failed to create contact with call log: {str(e)}"
            self.logger.error(error_msg)
            return False, None, None, error_msg
    
    def _prepare_contact_properties(self, extracted_data):
        """Convert extracted data to HubSpot contact properties"""
        properties = {}
        
        # Core contact fields
        if extracted_data.get('first_name'):
            properties['firstname'] = extracted_data['first_name']
        if extracted_data.get('last_name'):
            properties['lastname'] = extracted_data['last_name']
        if extracted_data.get('email'):
            properties['email'] = extracted_data['email']
        if extracted_data.get('phone'):
            properties['phone'] = extracted_data['phone']
        if extracted_data.get('company'):
            properties['company'] = extracted_data['company']
        if extracted_data.get('reason_for_call'):
            properties['reason_for_call'] = extracted_data['reason_for_call']
        
        self.logger.info(f"Prepared HubSpot properties: {properties}")
        return properties
    
    def _handle_existing_contact(self, extracted_data, conflict_response):
        """Handle case where contact already exists"""
        try:
            email = extracted_data.get('email')
            if email:
                existing_contact = self._find_contact_by_email(email)
                if existing_contact:
                    contact_id = existing_contact.get('id')
                    self.logger.info(f"Found existing contact: {contact_id}")
                    return True, contact_id, "Contact already exists"
            
            return False, None, "Contact exists but couldn't retrieve ID"
            
        except Exception as e:
            return False, None, f"Error handling existing contact: {str(e)}"
    
    def _find_contact_by_email(self, email):
        """Find existing contact by email"""
        try:
            url = f'{self.base_url}/crm/v3/objects/contacts/search'
            search_data = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "email",
                                "operator": "EQ",
                                "value": email
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(url, headers=self._get_headers(), json=search_data, timeout=10)
            
            if response.status_code == 200:
                results = response.json().get('results', [])
                if results:
                    return results[0]
                    
        except Exception as e:
            self.logger.error(f"Error searching for contact: {e}")
            
        return None

def push_to_hubspot(extracted_data):
    """Enhanced function to push contact + call activity to HubSpot"""
    try:
        hubspot = HubSpotIntegration()
        success, contact_id, call_id, message = hubspot.create_contact_with_call_log(extracted_data)
        
        if success:
            print(f"✅ HubSpot integration successful:")
            print(f"   📋 Contact ID: {contact_id}")
            if call_id:
                print(f"   📞 Call ID: {call_id}")
                print(f"   📝 Transcript logged to timeline")
            print(f"   🏷️ Tagged as after-hours AI call")
        else:
            print(f"❌ HubSpot integration failed: {message}")
            
        return success
        
    except Exception as e:
        print(f"❌ HubSpot integration error: {e}")
        return False