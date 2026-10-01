#!/usr/bin/env python3
import json
import requests
from requests.auth import HTTPBasicAuth

# ----------------- CONFIG -----------------
JIRA_URL = "http://192.168.10.172:8080"
USERNAME = "Armando"
PASSWORD = "Armando"
auth = HTTPBasicAuth(USERNAME, PASSWORD)
headers = {'Content-Type': 'application/json'}
DRY_RUN = False  # Set to True to preview changes without deleting


def delete_issue_labels(issues):
    print("Starting label deletion process...")

    for issue in issues:
        target_key = issue.get('key')

        # 1. Check Local JSON first to optimize
        # In your JSON structure, 'labels' is a list of strings
        local_labels = issue.get("labels", [])

        if not local_labels:
            print(f" [SKIP-CHECK] {target_key}: No labels defined in source JSON.")
            continue

        # If we reach here, the JSON suggests labels exist.
        # We proceed to delete them from Jira.

        if DRY_RUN:
            print(f" [DRY_RUN] Would REMOVE all labels from {target_key} (Local JSON had: {local_labels})")
            continue

        # 2. Construct the Payload to clear labels
        # Sending an empty list [] for the labels field removes them all.
        payload = {
            "fields": {
                "labels": []
            }
        }

        url = f"{JIRA_URL}/rest/api/2/issue/{target_key}"

        try:
            # 3. Perform the PUT request to update the issue
            resp = requests.put(
                url,
                auth=auth,
                headers=headers,
                data=json.dumps(payload)
            )

            if resp.status_code in (200, 204):
                print(f" [CLEARED] Labels removed from {target_key}")
            else:
                print(f" [FAILED] Could not remove labels from {target_key}: {resp.status_code} - {resp.text}")

        except Exception as e:
            print(f" [ERROR] Exception occurred processing {target_key}: {str(e)}")

    print("\n✅ Label deletion process finished.\n")


if __name__ == "__main__":
    SOURCE_JSON_FILE = "BOOK_20251119_094349.json"  # Replace with your file name

    if SOURCE_JSON_FILE.strip():
        try:
            print(f"Loading SOURCE from JSON: {SOURCE_JSON_FILE}")
            with open(SOURCE_JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle if the JSON is a list or a dict containing a list
            if isinstance(data, dict) and "issues" in data:
                issues_list = data["issues"]
            elif isinstance(data, list):
                issues_list = data
            else:
                issues_list = []
                print("Error: Could not determine issue list from JSON structure.")

            if issues_list:
                delete_issue_labels(issues_list)

        except FileNotFoundError:
            print(f"Error: File {SOURCE_JSON_FILE} not found.")
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON format in {SOURCE_JSON_FILE}.")