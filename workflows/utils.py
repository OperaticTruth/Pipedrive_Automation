import requests
from config import PIPEDRIVE_API_KEY

BASE_URL = "https://api.pipedrive.com/v1"

def update_deal_field(deal_id, field_name, new_value):
    url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
    resp = requests.put(url, json={field_name: new_value})
    print(f"[API] Updated '{field_name}' to {new_value} for Deal #{deal_id} (Status {resp.status_code})")

def update_deal_custom_field(deal_id, field_key, new_value):
    url = f"{BASE_URL}/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
    resp = requests.put(url, json={field_key: new_value})
    print(f"[API] Updated custom '{field_key}' to {new_value} for Deal #{deal_id} (Status {resp.status_code})")

def update_person_custom_field(person_id, field_key, new_value):
    url = f"{BASE_URL}/persons/{person_id}?api_token={PIPEDRIVE_API_KEY}"
    resp = requests.put(url, json={field_key: new_value})
    print(f"[API] Updated custom '{field_key}' to {new_value} for Person #{person_id} (Status {resp.status_code})") 