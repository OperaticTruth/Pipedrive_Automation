"""Delete ALL existing Dialpad webhooks and subscriptions — run before re-registering."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("DIALPAD_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
BASE = "https://dialpad.com/api/v2"


def delete_all(label, list_url, delete_url_template):
    r = requests.get(list_url, headers=HEADERS, timeout=30)
    print(f"List {label}: {r.status_code}")
    items = r.json().get("items", [])
    if not items:
        print(f"  No {label} found.")
        return
    for item in items:
        item_id = item.get("id")
        d = requests.delete(delete_url_template.format(item_id), headers=HEADERS, timeout=30)
        hook = item.get("hook_url", item.get("webhook_id", ""))
        print(f"  Deleted {label} {item_id} ({hook}): {d.status_code}")


# Webhooks
delete_all("webhooks", f"{BASE}/webhooks", f"{BASE}/webhooks/{{}}")

# Call subscriptions
delete_all("call subscriptions", f"{BASE}/subscriptions/call", f"{BASE}/subscriptions/call/{{}}")

# Contact subscriptions
delete_all("contact subscriptions", f"{BASE}/subscriptions/contact", f"{BASE}/subscriptions/contact/{{}}")

print("Done.")
