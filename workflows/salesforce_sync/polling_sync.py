"""
Polling-based Sync

Runs periodic syncs by querying Salesforce for modified loans.
"""

import logging
from datetime import datetime, timedelta
from typing import List
from .salesforce_client import SalesforceClient
from .sync_deal import sync_deal_from_loan

logger = logging.getLogger(__name__)


class PollingSync:
    """
    Handles polling-based synchronization from Salesforce to Pipedrive.
    """
    
    def __init__(self):
        self.sf_client = SalesforceClient()
        self.last_sync_time = None
    
    def run_sync(self, hours_back: int = 24) -> dict:
        """
        Run a sync for loans modified in the last N hours.
        
        Args:
            hours_back: How many hours back to look for modified loans
            
        Returns:
            Dictionary with sync statistics
        """
        # Calculate cutoff time
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        logger.info(f"Starting polling sync (modified since {cutoff_iso})...")
        
        # Query Salesforce for modified loans
        try:
            loans = self.sf_client.get_loans_by_loan_officer(modified_since=cutoff_iso)
            logger.info(f"Found {len(loans)} loans to sync")
        except Exception as e:
            logger.error(f"Failed to query Salesforce: {e}")
            return {
                "success": False,
                "error": str(e),
                "synced": 0,
                "failed": 0
            }
        
        # Sync each loan
        synced = 0
        failed = 0
        errors = []
        
        for loan in loans:
            try:
                deal_id = sync_deal_from_loan(loan)
                if deal_id:
                    synced += 1
                    logger.info(f"✓ Synced loan {loan.get('Id')} → Deal {deal_id}")
                else:
                    failed += 1
                    errors.append(f"Loan {loan.get('Id')}: Sync returned None")
            except Exception as e:
                failed += 1
                error_msg = f"Loan {loan.get('Id')}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Update last sync time
        self.last_sync_time = datetime.utcnow()
        
        result = {
            "success": True,
            "synced": synced,
            "failed": failed,
            "total": len(loans),
            "last_sync": self.last_sync_time.isoformat()
        }
        
        if errors:
            result["errors"] = errors[:10]  # Limit to first 10 errors
        
        logger.info(f"Sync complete: {synced} synced, {failed} failed")
        return result


def run_polling_sync(hours_back: int = 24) -> dict:
    """
    Convenience function to run a polling sync.
    
    Args:
        hours_back: How many hours back to look for modified loans
        
    Returns:
        Dictionary with sync statistics
    """
    sync = PollingSync()
    return sync.run_sync(hours_back=hours_back)


def run_initial_sync(limit: int = 1000) -> dict:
    """
    Run an initial full sync (no time filter).
    
    This is useful for the first sync to bring all existing loans into Pipedrive.
    
    Args:
        limit: Maximum number of loans to sync
        
    Returns:
        Dictionary with sync statistics
    """
    logger.info(f"Starting initial sync (limit: {limit})...")
    
    from .salesforce_client import SalesforceClient
    from .sync_deal import sync_deal_from_loan
    
    sf_client = SalesforceClient()
    
    # Query all loans (no time filter)
    try:
        loans = sf_client.get_loans_by_loan_officer(limit=limit)
        logger.info(f"Found {len(loans)} loans to sync")
    except Exception as e:
        logger.error(f"Failed to query Salesforce: {e}")
        return {
            "success": False,
            "error": str(e),
            "synced": 0,
            "failed": 0
        }
    
    # Sync each loan
    synced = 0
    failed = 0
    errors = []
    
    for loan in loans:
        try:
            deal_id = sync_deal_from_loan(loan)
            if deal_id:
                synced += 1
                if synced % 10 == 0:
                    logger.info(f"Progress: {synced}/{len(loans)} synced...")
            else:
                failed += 1
                errors.append(f"Loan {loan.get('Id')}: Sync returned None")
        except Exception as e:
            failed += 1
            error_msg = f"Loan {loan.get('Id')}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
    
    result = {
        "success": True,
        "synced": synced,
        "failed": failed,
        "total": len(loans),
    }
    
    if errors:
        result["errors"] = errors[:10]
    
    logger.info(f"Initial sync complete: {synced} synced, {failed} failed")
    return result

