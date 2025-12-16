"""
Salesforce/Jungo → Pipedrive Sync Module

This module handles syncing loan and contact data from Salesforce to Pipedrive.
"""

from .salesforce_client import SalesforceClient
from .sync_person import sync_person_from_contact, sync_coborrower_from_loan
from .sync_deal import sync_deal_from_loan
from .polling_sync import run_polling_sync, run_initial_sync
from .cdc_listener import handle_cdc_event

__all__ = [
    'SalesforceClient',
    'sync_person_from_contact',
    'sync_coborrower_from_loan',
    'sync_deal_from_loan',
    'run_polling_sync',
    'run_initial_sync',
    'handle_cdc_event',
]

