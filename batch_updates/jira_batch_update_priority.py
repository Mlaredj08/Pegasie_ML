#!/usr/bin/env python3
"""
Bulk update Jira priorities from Excel (run directly from main).

Excel must contain columns:
  - "Issue key"            e.g., ONTCM-123
  - "Suggested Priority"   e.g., Highest / High / Medium / Low

This version has no CLI args. Configure constants below and run:
  python update_priorities_main.py
"""

import time
import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry

# =============== CONFIG ===============
JIRA_BASE  = "http://192.168.10.172:8080"       # Your Jira Server/DC base URL
JIRA_USER  = "Armando"                    # <-- fill in
JIRA_PASS  = "Armando"                    # <-- fill in

EXCEL_PATH = "ONTCM_UPDATE_DESCRIPTION_WITH_PRIORITY.xlsx"
SHEET      = 0          # index or sheet name
DRY_RUN    = False      # True = only print actions, no changes
LIMIT      = 0          # 0 = no limit, or set e.g. 50 to test
SKIP_UNCHANGED = True   # Avoid PUT if current priority already matches
TIMEOUT_S  = 20
SLEEP_BETWEEN_UPDATES = 0.05
# =====================================


def make_session(user, pwd):
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET", "PUT", "POST"]
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.auth = (user, pwd)
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return s


def get_all_priorities(session, base):
    """Return list of priority dicts from the instance."""
    url = f"{base}/rest/api/2/priority"
    r = session.get(url, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def _norm(s):
    return (s or "").strip().lower()


def _canonical_bucket(label):
    """Map various synonyms to canonical buckets."""
    s = _norm(label)
    if s in {"highest", "critical", "blocker", "p1", "urgent", "severe"}:
        return "highest"
    if s in {"high", "major", "p2"}:
        return "high"
    if s in {"medium", "normal", "p3"}:
        return "medium"
    if s in {"low", "minor", "trivial", "p4", "p5"}:
        return "low"
    return s


def build_priority_picker(priorities):
    """
    Build a resolver that maps our label (Highest/High/Medium/Low or synonyms)
    to a real priority name in THIS Jira instance.
    Strategy:
      1) Direct case-insensitive name match.
      2) Canonical bucket → pick position in instance list (first/second/middle/last).
      3) Fallback: substring contains / middle.
    """
    names = [p["name"] for p in priorities]
    norm_to_real = {_norm(n): n for n in names}

    def pick(desired):
        if not desired:
            return None
        dn = _norm(desired)
        if dn in norm_to_real:
            return norm_to_real[dn]

        bucket = _canonical_bucket(dn)
        n = len(names)
        if n == 0:
            return None
        if bucket == "highest":
            return names[0]
        if bucket == "high":
            return names[min(1, n - 1)]
        if bucket == "medium":
            return names[n // 2]
        if bucket == "low":
            return names[-1]

        for real in names:
            if bucket in _norm(real):
                return real

        return names[n // 2]

    return pick


def get_issue_priority_name(session, base, issue_key):
    url = f"{base}/rest/api/2/issue/{issue_key}?fields=priority"
    r = session.get(url, timeout=TIMEOUT_S)
    if r.status_code == 404:
        print(f"⚠️  Issue not found: {issue_key}")
        return None
    r.raise_for_status()
    data = r.json()
    pr = ((data.get("fields") or {}).get("priority") or {})
    return pr.get("name")


def update_issue_priority(session, base, issue_key, priority_name, dry_run=False):
    url = f"{base}/rest/api/2/issue/{issue_key}"
    payload = {"fields": {"priority": {"name": priority_name}}}
    if dry_run:
        print(f"DRY_RUN: Would set {issue_key} priority -> {priority_name}")
        return True
    r = session.put(url, json=payload, timeout=TIMEOUT_S)
    if r.status_code in (204, 200):
        print(f"✅ Updated {issue_key} -> {priority_name}")
        return True
    else:
        print(f"❌ Failed {issue_key}: [{r.status_code}] {r.text}")
        return False


def main():
    # Load Excel
    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET)
    except Exception as e:
        print(f"ERROR reading Excel '{EXCEL_PATH}': {e}")
        return

    # Validate columns
    required = {"Issue key", "Suggested Priority"}
    missing = required - set(df.columns)
    if missing:
        print(f"ERROR: Excel missing required columns: {missing}")
        return

    # Auth/session
    session = make_session(JIRA_USER, JIRA_PASS)

    # Fetch instance priorities
    try:
        pri_list = get_all_priorities(session, JIRA_BASE)
    except Exception as e:
        print(f"ERROR fetching priorities: {e}")
        return

    pick_priority = build_priority_picker(pri_list)

    total = 0
    updated = 0
    skipped = 0
    failed = 0

    for _, row in df.iterrows():
        issue_key = str(row.get("Issue key", "")).strip()
        target_label = str(row.get("Suggested Priority", "")).strip()
        if not issue_key or not target_label:
            continue

        total += 1
        if LIMIT and total > LIMIT:
            break

        resolved_name = pick_priority(target_label)
        if not resolved_name:
            print(f"❓ Could not resolve priority for {issue_key} (label='{target_label}')")
            failed += 1
            continue

        if SKIP_UNCHANGED:
            try:
                current = get_issue_priority_name(session, JIRA_BASE, issue_key)
            except Exception as e:
                print(f"⚠️  Could not read current priority for {issue_key}: {e}")
                current = None
            if current and _norm(current) == _norm(resolved_name):
                print(f"⏭️  Skipping {issue_key} (already '{current}')")
                skipped += 1
                continue

        ok = update_issue_priority(session, JIRA_BASE, issue_key, resolved_name, dry_run=DRY_RUN)
        if ok:
            updated += 1
        else:
            failed += 1

        if SLEEP_BETWEEN_UPDATES:
            time.sleep(SLEEP_BETWEEN_UPDATES)

    print("\n--- Summary ---")
    print(f"Rows seen   : {total}")
    print(f"Updated     : {updated}")
    print(f"Skipped     : {skipped}")
    print(f"Failed      : {failed}")
    if DRY_RUN:
        print("DRY_RUN was enabled (no changes made).")


if __name__ == "__main__":
    main()
