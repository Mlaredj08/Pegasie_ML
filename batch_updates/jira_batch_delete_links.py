#!/usr/bin/env python3
import json
import requests
from requests.auth import HTTPBasicAuth

# ----------------- CONFIG -----------------
JIRA_URL = "http://192.168.10.172:8080"
USERNAME  = "Armando"
PASSWORD  = "Armando"
auth = HTTPBasicAuth(USERNAME, PASSWORD)
headers = {'Content-Type': 'application/json'}
DRY_RUN   = False


def delete_existing_links(issues, link_types_to_delete=None):
    print("Deleting existing links in target project first...")

    # Descriptive message about what we are doing
    if link_types_to_delete:
        print(f"Filter active: Only deleting links of type: {link_types_to_delete}")
    else:
        print("No filter: Deleting ALL link types.")

    for issue in issues:
        target_key = issue['key']
        local_links = issue.get("issuelinks", [])
        # target_key = issue['key'].replace(SOURCE_PROJECT, TARGET_PROJECT)

        if not local_links:
            # JSON says no links exist at all
            print(f" [SKIP-CHECK] {target_key}: No links defined in source JSON.")
            continue

        if link_types_to_delete:
            # Check if any link in the JSON matches the types we want to delete
            # Note: We check 'type' -> 'name' or just 'type' depending on your JSON structure
            has_relevant_link = False
            for link in local_links:
                type_name = str(link.get("type"))

                if type_name.lower() in link_types_to_delete:
                    has_relevant_link = True
                    break

            if not has_relevant_link:
                print(f" [SKIP-CHECK] {target_key}: No links of type {link_types_to_delete} found in JSON.")
                continue

        url = f"{JIRA_URL}/rest/api/2/issue/{target_key}"
        print(f" Checking links for {target_key}")
        resp = requests.get(url, auth=auth, headers=headers).json()
        existing_links = resp.get("fields", {}).get("issuelinks", [])

        if not existing_links:
            print("  No links found.")
            continue

        for link in existing_links:
            link_id = link.get("id")
            inward = link.get("inwardIssue")
            outward = link.get("outwardIssue")
            link_type = ""
            target_link_key = ""
            if inward:
                link_type = link["type"]["inward"]
                target_link_key = inward["key"]
            elif outward:
                link_type = link["type"]["outward"]
                target_link_key = outward["key"]

            if not link_id:
                continue

            # If a specific list is provided, skip links that are NOT in that list
            link_type_name = link_type.lower()
            if link_types_to_delete and link_type_name not in link_types_to_delete:
                # print(f"  [SKIPPING] Link {link_id} (Type: '{link_type_name}') - Not in deletion list.")
                continue

            if DRY_RUN:
                print(f"DRY_RUN: Would DELETE link: {target_key} '{link_type_name}' {target_link_key} - (link_id={link_id})")
                continue

            del_resp = requests.delete(
                f"{JIRA_URL}/rest/api/2/issueLink/{link_id}",
                auth=auth,
                headers=headers
            )

            if del_resp.status_code in (204, 200):
                print(f"DELETED link: {target_key} '{link_type_name}' {target_link_key} - (link_id={link_id})")
            else:
                print(f"  [FAILED DELETE] link {link_id}: {del_resp.text}")

    print("✅ All existing links deleted.\n")


if __name__ == "__main__":
    SOURCE_JSON_FILE = "BOOK_20251119_094349.json"
    link_types_to_delete = ["relates to","relates"]

    if SOURCE_JSON_FILE.strip():
        print(f"Loading SOURCE from JSON: {SOURCE_JSON_FILE}")
        with open(SOURCE_JSON_FILE, "r", encoding="utf-8") as f:
            src = json.load(f)

    delete_existing_links(src, link_types_to_delete)
