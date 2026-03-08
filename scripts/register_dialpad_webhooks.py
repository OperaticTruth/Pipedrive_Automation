"""
Run this once to register webhooks in Dialpad.

Usage:
  Production:  python scripts/register_dialpad_webhooks.py
  Local test:  set RENDER_URL=https://YOUR-NGROK-URL.ngrok-free.app
               python scripts/register_dialpad_webhooks.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("DIALPAD_API_KEY")
RENDER_URL = os.environ.get("RENDER_URL", "https://pipedrive-automation.onrender.com")

if not API_KEY:
    print("Set DIALPAD_API_KEY in .env")
    exit(1)

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
BASE = "https://dialpad.com/api/v2"


def get_user_id():
    """Fetch the first user's ID from the account."""
    r = requests.get(f"{BASE}/users", headers=HEADERS, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError("No users found in Dialpad account")
    user_id = items[0]["id"]
    name = items[0].get("display_name", "unknown")
    print(f"Targeting user: {name} (id={user_id})")
    return str(user_id)


def create_call_webhook():
    """Step 1a: Register the call URL endpoint. Returns webhook dict."""
    payload = {"hook_url": f"{RENDER_URL}/webhook/dialpad/call"}
    r = requests.post(f"{BASE}/webhooks", headers=HEADERS, json=payload, timeout=30)
    print(f"Create call webhook: {r.status_code} — {r.text}")
    return r.json() if r.ok else None


def create_contact_webhook():
    """Step 1b: Register the contact URL endpoint. Returns webhook dict."""
    payload = {"hook_url": f"{RENDER_URL}/webhook/dialpad/contact"}
    r = requests.post(f"{BASE}/webhooks", headers=HEADERS, json=payload, timeout=30)
    print(f"Create contact webhook: {r.status_code} — {r.text}")
    return r.json() if r.ok else None


def create_call_subscription(webhook_id: str, user_id: str):
    """Step 2a: Subscribe to call events for this user."""
    payload = {
        "webhook_id": webhook_id,
        "target_type": "user",
        "target_id": user_id,
        "call_states": ["hangup", "missed"],
        "enabled": True,
    }
    r = requests.post(f"{BASE}/subscriptions/call", headers=HEADERS, json=payload, timeout=30)
    print(f"Call subscription: {r.status_code} — {r.text}")
    return r.json() if r.ok else None


def create_contact_subscription(webhook_id: str, user_id: str):
    """Step 2b: Subscribe to contact create/update events for this user."""
    payload = {
        "webhook_id": webhook_id,
        "target_type": "user",
        "target_id": user_id,
        "contact_type": "local",
        "enabled": True,
    }
    r = requests.post(f"{BASE}/subscriptions/contact", headers=HEADERS, json=payload, timeout=30)
    print(f"Contact subscription: {r.status_code} — {r.text}")
    return r.json() if r.ok else None


if __name__ == "__main__":
    print(f"Registering webhooks for: {RENDER_URL}")
    user_id = get_user_id()

    # --- Call webhook + subscription ---
    call_wh = create_call_webhook()
    call_webhook_id = call_wh.get("id") if call_wh else None

    if not call_webhook_id:
        print("Failed to create call webhook — check API key and Render URL")
        exit(1)

    call_sub = create_call_subscription(str(call_webhook_id), user_id)
    if call_sub and call_sub.get("id"):
        print(f"Call setup done. Webhook ID: {call_webhook_id} | Subscription ID: {call_sub.get('id')}")
    else:
        print(f"Call webhook created (ID: {call_webhook_id}) but call subscription failed — see above")

    print()

    # --- Contact webhook + subscription ---
    contact_wh = create_contact_webhook()
    contact_webhook_id = contact_wh.get("id") if contact_wh else None

    if not contact_webhook_id:
        print("Failed to create contact webhook — skipping contact subscription")
    else:
        contact_sub = create_contact_subscription(str(contact_webhook_id), user_id)
        if contact_sub and contact_sub.get("id"):
            print(f"Contact setup done. Webhook ID: {contact_webhook_id} | Subscription ID: {contact_sub.get('id')}")
        else:
            print(f"Contact webhook created (ID: {contact_webhook_id}) but contact subscription failed — see above")
