import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = "https://api.pipedrive.com/v1"
PIPEDRIVE_API_KEY = os.getenv("PIPEDRIVE_API_KEY")
COBORROWER_KEY = os.getenv("COBORROWER_KEY") or "1d9f3e850fd4fbcf9ffd0b1eef9522e1d98574fc"


def extract_person_id(value):
    if isinstance(value, dict):
        value = value.get("value")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_open_deals():
    url = f"{BASE_URL}/deals"
    params = {
        "api_token": PIPEDRIVE_API_KEY,
        "status": "open",
        "limit": 500,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success", True):
        raise RuntimeError(f"Failed to fetch open deals: {result}")
    return result.get("data") or []


def get_deal_participants(deal_id):
    url = f"{BASE_URL}/deals/{deal_id}/participants"
    params = {"api_token": PIPEDRIVE_API_KEY}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success", True):
        raise RuntimeError(f"Failed to fetch participants for deal {deal_id}: {result}")
    participants = result.get("data") or []
    person_ids = set()
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        participant_person_id = participant.get("person_id")
        if isinstance(participant_person_id, dict):
            participant_person_id = participant_person_id.get("value")
        elif participant_person_id is None:
            person = participant.get("person")
            if isinstance(person, dict):
                participant_person_id = person.get("id")
        participant_person_id = extract_person_id(participant_person_id)
        if participant_person_id is not None:
            person_ids.add(participant_person_id)
    return person_ids


def add_deal_participant(deal_id, person_id, dry_run=False):
    if dry_run:
        print(f"[DRY RUN] Would add Person {person_id} as participant to Deal {deal_id}")
        return True

    url = f"{BASE_URL}/deals/{deal_id}/participants"
    params = {"api_token": PIPEDRIVE_API_KEY}
    resp = requests.post(url, params=params, json={"person_id": person_id})
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success", True):
        raise RuntimeError(f"Failed to add participant to deal {deal_id}: {result}")
    print(f"Added Person {person_id} as participant to Deal {deal_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Backfill Pipedrive co-borrower deal participants")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without making changes")
    args = parser.parse_args()

    if not PIPEDRIVE_API_KEY:
        print("Missing PIPEDRIVE_API_KEY in environment/.env", file=sys.stderr)
        sys.exit(1)

    deals_checked = 0
    participants_added = 0
    already_correct = 0

    deals = get_open_deals()
    print(f"Fetched {len(deals)} open deals")

    for deal in deals:
        deals_checked += 1
        deal_id = deal.get("id")
        primary_person_id = extract_person_id(deal.get("person_id"))
        coborrower_person_id = extract_person_id(deal.get(COBORROWER_KEY))

        print(f"Checking Deal {deal_id}")

        participants = get_deal_participants(deal_id)

        if coborrower_person_id:
            if coborrower_person_id == primary_person_id:
                print(
                    f"Deal {deal_id}: co-borrower field points to primary person {primary_person_id}; skipping"
                )
            elif coborrower_person_id in participants:
                print(f"Deal {deal_id}: co-borrower {coborrower_person_id} already a participant")
                already_correct += 1
            else:
                add_deal_participant(deal_id, coborrower_person_id, dry_run=args.dry_run)
                participants_added += 1
        else:
            print(
                f"Deal {deal_id}: co-borrower field empty; edge-case unlinked associated people check skipped"
            )

        time.sleep(0.2)

    print("\nSummary")
    print(f"Deals checked: {deals_checked}")
    print(f"Participants added: {participants_added}")
    print(f"Already correct: {already_correct}")


if __name__ == "__main__":
    main()
