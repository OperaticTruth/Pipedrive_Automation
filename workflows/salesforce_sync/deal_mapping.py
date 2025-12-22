"""
Deal Mapping Storage

Stores mapping of Salesforce Loan ID → Pipedrive Deal ID to track deals
even when they're archived (since archived deals can't be queried via API).
"""

import json
import os
import logging
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# Store mapping file in the project directory
# Note: On Render, the filesystem persists between deployments (not ephemeral)
# The file will survive restarts and redeployments
MAPPING_FILE = Path(__file__).parent.parent.parent / "deal_mappings.json"


def load_mappings() -> Dict[str, int]:
    """
    Load deal mappings from file.
    
    Returns:
        Dictionary mapping Salesforce Loan ID -> Deal ID
    """
    logger.info(f"Loading deal mappings from: {MAPPING_FILE}")
    logger.info(f"Mapping file exists: {MAPPING_FILE.exists()}")
    
    if not MAPPING_FILE.exists():
        logger.info("Mapping file does not exist - returning empty mapping")
        return {}
    
    try:
        with open(MAPPING_FILE, 'r') as f:
            data = json.load(f)
            mappings = {str(k): int(v) for k, v in data.items()}
            logger.info(f"Loaded {len(mappings)} deal mappings from file")
            return mappings
    except Exception as e:
        logger.warning(f"Error loading deal mappings: {e}", exc_info=True)
        return {}


def save_mappings(mappings: Dict[str, int]) -> None:
    """
    Save deal mappings to file.
    
    Args:
        mappings: Dictionary mapping Salesforce Loan ID -> Deal ID
    """
    try:
        # Ensure directory exists
        MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(MAPPING_FILE, 'w') as f:
            json.dump(mappings, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving deal mappings: {e}")


def get_deal_id_for_loan(salesforce_loan_id: str) -> Optional[int]:
    """
    Get Pipedrive Deal ID for a Salesforce Loan ID from stored mapping.
    
    Args:
        salesforce_loan_id: Salesforce Loan ID
        
    Returns:
        Pipedrive Deal ID if found in mapping, None otherwise
    """
    mappings = load_mappings()
    deal_id = mappings.get(str(salesforce_loan_id))
    if deal_id:
        logger.info(f"Found mapping: Loan {salesforce_loan_id} → Deal {deal_id}")
    else:
        logger.info(f"No mapping found for Loan {salesforce_loan_id} (total mappings: {len(mappings)})")
    return deal_id


def store_deal_mapping(salesforce_loan_id: str, deal_id: int) -> None:
    """
    Store mapping of Salesforce Loan ID → Deal ID.
    
    Args:
        salesforce_loan_id: Salesforce Loan ID
        deal_id: Pipedrive Deal ID
    """
    mappings = load_mappings()
    mappings[str(salesforce_loan_id)] = int(deal_id)
    save_mappings(mappings)
    logger.info(f"Stored mapping: Loan {salesforce_loan_id} → Deal {deal_id} (total mappings: {len(mappings)})")


def remove_deal_mapping(salesforce_loan_id: str) -> None:
    """
    Remove mapping for a Salesforce Loan ID.
    
    Args:
        salesforce_loan_id: Salesforce Loan ID
    """
    mappings = load_mappings()
    if str(salesforce_loan_id) in mappings:
        del mappings[str(salesforce_loan_id)]
        save_mappings(mappings)
        logger.debug(f"Removed mapping for Loan {salesforce_loan_id}")

