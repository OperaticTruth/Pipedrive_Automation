"""
Read-only verifier for the Pipedrive lead lookup fix.

Usage:
    python workflows/salesforce_sync/test_lead_fix.py <phone_number>
"""

import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from workflows.salesforce_sync.sync_person import find_person_by_phone
from workflows.salesforce_sync.sync_deal import find_active_lead_for_person

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) != 2:
        print("Usage: python workflows/salesforce_sync/test_lead_fix.py <phone_number>")
        return 1

    phone = sys.argv[1]
    print(f"Testing read-only lead lookup for phone: {phone}")

    person_id = find_person_by_phone(phone)
    print(f"Person found: {person_id}")

    lead_id = None
    if person_id:
        lead_id = find_active_lead_for_person(person_id)
        print(f"Lead found: {lead_id}")
    else:
        print("Lead lookup skipped: no matching person")

    print("What a real sync would do:")
    if person_id and lead_id:
        print(f"- Reuse existing Person {person_id}")
        print(f"- Convert existing Lead {lead_id} to a Deal via Pipedrive API")
        print("- Populate the converted deal with Salesforce loan data")
    elif person_id:
        print(f"- Reuse existing Person {person_id}")
        print("- No active lead found, so sync would create a new Deal")
    else:
        print("- No existing person found, so sync would create a new Person")
        print("- Then sync would create a new Deal if no existing deal matched")

    print("Read-only check complete. No API writes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
