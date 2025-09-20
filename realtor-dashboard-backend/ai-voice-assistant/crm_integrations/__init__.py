"""
CRM Integrations Initialization

This module initializes CRM integrations based on the PRIMARY_CRM environment variable.
"""

import os
from crm_integrations.base_crm import crm_manager, register_crm
from crm_integrations.followupboss import FollowUpBossIntegration


def initialize_crm_integrations():
    """Initialize and register CRM integration based on PRIMARY_CRM environment variable"""
    try:
        primary_crm = os.getenv('PRIMARY_CRM', '').lower()
        
        if not primary_crm:
            print("No PRIMARY_CRM environment variable set. CRM integration disabled.")
            return False
        
        crm_instance = None
        
        if primary_crm == 'followupboss':
            crm_instance = FollowUpBossIntegration()
        elif primary_crm == 'hubspot':
            # TODO: Import and initialize HubSpot when implemented
            print(f"HubSpot CRM not yet implemented")
            return False
        elif primary_crm == 'zoho':
            # TODO: Import and initialize Zoho when implemented  
            print(f"Zoho CRM not yet implemented")
            return False
        else:
            print(f"Unsupported PRIMARY_CRM: {primary_crm}")
            print("Supported CRMs: followupboss, hubspot, zoho")
            return False
        
        if crm_instance:
            register_crm(crm_instance, is_primary=True)
            print("CRM integrations initialized successfully")
            print(f"Primary CRM: {crm_instance.get_crm_name()}")
            return True
        
        return False
        
    except Exception as e:
        print(f"Failed to initialize CRM integrations: {e}")
        return False


def get_primary_crm():
    """Get the primary CRM integration"""
    return crm_manager.get_crm()


def get_crm_by_name(crm_name: str):
    """Get a specific CRM integration by name"""
    return crm_manager.get_crm(crm_name)


# Initialize CRMs when module is imported
initialize_crm_integrations()