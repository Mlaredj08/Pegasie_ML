import requests
import json
import os
import base64
from datetime import datetime
from config.constants import DATABASES_FOLDER, DATABASES_SETTINGS_FOLDER, AZURE_API_VERSION

os.makedirs(DATABASES_FOLDER, exist_ok=True)
os.makedirs(DATABASES_SETTINGS_FOLDER, exist_ok=True)

def _build_headers(pat: str):
    """
    Build the correct Azure DevOps headers for PAT authentication.
    Username must be empty, password = PAT, encoded as :PAT
    """
    token = f":{pat}"
    b64 = base64.b64encode(token.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {b64}",
        "Content-Type": "application/json"
    }


def export_azure_work_items(org_url, project, pat, fields_to_include, work_item_types, timestamp=None):
    headers = _build_headers(pat)

    # ----- Build Wiql query -----
    wiql = {
        "query": f"SELECT [System.Id], [System.Title], [System.WorkItemType] "
                 f"FROM WorkItems WHERE [System.TeamProject] = '{project}'"
                 + (f" AND [System.WorkItemType] IN ({','.join([repr(t) for t in work_item_types])})"
                    if work_item_types else "")
    }

    wiql_url = f"{org_url.rstrip('/')}/{project}/_apis/wit/wiql?api-version=" + AZURE_API_VERSION
    resp = requests.post(wiql_url, headers=headers, json=wiql)
    resp.raise_for_status()
    work_items = resp.json().get("workItems", [])

    all_items = []
    for batch_start in range(0, len(work_items), 100):
        batch_ids = [str(wi["id"]) for wi in work_items[batch_start:batch_start + 100]]
        if not batch_ids:
            continue
        items_url = (
            f"{org_url.rstrip('/')}/_apis/wit/workitems"
            f"?ids={','.join(batch_ids)}&fields={','.join(fields_to_include)}&api-version=" + AZURE_API_VERSION
        )
        resp = requests.get(items_url, headers=headers)
        resp.raise_for_status()
        for wi in resp.json().get("value", []):
            fields = wi.get("fields", {})
            item_data = {"id": wi["id"], "url": wi.get("url")}
            for f in fields_to_include:
                item_data[f] = fields.get(f)
            all_items.append(item_data)

    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ----- Save JSON data -----
    filename = f"{project}_azure_{timestamp}.json"
    filepath = os.path.join(DATABASES_FOLDER, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)

    # ----- Save settings file -----
    settings_filename = f"{project}_azure_{timestamp}_settings.json"
    settings_path = os.path.join(DATABASES_SETTINGS_FOLDER, settings_filename)
    settings = {
        "project": project,
        "orgUrl": org_url,
        "exportedAt": timestamp,
        "totalItems": len(all_items),
        "filters": {
            "workItemTypes": work_item_types or [],
            "fieldsIncluded": fields_to_include or []
        }
    }
    with open(settings_path, "w", encoding="utf-8") as sf:
        json.dump(settings, sf, indent=2, ensure_ascii=False)

    return filepath, len(all_items)
