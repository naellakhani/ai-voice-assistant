"""
FollowUpBoss CRM Integration Module

This module contains all FollowUpBoss-specific functionality:
- Core integration (API calls, contact management)
- Webhook handling (peopleCreated, peopleUpdated events)
- Batch outbound calling
- Scheduling and automation
- Testing utilities
"""

from .integration import FollowUpBossIntegration, push_to_followupboss

__all__ = [
    'FollowUpBossIntegration',
    'push_to_followupboss'
]