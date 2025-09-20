import os
import requests
from datetime import datetime
import time
from dotenv import load_dotenv
from call_logger import get_call_logger
import json

load_dotenv()

class ZohoIntegration:
    def __init__(self):
        self.client_id = os.getenv('ZOHO_CLIENT_ID')
        self.client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        self.refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
        self.access_token = os.getenv('ZOHO_ACCESS_TOKEN')
        # For Canada DC - use accounts.zohocloud.ca and zohoapis.ca
        self.region = os.getenv('ZOHO_REGION', 'ca')
        
        if self.region == 'ca':
            self.base_url = 'https://www.zohoapis.ca/crm/v2'
        elif self.region == 'eu':
            self.base_url = 'https://www.zohoapis.eu/crm/v2'
        elif self.region == 'in':
            self.base_url = 'https://www.zohoapis.in/crm/v2'
        else:
            self.base_url = 'https://www.zohoapis.com/crm/v2'
        self.logger = get_call_logger()
        
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError("Zoho credentials not found in environment variables")
    
    def _refresh_access_token(self):
        """Refresh the access token using refresh token"""
        try:
            # Use correct token URL for Canadian DC
            if self.region == 'ca':
                url = 'https://accounts.zohocloud.ca/oauth/v2/token'
            elif self.region == 'eu':
                url = 'https://accounts.zoho.eu/oauth/v2/token'
            elif self.region == 'in':
                url = 'https://accounts.zoho.in/oauth/v2/token'
            else:
                url = 'https://accounts.zoho.com/oauth/v2/token'
                
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': self.refresh_token
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                self.logger.info("✅ Zoho access token refreshed successfully")
                return True
            else:
                self.logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error refreshing Zoho token: {e}")
            return False
    
    def _get_headers(self):
        """Get authentication headers for Zoho API"""
        return {
            'Authorization': f'Zoho-oauthtoken {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method, endpoint, data=None, retry_on_auth_failure=True):
        """Make API request with automatic token refresh"""
        url = f'{self.base_url}/{endpoint}'
        headers = self._get_headers()
        
        try:
            if method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=10)
            elif method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=data, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # If unauthorized and we haven't tried refreshing yet
            if response.status_code == 401 and retry_on_auth_failure:
                self.logger.info("Access token expired, refreshing...")
                if self._refresh_access_token():
                    # Retry the request with new token
                    return self._make_request(method, endpoint, data, retry_on_auth_failure=False)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error making Zoho API request: {e}")
            raise
    
    def create_contact(self, extracted_data):
        """Create a new contact in Zoho CRM from extracted call data"""
        try:
            contact_data = {
                "data": [self._prepare_contact_data(extracted_data)]
            }
            
            response = self._make_request('POST', 'Contacts', contact_data)
            
            if response.status_code == 201:
                result = response.json()
                if result.get('data') and len(result['data']) > 0:
                    contact_info = result['data'][0]
                    if contact_info.get('status') == 'success':
                        contact_id = contact_info.get('details', {}).get('id')
                        self.logger.info(f"✅ Zoho contact created successfully: {contact_id}")
                        return True, contact_id, "Contact created successfully"
                    else:
                        error_msg = contact_info.get('message', 'Unknown error')
                        self.logger.error(f"Zoho contact creation failed: {error_msg}")
                        return False, None, error_msg
            
            elif response.status_code == 200:
                # Sometimes Zoho returns 200 for duplicates
                result = response.json()
                if result.get('data') and len(result['data']) > 0:
                    contact_info = result['data'][0]
                    if contact_info.get('code') == 'DUPLICATE_DATA':
                        self.logger.info("Contact already exists, attempting to find existing...")
                        return self._handle_existing_contact(extracted_data)
            
            else:
                error_msg = f"Zoho API error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Failed to create Zoho contact: {str(e)}"
            self.logger.error(error_msg)
            return False, None, error_msg
    
    def log_call_activity(self, contact_id, extracted_data):
        """Log the call as an activity in Zoho CRM"""
        try:
            # Get timestamp from call data or use current time
            call_timestamp = extracted_data.get('call_start_time')
            if call_timestamp:
                call_time = call_timestamp.strftime('%Y-%m-%dT%H:%M:%S%z')
            else:
                call_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')
            
            # Format transcript for Zoho
            transcript = extracted_data.get('transcript', '')
            reason = extracted_data.get('reason_for_call', 'General inquiry')
            
            if transcript:
                description = f"After-hours AI call transcript:\n\n{transcript}"
            else:
                description = f"After-hours AI call - {reason}"
            
            # Get call duration
            duration = extracted_data.get('call_duration', 180)  # Default 3 minutes
            if isinstance(duration, (int, float)):
                duration_minutes = max(1, int(duration / 60))  # Convert to minutes, minimum 1
            else:
                duration_minutes = 3
            
            activity_data = {
                "data": [{
                    "Subject": f"After-hours AI call - {reason[:50]}",
                    "Activity_Type": "Call",
                    "Description": description,
                    "Start_DateTime": call_time,
                    "Duration_Minutes": duration_minutes,
                    "Call_Type": "Inbound",
                    "Call_Result": "Completed",
                    "What_Id": contact_id,  # Associate with contact
                    "Call_Purpose": reason
                }]
            }
            
            response = self._make_request('POST', 'Activities', activity_data)
            
            if response.status_code == 201:
                result = response.json()
                if result.get('data') and len(result['data']) > 0:
                    activity_info = result['data'][0]
                    if activity_info.get('status') == 'success':
                        activity_id = activity_info.get('details', {}).get('id')
                        self.logger.info(f"✅ Call activity logged successfully: {activity_id}")
                        return True, activity_id
                        
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
                call_logged, activity_id = self.log_call_activity(contact_id, extracted_data)
                
                if call_logged:
                    self.logger.info(f"✅ Complete: Contact {contact_id} + Activity {activity_id}")
                    return True, contact_id, activity_id, "Contact and call logged successfully"
                else:
                    self.logger.warning(f"⚠️ Contact created but call logging failed")
                    return True, contact_id, None, "Contact created, call logging failed"
            
            return False, None, None, message
            
        except Exception as e:
            error_msg = f"Failed to create contact with call log: {str(e)}"
            self.logger.error(error_msg)
            return False, None, None, error_msg
    
    def _prepare_contact_data(self, extracted_data):
        """Convert extracted data to Zoho contact format"""
        contact = {}
        
        # Core contact fields (using Zoho field names)
        # Combine first_name and last_name into Contact_Name (Full Name field)
        if extracted_data.get('first_name') and extracted_data.get('last_name'):
            contact['Contact_Name'] = f"{extracted_data['first_name']} {extracted_data['last_name']}"
        elif extracted_data.get('name'):
            contact['Contact_Name'] = extracted_data['name']
        elif extracted_data.get('first_name'):
            contact['Contact_Name'] = extracted_data['first_name']
        elif extracted_data.get('last_name'):
            contact['Contact_Name'] = extracted_data['last_name']
        
        # Standard contact fields
        if extracted_data.get('email'):
            contact['Email'] = extracted_data['email']
        if extracted_data.get('phone'):
            contact['Phone'] = extracted_data['phone']
        
        # Description field for reason for call
        description_parts = []
        if extracted_data.get('reason_for_call'):
            description_parts.append(f"Reason for call: {extracted_data['reason_for_call']}")
        
        if extracted_data.get('company'):
            description_parts.append(f"Company: {extracted_data['company']}")
        
        # Add source info
        description_parts.append("Source: After-hours AI Call")
        
        if description_parts:
            contact['Description'] = "\n".join(description_parts)
        
        # Last Activity Time - use call start time or current time
        if extracted_data.get('call_start_time'):
            # Format for Zoho: YYYY-MM-DDTHH:MM:SS+00:00
            last_activity = extracted_data['call_start_time'].strftime('%Y-%m-%dT%H:%M:%S+00:00')
            contact['Last_Activity_Time'] = last_activity
        else:
            # Use current time if no call start time
            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')
            contact['Last_Activity_Time'] = current_time
        
        # Add lead source for tracking
        contact['Lead_Source'] = 'After-hours AI Call'
        
        self.logger.info(f"Prepared Zoho contact data: {contact}")
        return contact
    
    def _handle_existing_contact(self, extracted_data):
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
            # Use Zoho's search API
            search_params = {
                'criteria': f'(Email:equals:{email})',
                'per_page': 1
            }
            
            response = self._make_request('GET', 'Contacts/search', search_params)
            
            if response.status_code == 200:
                result = response.json()
                contacts = result.get('data', [])
                if contacts:
                    return contacts[0]
                    
        except Exception as e:
            self.logger.error(f"Error searching for contact: {e}")
            
        return None

def push_to_zoho(extracted_data):
    """Enhanced function to push contact + call activity to Zoho CRM"""
    try:
        zoho = ZohoIntegration()
        success, contact_id, activity_id, message = zoho.create_contact_with_call_log(extracted_data)
        
        if success:
            print(f"✅ Zoho CRM integration successful:")
            print(f"   📋 Contact ID: {contact_id}")
            if activity_id:
                print(f"   📞 Activity ID: {activity_id}")
                print(f"   📝 Call transcript logged")
            print(f"   🏷️ Tagged as after-hours AI call")
        else:
            print(f"❌ Zoho CRM integration failed: {message}")
            
        return success
        
    except Exception as e:
        print(f"❌ Zoho CRM integration error: {e}")
        return False