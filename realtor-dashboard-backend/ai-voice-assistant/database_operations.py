
# This module provides core database operations for managing leads, realtors, and call history.
#
# Key Responsibilities:
# - Lead identification and management (CRUD operations)
# - Phone number normalization and matching
# - Realtor lookup and assignment
# - Call history tracking and transcript storage  
# - Integration with CRM systems via person IDs
# - Multi-realtor isolation (leads don't cross between realtors)
#
# Core Functions by Workflow Stage:
# Pre-Call (Lead Identification):
# - get_realtor_by_phone(): Maps incoming numbers to realtor accounts
# - get_lead_info_by_phone(): Finds existing leads for inbound calls
# - normalize_phone_number(): Standardizes phone formats for reliable matching
#
# Lead Creation (if no identification is found pre-call):
# - create_new_lead(): Creates basic lead for unknown callers
# - create_new_lead_with_fub_id(): Creates leads from CRM webhook data
# - get_lead_by_fub_person_id(): Prevents CRM duplicate creation
#
# During Call:
# - get_lead_info(): Retrieves lead data by ID for conversation context
#
# Post-Call:
# - update_lead_info(): Main function for storing conversation results
#   * Updates lead profile (name, email, preferences, etc.)
#   * Creates call history record (transcript, duration, status)
#
# Database Design:
# - leads table: contact information and reason for calling (preferences)
# - call_histories table: Individual call records with transcripts
# - realtors table: Agent information and phone number mapping
#

import re
import datetime
from db_connection import get_db

def normalize_phone_number(phone_number):
    if not phone_number:
        return None
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone_number)
    
    # Ensure it's a North American number (10 digits)
    if len(digits_only) == 10:
        return digits_only
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        return digits_only[1:]
    else:
        return digits_only

def get_lead_info(lead_id):
    print(f"Attempting to get lead info for lead_id: {lead_id}")
    db_pool = get_db()
    try:
        with db_pool.get_cursor() as cursor:
            cursor.execute("""
                SELECT l.*
                FROM leads l
                WHERE l.id = %s
            """, (lead_id,))
            
            lead = cursor.fetchone()
            
            if lead:
                return {
                    'id': lead.get('id'),
                    'name': lead.get('name', 'the lead'),
                    'first_name': lead.get('first_name'),
                    'last_name': lead.get('last_name'),
                    'email': lead.get('email', 'no email on file'),
                    'phone': lead.get('phone', ''),
                    'source': lead.get('source'),
                    'reason_for_call': lead.get('reason_for_call', 'no'),
                    'realtor_id': lead.get('realtor_id'),
                    'bedrooms': lead.get('bedrooms'),
                    'bathrooms': lead.get('bathrooms'),
                    'property_type': lead.get('property_type'),
                    'parking': lead.get('parking'),
                    'budget': lead.get('budget'),
                    'pre_approval': lead.get('pre_approval'),
                    'timeline': lead.get('timeline'),
                    'realtor_status': lead.get('realtor_status'),
                    'followupboss_person_id': lead.get('followupboss_person_id'),
                    'agent_name': lead.get('agent_name'),
                    'property_address': lead.get('property_address'),
                    'is_inbound': False
                }
            else:
                print(f"No lead found with ID: {lead_id}")
                return None
    except Exception as e:
        print(f"Error fetching lead info: {e}")
        return None
    
