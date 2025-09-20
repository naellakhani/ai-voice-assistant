"""
Base CRM Integration Interface

This module defines the base interface that all CRM integrations should implement.
It provides a consistent API for the voice assistant to interact with different CRMs.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime


class BaseCRMIntegration(ABC):
    """Base class for all CRM integrations"""
    
    def __init__(self):
        self.logger = None
        self.api_key = None
        self.base_url = None
    
    @abstractmethod
    def get_crm_name(self) -> str:
        """Return the name of this CRM (e.g., 'FollowUpBoss', 'HubSpot', 'Salesforce')"""
        pass
    
    # Contact/Person Management
    @abstractmethod
    def search_person_by_phone(self, phone_number: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Search for existing person by phone number.
        
        Args:
            phone_number: Phone number to search for
            
        Returns:
            Tuple of (exists, person_id, person_data)
        """
        pass
    
    @abstractmethod
    def create_person(self, extracted_data: Dict[str, Any]) -> Tuple[bool, Optional[str], str]:
        """
        Create a new person/lead in the CRM.
        
        Args:
            extracted_data: Call data with person details
            
        Returns:
            Tuple of (success, person_id, message)
        """
        pass
    
    @abstractmethod
    def update_existing_person(self, person_id: str, extracted_data: Dict[str, Any]) -> bool:
        """
        Update an existing person in the CRM.
        
        Args:
            person_id: CRM person ID
            extracted_data: Updated call data
            
        Returns:
            bool indicating success
        """
        pass
    
    # Call Activity & Notes
    @abstractmethod
    def create_note_with_transcript(self, person_id: str, extracted_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Create a note/activity with call transcript in the CRM timeline.
        
        Args:
            person_id: CRM person ID
            extracted_data: Call data including transcript
            
        Returns:
            Tuple of (success, note_id)
        """
        pass
    
    # Main Integration Method
    @abstractmethod
    def create_person_with_call_log(self, extracted_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str], Optional[str], str]:
        """
        Main method to create/update person and log call activity.
        This is the primary entry point used by call_status.py and data_extraction.py.
        
        Args:
            extracted_data: Complete call data
            
        Returns:
            Tuple of (success, person_id, note_id, task_id, status_message)
        """
        pass
    
    # Webhook Support (for CRMs that support webhooks like FollowUpBoss)
    def supports_webhooks(self) -> bool:
        """Return True if this CRM supports webhooks for real-time lead updates"""
        return False
    
    def register_webhooks(self, webhook_url: str) -> bool:
        """
        Register webhooks with the CRM for peopleCreated/peopleUpdated events.
        
        Args:
            webhook_url: Public URL for webhook endpoint
            
        Returns:
            bool indicating success
        """
        return False
    
    def handle_webhook_data(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook data and return standardized format.
        
        Args:
            webhook_data: Raw webhook payload from CRM
            
        Returns:
            Dict with standardized webhook data format:
            {
                'event_type': 'person_created' | 'person_updated',
                'person_id': str,
                'person_data': dict,
                'should_call': bool,
                'lead_info': dict
            }
        """
        return {}
    
    def fetch_person_from_api(self, person_id: str) -> Optional[Dict]:
        """
        Fetch person data from CRM API using person ID.
        Used by webhook handlers to get full person data.
        
        Args:
            person_id: CRM person ID
            
        Returns:
            Person data dict or None if not found
        """
        return None
    
    # Outbound Calling Support (for CRMs that manage call queues)
    def supports_outbound_calling(self) -> bool:
        """Return True if this CRM can provide contacts for outbound calling"""
        return False
    
    def fetch_contacts_to_call(self, limit: int = 50) -> List[Dict]:
        """
        Fetch contacts that need outbound calls.
        
        Args:
            limit: Maximum number of contacts to return
            
        Returns:
            List of contact dicts with phone, name, etc.
        """
        return []
    
    def mark_contact_as_called(self, person_id: str) -> bool:
        """
        Mark contact in CRM as having been called.
        
        Args:
            person_id: CRM person ID
            
        Returns:
            bool indicating success
        """
        return False
    
    # Utility Methods (can be overridden for CRM-specific formatting)
    def format_phone_number(self, phone: str) -> str:
        """Standardize phone number format for this CRM"""
        return phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    def prepare_extracted_data(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare extracted data for this specific CRM's format.
        Override for CRM-specific field mapping.
        
        Args:
            extracted_data: Standard call data format
            
        Returns:
            CRM-specific formatted data
        """
        return extracted_data.copy()


class CRMManager:
    """Manages multiple CRM integrations and provides unified interface"""
    
    def __init__(self):
        self.crm_integrations = {}
        self.primary_crm = None
    
    def register_crm(self, crm_integration: BaseCRMIntegration, is_primary: bool = False):
        """Register a CRM integration"""
        crm_name = crm_integration.get_crm_name()
        self.crm_integrations[crm_name] = crm_integration
        
        if is_primary or self.primary_crm is None:
            self.primary_crm = crm_name
        
        print(f"✅ Registered {crm_name} CRM {'(PRIMARY)' if is_primary else ''}")
    
    def get_crm(self, crm_name: str = None) -> Optional[BaseCRMIntegration]:
        """Get a specific CRM integration or the primary one"""
        if crm_name:
            return self.crm_integrations.get(crm_name)
        
        if self.primary_crm:
            return self.crm_integrations.get(self.primary_crm)
        
        return None
    
    def get_primary_crm_name(self) -> Optional[str]:
        """Get the name of the primary CRM"""
        return self.primary_crm
    
    def get_all_crms(self) -> List[BaseCRMIntegration]:
        """Get all registered CRM integrations"""
        return list(self.crm_integrations.values())
    
    def get_webhook_enabled_crms(self) -> List[BaseCRMIntegration]:
        """Get CRMs that support webhooks"""
        return [crm for crm in self.crm_integrations.values() if crm.supports_webhooks()]
    
    def get_outbound_calling_crms(self) -> List[BaseCRMIntegration]:
        """Get CRMs that support outbound calling"""
        return [crm for crm in self.crm_integrations.values() if crm.supports_outbound_calling()]
    
    def push_to_all_crms(self, extracted_data: Dict[str, Any]) -> Dict[str, bool]:
        """Push data to all registered CRMs"""
        results = {}
        
        for crm_name, crm_integration in self.crm_integrations.items():
            try:
                success, _, _, _, message = crm_integration.create_person_with_call_log(extracted_data)
                results[crm_name] = success
                print(f"{'✅' if success else '❌'} {crm_name}: {message}")
            except Exception as e:
                print(f"❌ Error pushing to {crm_name}: {e}")
                results[crm_name] = False
        
        return results
    
    def push_to_primary_crm(self, extracted_data: Dict[str, Any]) -> bool:
        """Push data to the primary CRM only"""
        primary_crm = self.get_crm()
        if primary_crm:
            try:
                success, _, _, _, message = primary_crm.create_person_with_call_log(extracted_data)
                print(f"{'✅' if success else '❌'} {self.primary_crm}: {message}")
                return success
            except Exception as e:
                print(f"❌ Error pushing to primary CRM ({self.primary_crm}): {e}")
                return False
        
        print("❌ No primary CRM configured")
        return False


# Global CRM manager instance
crm_manager = CRMManager()


def push_to_crm(extracted_data: Dict[str, Any], crm_name: str = None) -> bool:
    """
    Convenience function to push data to CRM(s).
    This is the main function that call_status.py and data_extraction.py should use.
    
    Args:
        extracted_data: Call data to push to CRM
        crm_name: Specific CRM name, or None for primary CRM
    
    Returns:
        bool indicating success
    """
    if crm_name:
        crm = crm_manager.get_crm(crm_name)
        if crm:
            success, _, _, _, message = crm.create_person_with_call_log(extracted_data)
            return success
        return False
    else:
        return crm_manager.push_to_primary_crm(extracted_data)


def get_crm(crm_name: str = None) -> Optional[BaseCRMIntegration]:
    """
    Get a CRM integration instance.
    
    Args:
        crm_name: Specific CRM name, or None for primary CRM
        
    Returns:
        CRM integration instance or None
    """
    return crm_manager.get_crm(crm_name)


def register_crm(crm_integration: BaseCRMIntegration, is_primary: bool = False):
    """
    Register a CRM integration with the global manager.
    
    Args:
        crm_integration: CRM integration instance
        is_primary: Whether this should be the primary CRM
    """
    crm_manager.register_crm(crm_integration, is_primary)