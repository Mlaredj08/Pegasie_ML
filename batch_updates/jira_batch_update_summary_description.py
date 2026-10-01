import pandas as pd
import requests

# Jira server details
JIRA_URL = "http://192.168.10.172:8080"
JIRA_USER = "Armando"
JIRA_PASS = "Armando"

# Load enriched Excel file
df = pd.read_excel("ONTCM DATABASE 2025-10-10.xlsx")

# Iterate and update issues
for _, row in df.iterrows():
    issue_key = row["Key"]
    new_summary = row["Summary"]
    new_description = row["Description"]

    url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}"
    payload = {
        "fields": {
            "summary": new_summary,
            "description": new_description
        }
    }

    response = requests.put(
        url,
        json=payload,
        auth=(JIRA_USER, JIRA_PASS),
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 204:
        print(f"✅ Updated {issue_key}")
    else:
        print(f"❌ Failed {issue_key}: {response.status_code} {response.text}")