def get_lead_info_by_phone(phone_number, realtor_id):
    # Get lead information by phone number to check for existing leads within specific realtor's client list. happens at the very start of inbound call to use lead info on the call.
    db_pool = get_db()
    try:
        normalized_number = normalize_phone_number(phone_number)
        print(f"Normalized incoming phone number: {normalized_number}")
        
        with db_pool.get_cursor() as cursor:
            # Try exact match first with realtor_id filter
            cursor.execute("""
                SELECT * FROM leads WHERE phone = %s AND realtor_id = %s
            """, (normalized_number, realtor_id))
            lead = cursor.fetchone()
            
            if not lead:
                print("No exact match found, trying alternative formats...")
                # Try alternative formats but still filter by realtor_id
                possible_formats = [
                    normalized_number,
                    f"+1{normalized_number}",
                    f"+1 {normalized_number}",
                    f"{normalized_number[:3]}-{normalized_number[3:6]}-{normalized_number[6:]}"
                ]
                cursor.execute("""
                    SELECT * FROM leads 
                    WHERE phone = ANY(%s) AND realtor_id = %s
                """, (possible_formats, realtor_id))
                lead = cursor.fetchone()
            
            if lead:
                print(f"Lead found for realtor {realtor_id}: {lead}")
                return {
                    'id': lead.get('id'),
                    'name': lead.get('name', 'the lead'),
                    'first_name': lead.get('first_name'),
                    'last_name': lead.get('last_name'),
                    'email': lead.get('email', 'no email on file'),
                    'phone': lead.get('phone', ''),
                    'source': lead.get('source'),
                    'reason_for_call': lead.get('reason_for_call', 'no'),
                    'realtor_id': lead.get('realtor_id'),
                    'bedrooms': lead.get('bedrooms'),
                    'bathrooms': lead.get('bathrooms'),
                    'property_type': lead.get('property_type'),
                    'parking': lead.get('parking'),
                    'budget': lead.get('budget'),
                    'pre_approval': lead.get('pre_approval'),
                    'timeline': lead.get('timeline'),
                    'realtor_status': lead.get('realtor_status'),
                    'followupboss_person_id': lead.get('followupboss_person_id'),
                    'agent_name': lead.get('agent_name'),
                    'property_address': lead.get('property_address'),
                    'is_inbound': False
                }
            else:
                print(f"No lead found for realtor {realtor_id} with this phone number")
                return None
    except Exception as e:
        print(f"Error fetching lead info by phone: {e}")
        return None

def create_new_lead(phone_number, realtor_id):
    # create basic lead structure for unknown caller.
    db_pool = get_db()
    try:
        normalized_number = normalize_phone_number(phone_number)
        
        with db_pool.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO leads (
                    phone, name, first_name, last_name, email, realtor_id,
                    source, reason_for_call, created_at, updated_at
                ) VALUES ( %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                normalized_number, 
                "there", 
                None,
                None,
                "unknown@example.com", 
                realtor_id,
                None,
                "no"
            ))
            
            new_lead = cursor.fetchone()
            lead_id = new_lead['id']
            
            # Create initial call history entry
            cursor.execute("""
                INSERT INTO call_histories (
                    lead_id, call_status, transcript, 
                    realtor_id, created_at
                ) VALUES (%s, 'pending', '', %s, NOW())
            """, (lead_id, realtor_id))
            
            print(f"New lead created with ID: {lead_id}")
            return str(lead_id)
    except Exception as e:
        print(f"Error creating new lead: {e}")
        return None

def create_new_lead_with_fub_id(phone_number, realtor_id, followupboss_person_id, name=None, email=None, agent_name=None, property_address=None, source=None):
    # Create a new lead with FollowUpBoss person ID to prevent duplicates
    db_pool = get_db()
    try:
        normalized_number = normalize_phone_number(phone_number)
        
        with db_pool.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO leads (
                    phone, name, first_name, last_name, email, realtor_id,
                    source, reason_for_call, followupboss_person_id, agent_name, property_address, created_at, updated_at
                ) VALUES ( %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                normalized_number, 
                name or "Unknown", 
                None,  # first_name - can be parsed from name if needed
                None,  # last_name - can be parsed from name if needed
                email or "unknown@example.com", 
                realtor_id,
                source,
                "webhook_lead",  # reason_for_call
                followupboss_person_id,
                agent_name,
                property_address
            ))
            
            new_lead = cursor.fetchone()
            lead_id = new_lead['id']
            
            # Create initial call history entry
            cursor.execute("""
                INSERT INTO call_histories (
                    lead_id, call_status, transcript, 
                    realtor_id, created_at
                ) VALUES (%s, 'pending', '', %s, NOW())
            """, (lead_id, realtor_id))
            
            print(f"New lead created with ID: {lead_id}, FollowUpBoss Person ID: {followupboss_person_id}")
            return str(lead_id)
    except Exception as e:
        print(f"Error creating new lead with FollowUpBoss ID: {e}")
        return None

