import os
import requests
import time
from datetime import datetime, timedelta
from call_logger import get_call_logger
from call_routes import handle_make_call
from database_operations import get_db
from db_connection import initialize_db

class HubSpotOutboundManager:
    def __init__(self):
        self.api_key = os.getenv('HUBSPOT_API_KEY')
        self.base_url = 'https://api.hubapi.com'
        self.logger = get_call_logger()
        self.polling_interval = 45  # Check every 45 seconds
        
        # Initialize database connection if not already done
        self._ensure_db_connection()
        
    def _ensure_db_connection(self):
        """Ensure database connection is initialized"""
        try:
            self.logger.info("Initializing database connection...")
            # Load environment variables
            from dotenv import load_dotenv
            load_dotenv(dotenv_path='.env.docker')
            
            # Get database URL from environment
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                raise ValueError("DATABASE_URL not found in environment variables")
            
            initialize_db(connection_string=db_url)
            self.logger.info("✅ Database connection initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database connection: {e}")
            raise
        
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def verify_call_action_property(self):
        """Verify that the 'Call Action' property exists in HubSpot"""
        try:
            url = f'{self.base_url}/crm/v3/properties/contacts/call_action'
            response = requests.get(url, headers=self._get_headers())
            
            if response.status_code == 200:
                self.logger.info("✅ 'Call Action' property found in HubSpot")
                return True
            else:
                self.logger.warning("⚠️ 'Call Action' property not found - please create it manually")
                return False
                
        except Exception as e:
            self.logger.error(f"Error verifying Call Action property: {e}")
            return False
    
    def get_contacts_to_call(self):
        """Get contacts with Call Action = 'call'"""
        try:
            search_data = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "call_action",
                                "operator": "EQ",
                                "value": "call"
                            }
                        ]
                    }
                ],
                "properties": [
                    "firstname", "lastname", "email", "phone", 
                    "call_action", "company", "hs_object_id"
                ],
                "limit": 50
            }
            
            url = f'{self.base_url}/crm/v3/objects/contacts/search'
            response = requests.post(url, headers=self._get_headers(), json=search_data)
            
            if response.status_code == 200:
                results = response.json().get('results', [])
                self.logger.info(f"Found {len(results)} contacts marked for calling")
                return results
            else:
                self.logger.error(f"Failed to search contacts: {response.text}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error searching for contacts to call: {e}")
            return []
    
    def update_contact_call_action(self, contact_id, new_status):
        """Update a contact's Call Action status"""
        try:
            # Map our internal status to HubSpot values (only use allowed values)
            status_mapping = {
                "completed": "completed",
                "error": "error", 
                "failed": "failed",
                "calling": "call"  # Keep as "call" while processing to avoid invalid option error
            }
            
            hubspot_status = status_mapping.get(new_status, new_status)
            
            # Only update the call_action field (remove last_call_attempt since it doesn't exist)
            update_data = {
                "properties": {
                    "call_action": hubspot_status
                }
            }
            
            url = f'{self.base_url}/crm/v3/objects/contacts/{contact_id}'
            response = requests.patch(url, headers=self._get_headers(), json=update_data)
            
            if response.status_code == 200:
                self.logger.info(f"✅ Updated contact {contact_id} Call Action to {hubspot_status}")
                return True
            else:
                self.logger.error(f"Failed to update contact Call Action: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error updating contact Call Action: {e}")
            return False
    
    def create_or_update_lead_in_db(self, hubspot_contact):
        """Create or update lead in local database from HubSpot contact"""
        try:
            properties = hubspot_contact.get('properties', {})
            
            # Extract contact information
            first_name = properties.get('firstname', '')
            last_name = properties.get('lastname', '')
            email = properties.get('email', '')
            phone = properties.get('phone', '')
            company = properties.get('company', '')
            hubspot_id = hubspot_contact.get('id')
            
            # Clean phone number (remove formatting)
            if phone:
                phone = ''.join(filter(str.isdigit, phone))
                if phone.startswith('1') and len(phone) == 11:
                    phone = phone[1:]  # Remove country code
            
            if not phone:
                self.logger.warning(f"No valid phone number for contact {hubspot_id}")
                return None
            
            # Check if lead already exists
            db = get_db()
            with db.get_cursor() as cursor:
                # Try to find existing lead by HubSpot ID or phone
                cursor.execute("""
                    SELECT id FROM leads 
                    WHERE hubspot_id = %s OR phone = %s
                    LIMIT 1
                """, (hubspot_id, phone))
                
                existing_lead = cursor.fetchone()
                
                if existing_lead:
                    # Update existing lead
                    lead_id = existing_lead['id']
                    cursor.execute("""
                        UPDATE leads 
                        SET first_name = %s, last_name = %s, name = %s,
                            email = %s, phone = %s, company = %s,
                            hubspot_id = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (
                        first_name, last_name, f"{first_name} {last_name}".strip(),
                        email, phone, company, hubspot_id, lead_id
                    ))
                    self.logger.info(f"Updated existing lead {lead_id}")
                else:
                    # Create new lead
                    cursor.execute("""
                        INSERT INTO leads (
                            first_name, last_name, name, email, phone, 
                            company, hubspot_id, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING id
                    """, (
                        first_name, last_name, f"{first_name} {last_name}".strip(),
                        email, phone, company, hubspot_id
                    ))
                    
                    result = cursor.fetchone()
                    lead_id = result['id']
                    self.logger.info(f"Created new lead {lead_id}")
                
                return str(lead_id)
                
        except Exception as e:
            self.logger.error(f"Error creating/updating lead in database: {e}")
            return None
    
    def process_outbound_calls(self):
        """Main function to process outbound calls"""
        try:
            # Get contacts marked for calling
            contacts_to_call = self.get_contacts_to_call()
            
            if not contacts_to_call:
                return
            
            for contact in contacts_to_call:
                contact_id = contact.get('id')
                properties = contact.get('properties', {})
                phone = properties.get('phone', '')
                name = f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip()
                
                self.logger.info(f"Processing outbound call for {name} ({phone})")
                
                # Don't update status to "calling" since it's not allowed - just proceed
                # self.update_contact_call_action(contact_id, "calling")
                
                # Create/update lead in local database
                lead_id = self.create_or_update_lead_in_db(contact)
                
                if not lead_id:
                    self.logger.error(f"Failed to create lead for contact {contact_id}")
                    self.update_contact_call_action(contact_id, "error")
                    continue
                
                # Clean phone number for calling
                clean_phone = ''.join(filter(str.isdigit, phone))
                if clean_phone.startswith('1') and len(clean_phone) == 11:
                    clean_phone = clean_phone[1:]
                
                if len(clean_phone) != 10:
                    self.logger.error(f"Invalid phone number format: {phone}")
                    self.update_contact_call_action(contact_id, "error")
                    continue
                
                # Format phone number for calling
                formatted_phone = f"+1{clean_phone}"
                
                # Initiate call using existing call handling system
                call_data = {
                    'leadId': lead_id,
                    'phoneNumber': formatted_phone
                }
                
                result = handle_make_call(call_data, is_http_request=False)
                
                if result.get('status') == 'success':
                    self.logger.info(f"✅ Call initiated for {name}")
                    
                    self.logger.error(f"❌ Failed to initiate call for {name}: {result.get('message')}")
                    self.update_contact_call_action(contact_id, "error")
                
                # Small delay between calls to avoid overwhelming the system
                time.sleep(2)
                
        except Exception as e:
            self.logger.error(f"Error processing outbound calls: {e}")
    
    def start_polling(self):
        """Start continuous polling for contacts to call"""
        self.logger.info("🔄 Starting HubSpot outbound call polling...")
        
        # Verify the Call Action property exists
        if not self.verify_call_action_property():
            self.logger.error("❌ Call Action property not found. Please create it manually in HubSpot.")
            return
        
        while True:
            try:
                self.process_outbound_calls()
                time.sleep(self.polling_interval)
            except KeyboardInterrupt:
                self.logger.info("Stopping HubSpot polling...")
                break
            except Exception as e:
                self.logger.error(f"Error in polling loop: {e}")
                time.sleep(self.polling_interval)

# Usage functions
def setup_hubspot_outbound():
    """Setup function to create the property and start polling"""
    manager = HubSpotOutboundManager()
    return manager

def start_hubspot_polling():
    """Start the polling service (can be run as a background service)"""
    manager = setup_hubspot_outbound()
    manager.start_polling()

# Test function
def test_hubspot_outbound():
    """Test function to check the integration"""
    # Load environment variables first
    from dotenv import load_dotenv
    load_dotenv(dotenv_path='.env.docker')
    
    manager = HubSpotOutboundManager()
    
    print("🧪 Testing HubSpot Outbound Integration...")
    
    # Test 1: Verify Call Action property
    print("1. Verifying Call Action property...")
    success = manager.verify_call_action_property()
    print(f"   ✅ Property verification: {'Success' if success else 'Failed'}")
    
    # Test 2: Search for contacts
    print("2. Searching for contacts to call...")
    contacts = manager.get_contacts_to_call()
    print(f"   ℹ️ Found {len(contacts)} contacts marked for calling")
    
    if contacts:
        # Test 3: Show contact details
        for i, contact in enumerate(contacts[:3]):  # Show first 3
            props = contact.get('properties', {})
            name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            phone = props.get('phone', 'No phone')
            call_action = props.get('call_action', 'No status')
            print(f"   📞 Contact {i+1}: {name} - {phone} - Status: {call_action}")
        print("3. Testing actual call processing...")
        manager.process_outbound_calls()
    
    print("🧪 Test completed!")

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv(dotenv_path='.env.docker')
    
    # For testing
    test_hubspot_outbound()