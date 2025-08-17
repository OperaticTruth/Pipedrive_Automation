# fetch_stages.py
#!/usr/bin/env python3
import requests
from config import PIPEDRIVE_API_KEY

BASE_URL = "https://api.pipedrive.com/v1"

def fetch_pipeline_stages(pipeline_id):
    """
    Fetch and print all stages for a given pipeline ID.
    """
    url = f"{BASE_URL}/stages?api_token={PIPEDRIVE_API_KEY}&pipeline_id={pipeline_id}"
    resp = requests.get(url)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"API error: {payload}")
    stages = payload["data"]
    print(f"Pipeline {pipeline_id} stages:")
    for s in stages:
        print(f" • {s['name']} (ID = {s['id']})")
    return stages

if __name__ == "__main__":
    # Replace 2 with your actual pipeline ID (you’ve said it’s 2)
    fetch_pipeline_stages(2)