def get_lead_by_fub_person_id(followupboss_person_id):
    # Get lead by FollowUpBoss person ID
    db_pool = get_db()
    try:
        with db_pool.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, name, phone, email, followupboss_person_id, realtor_id, created_at
                FROM leads
                WHERE followupboss_person_id = %s
                LIMIT 1
            """, (followupboss_person_id,))
            
            lead = cursor.fetchone()
            if lead:
                # Handle both dict (RealDictCursor) and tuple return types
                if isinstance(lead, dict):
                    return {
                        'id': lead['id'],
                        'name': lead['name'],
                        'phone': lead['phone'],
                        'email': lead['email'],
                        'followupboss_person_id': lead['followupboss_person_id'],
                        'realtor_id': lead['realtor_id'],
                        'created_at': lead['created_at']
                    }
                else:
                    # Handle tuple return (id, name, phone, email, followupboss_person_id, realtor_id, created_at)
                    return {
                        'id': lead[0],
                        'name': lead[1],
                        'phone': lead[2],
                        'email': lead[3],
                        'followupboss_person_id': lead[4],
                        'realtor_id': lead[5],
                        'created_at': lead[6]
                    }
            return None
    except Exception as e:
        print(f"Error getting lead by FollowUpBoss person ID: {e}")
        return None

def get_realtor_by_phone(phone_number):
    # Identify which realtor owns the incoming number to use realtor info on the call.
    db_pool = get_db()
    try:
        normalized_number = normalize_phone_number(phone_number)
        
        with db_pool.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name, last_name, email, phone
                FROM realtors 
                WHERE phone = %s
                LIMIT 1
            """, (normalized_number,))
            
            realtor = cursor.fetchone()
            if realtor:
                return {
                    'id': realtor.get('id'),
                    'first_name': realtor.get('first_name'),
                    'last_name': realtor.get('last_name'),
                    'email': realtor.get('email'),
                    'phone': realtor.get('phone')
                }
            return None
    except Exception as e:
        print(f"Error fetching realtor by phone: {e}")
        return None

def update_lead_info(lead_id, extracted_data):
    # main post-call function: update lead record with new conversation data (name, preferneces, email etc.)
    print(f"Starting update for lead_id: {lead_id}")
    print(f"Full extracted data: {extracted_data}")

    if lead_id is None:
        print("Error: Cannot update lead info. No lead ID provided.")
        return 0

    # Separate lead-specific and call-specific data
    lead_fields = {
        'name': extracted_data.get('name'),
        'first_name': extracted_data.get('first_name'),
        'last_name': extracted_data.get('last_name'),
        'email': extracted_data.get('email'),
        'phone': extracted_data.get('phone'),
        'status': extracted_data.get('status'),
        'reason_for_call': extracted_data.get('reason_for_call'),
        'bedrooms': extracted_data.get('bedrooms'),
        'bathrooms': extracted_data.get('bathrooms'),
        'property_type': extracted_data.get('property_type'),
        'parking': extracted_data.get('parking'),
        'budget': extracted_data.get('budget'),
        'pre_approval': extracted_data.get('pre_approval'),
        'timeline': extracted_data.get('timeline'),
        'realtor_status': extracted_data.get('realtor_status'),
        'agent_name': extracted_data.get('agent_name'),
        'property_address': extracted_data.get('property_address'),
        'last_contact_date': datetime.datetime.now() # Update last contact
    }

    print(f"Lead fields before filtering: {lead_fields}")

    call_fields = {
        'call_status': extracted_data.get('call_status', 'completed'),
        'call_sid': extracted_data.get('call_sid', ''),
        'transcript': extracted_data.get('transcript', ''),
        'realtor_id': extracted_data.get('realtor_id'),
        'reason_for_call': extracted_data.get('reason_for_call'),
        'call_start_time': extracted_data.get('call_start_time'),
        'call_end_time': extracted_data.get('call_end_time'),
        'call_duration': extracted_data.get('call_duration')
    }

    db_pool = get_db()
    try:
        with db_pool.get_cursor() as cursor:
            # Filter out None values from lead_fields
            lead_updates = {k: v for k, v in lead_fields.items() if v is not None}
            print(f"Lead updates after filtering: {lead_updates}")
            
            if lead_updates:
                # Update leads table with lead-specific data
                set_clause = ", ".join([f"{key} = %s" for key in lead_updates.keys()])
                set_clause += ", updated_at = NOW()"
                values = list(lead_updates.values()) + [lead_id]
                
                query = f"""
                    UPDATE leads
                    SET {set_clause}
                    WHERE id = %s
                """
                cursor.execute(query, values)
            
            # Create call history entry with call-specific info
            cursor.execute("""
                INSERT INTO call_histories (
                    lead_id,
                    call_status,
                    call_sid,
                    transcript,
                    realtor_id,
                    reason_for_call,
                    call_start_time,
                    call_end_time,
                    call_duration,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                lead_id,
                call_fields['call_status'],
                call_fields['call_sid'],
                call_fields['transcript'],
                call_fields['realtor_id'],
                call_fields.get('reason_for_call', 'no'),
                call_fields.get('call_start_time'),
                call_fields.get('call_end_time'),
                call_fields.get('call_duration'),
            ))
            
            return cursor.rowcount
    except Exception as e:
        print(f"Error updating lead info: {e}")
        return 0

