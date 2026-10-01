#!/usr/bin/env python3
"""
Bulk reset & recreate Jira links from CSV.

- Clears ALL existing links on every issue that appears in the CSV
  (both as InwardIssue or OutwardIssue).
- Then recreates links from rows: InwardIssue,LinkType,OutwardIssue.

Test on a small subset first. Use DRY_RUN=True to preview actions.
"""

import csv
import time
import sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import requests
from requests.adapters import HTTPAdapter, Retry

# ----------------- CONFIG -----------------
JIRA_BASE = "http://192.168.10.172:8080"
USERNAME  = "Armando"
PASSWORD  = "Armando"

CSV_PATH  = "ONTCM_JIRA_LINKS.csv"  # columns: InwardIssue,LinkType,OutwardIssue
DRY_RUN   = False                    # True = no changes, only logs
TIMEOUT_S = 20
# Optional: slow down between destructive ops to reduce load
SLEEP_BETWEEN_DELETES = 0.1
SLEEP_BETWEEN_CREATES = 0.05
# ------------------------------------------


def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET", "POST", "DELETE"]
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.auth = (USERNAME, PASSWORD)
    s.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    return s


def read_links_from_csv(csv_path: str) -> List[Tuple[str, str, str]]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"InwardIssue", "LinkType", "OutwardIssue"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        for r in reader:
            inward = (r["InwardIssue"] or "").strip()
            ltype  = (r["LinkType"] or "").strip()
            outward= (r["OutwardIssue"] or "").strip()
            if inward and ltype and outward and inward != outward:
                rows.append((inward, ltype, outward))
    return rows


def collect_unique_issues(links: List[Tuple[str, str, str]]) -> Set[str]:
    issues = set()
    for a, _, b in links:
        issues.add(a)
        issues.add(b)
    return issues


def get_issue_links(session: requests.Session, key: str) -> List[Dict]:
    """Return list of issuelinks objects from Jira's issue response."""
    url = f"{JIRA_BASE}/rest/api/2/issue/{key}?fields=issuelinks"
    r = session.get(url, timeout=TIMEOUT_S)
    if r.status_code == 404:
        print(f"⚠️  Issue not found: {key}")
        return []
    r.raise_for_status()
    data = r.json()
    links = (data.get("fields", {}) or {}).get("issuelinks", []) or []
    return links


def delete_link(session: requests.Session, link_id: str) -> None:
    url = f"{JIRA_BASE}/rest/api/2/issueLink/{link_id}"
    if DRY_RUN:
        print(f"DRY_RUN: Would DELETE link id={link_id}")
        return
    r = session.delete(url, timeout=TIMEOUT_S)
    if r.status_code in (204, 200):
        print(f"✅ Deleted link id={link_id}")
    else:
        print(f"❌ Delete failed for link id={link_id}: [{r.status_code}] {r.text}")


def clear_links_for_issues(session: requests.Session, issues: Set[str]) -> None:
    """Delete ALL existing links for each issue in issues (deduping by link id)."""
    seen_link_ids: Set[str] = set()
    for key in sorted(issues):
        links = get_issue_links(session, key)
        if not links:
            print(f"ℹ️  No links on {key}")
            continue
        print(f"Found {len(links)} link(s) on {key} — deleting...")
        for l in links:
            link_id = str(l.get("id", "")).strip()
            if not link_id or link_id in seen_link_ids:
                continue
            seen_link_ids.add(link_id)
            delete_link(session, link_id)
            if SLEEP_BETWEEN_DELETES:
                time.sleep(SLEEP_BETWEEN_DELETES)


def create_link(session: requests.Session, inward: str, ltype: str, outward: str) -> None:
    """POST /rest/api/2/issueLink"""
    payload = {
        "type": {"name": ltype},             # e.g., "Blocks", "Relates", etc.
        "inwardIssue": {"key": inward},
        "outwardIssue": {"key": outward},
    }
    if DRY_RUN:
        print(f"DRY_RUN: Would CREATE link {inward} -[{ltype}]-> {outward}")
        return
    url = f"{JIRA_BASE}/rest/api/2/issueLink"
    r = session.post(url, json=payload, timeout=TIMEOUT_S)
    if r.status_code in (201, 200, 204):
        print(f"✅ Created link {inward} -[{ltype}]-> {outward}")
    else:
        print(f"❌ Create failed for {inward} -[{ltype}]-> {outward}: [{r.status_code}] {r.text}")


def recreate_links(session: requests.Session, links: List[Tuple[str, str, str]]) -> None:
    # Optional: group by (inward, ltype, outward) to dedupe CSV
    seen = set()
    for inward, ltype, outward in links:
        key = (inward, ltype, outward)
        if key in seen:
            continue
        seen.add(key)
        create_link(session, inward, ltype, outward)
        if SLEEP_BETWEEN_CREATES:
            time.sleep(SLEEP_BETWEEN_CREATES)


def main():
    try:
        links = read_links_from_csv(CSV_PATH)
        if not links:
            print("No valid link rows found in CSV. Nothing to do.")
            return

        issues = collect_unique_issues(links)
        print(f"Parsed {len(links)} link rows; {len(issues)} unique issues to reset.")

        session = make_session()

        # 1) Clear all existing links on all involved issues
        print("\n--- Clearing existing links ---")
        clear_links_for_issues(session, issues)

        # 2) Recreate links per CSV
        print("\n--- Creating links from CSV ---")
        recreate_links(session, links)

        print("\nDone.")
        if DRY_RUN:
            print("DRY_RUN was enabled: no changes were made.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
