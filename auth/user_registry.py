# auth/user_registry.py
"""
Persistent Jira user registry.

Maintains a JSON file (auth/jira_user_registry.json) that tracks all users
who have ever authenticated through the application. Structure:

{
  "jira_server": {
    "<url>": {
      "users": {
        "<username>": {
          "username": "<username>",
          "projects": ["PROJ1", "PROJ2"],
          "last_login": "2025-06-02T10:30:00"
        }
      }
    }
  },
  "jira_cloud": {
    "<url>": {
      "users": { ... }
    }
  }
}

This file is NOT gitignored — it is a permanent reference for project access
across the application.
"""
import json
import os
from datetime import datetime
from typing import List, Optional

import requests
from requests.auth import HTTPBasicAuth

from config.constants import BASE_DIR, JIRA_USERS_FILE

REGISTRY_FILE = os.path.join(BASE_DIR, "auth", "jira_user_registry.json")


def _detect_jira_type(jira_url: str) -> str:
    """Return 'jira_cloud' or 'jira_server' based on URL."""
    return "jira_cloud" if ".atlassian.net" in jira_url.lower() else "jira_server"


def _normalize_registry_users(registry: dict) -> dict:
    """Migrate any mixed-case username keys to lowercase, merging duplicates."""
    for jira_type in ("jira_server", "jira_cloud"):
        for url_data in registry.get(jira_type, {}).values():
            users = url_data.get("users", {})
            normalized: dict = {}
            for raw_key, entry in users.items():
                key = raw_key.lower()
                if key in normalized:
                    # Merge: keep the more recent entry, union the projects
                    existing = normalized[key]
                    merged_projects = sorted(
                        set(existing.get("projects", [])) | set(entry.get("projects", []))
                    )
                    keep = existing if (existing.get("last_login", "") >= entry.get("last_login", "")) else entry
                    normalized[key] = {
                        "username": key,
                        "projects": merged_projects,
                        "last_login": keep.get("last_login", ""),
                    }
                else:
                    normalized[key] = dict(entry)
                    normalized[key]["username"] = key
            url_data["users"] = normalized
    return registry


def _load_registry() -> dict:
    """Load the registry from disk, returning empty structure if missing."""
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
            return _normalize_registry_users(registry)
        except (json.JSONDecodeError, OSError):
            pass
    return {"jira_server": {}, "jira_cloud": {}}


def _save_registry(registry: dict) -> None:
    """Persist the registry to disk."""
    os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def _verify_tracked_projects(
    jira_url: str, username: str, password: str, tracked_projects: List[str]
) -> List[str]:
    """
    Verify that the user still has CREATE_ISSUES access to their tracked projects.
    Only checks the projects already in the user's registry entry — not all projects
    on the server. Returns the subset of tracked_projects that are still accessible.

    If the user has no tracked projects yet, returns an empty list (no API calls).
    """
    if not tracked_projects:
        return []

    auth = HTTPBasicAuth(username, password)
    base_url = jira_url.rstrip("/")
    is_cloud = ".atlassian.net" in base_url.lower()

    if is_cloud:
        return _verify_projects_cloud(base_url, auth, tracked_projects)
    else:
        return _verify_projects_server(base_url, auth, tracked_projects)


def _verify_projects_cloud(base_url: str, auth, tracked_projects: List[str]) -> List[str]:
    """Verify tracked projects on Jira Cloud using mypermissions."""
    accessible = []
    for key in tracked_projects:
        url = f"{base_url}/rest/api/3/mypermissions?projectKey={key}&permissions=CREATE_ISSUES"
        try:
            resp = requests.get(url, auth=auth, timeout=10)
            if resp.ok:
                perms = resp.json().get("permissions", {})
                if perms.get("CREATE_ISSUES", {}).get("havePermission", False):
                    accessible.append(key)
                else:
                    print(f"[INFO] User lost access to project {key} (Cloud)")
            else:
                # If API fails for a project, keep it (fail-open)
                accessible.append(key)
        except requests.RequestException:
            accessible.append(key)
    return sorted(accessible)


def _verify_projects_server(base_url: str, auth, tracked_projects: List[str]) -> List[str]:
    """
    Verify tracked projects on Jira Server/Data Center.

    Strategy:
    1. Try bulk POST /rest/api/2/permissions/check (requires project IDs)
    2. Fall back to per-project /mypermissions check
    """
    # First try to resolve project keys to IDs for bulk check
    key_to_id = {}
    for key in tracked_projects:
        url = f"{base_url}/rest/api/2/project/{key}"
        try:
            resp = requests.get(url, auth=auth, timeout=10)
            if resp.ok:
                key_to_id[key] = int(resp.json()["id"])
            elif resp.status_code == 404:
                # Project no longer exists or user cannot see it at all
                print(f"[INFO] Project {key} not found or not visible — removing")
        except requests.RequestException:
            # On failure, keep the project (fail-open)
            key_to_id[key] = None

    # Projects that resolved to IDs — try bulk permission check
    resolved = {k: v for k, v in key_to_id.items() if v is not None}
    if resolved:
        id_to_key = {v: k for k, v in resolved.items()}
        project_ids = list(resolved.values())

        bulk_url = f"{base_url}/rest/api/2/permissions/check"
        payload = {
            "projectPermissions": [{
                "permissions": ["CREATE_ISSUES"],
                "projects": project_ids
            }]
        }
        try:
            resp = requests.post(bulk_url, json=payload, auth=auth, timeout=20)
            if resp.ok:
                result = resp.json()
                granted_ids = set()
                for perm_entry in result.get("projectPermissions", []):
                    granted_ids.update(perm_entry.get("projects", []))
                accessible = [id_to_key[pid] for pid in granted_ids if pid in id_to_key]
                removed = set(resolved.keys()) - set(accessible)
                if removed:
                    print(f"[INFO] User lost access to projects: {sorted(removed)}")
                print(f"[INFO] Bulk permission check: {len(accessible)}/{len(tracked_projects)} projects still accessible")
                return sorted(accessible)
        except requests.RequestException as e:
            print(f"[DEBUG] Bulk permissions/check failed: {e}")

    # Fallback: per-project mypermissions check
    print("[INFO] Falling back to per-project permission check...")
    accessible = []
    for key in tracked_projects:
        url = f"{base_url}/rest/api/2/mypermissions?projectKey={key}&permissions=CREATE_ISSUES"
        try:
            resp = requests.get(url, auth=auth, timeout=10)
            if resp.ok:
                perms = resp.json().get("permissions", {})
                if perms.get("CREATE_ISSUES", {}).get("havePermission", False):
                    accessible.append(key)
                else:
                    print(f"[INFO] User lost access to project {key}")
            else:
                # If check fails, keep it (fail-open)
                accessible.append(key)
        except requests.RequestException:
            accessible.append(key)

    print(f"[INFO] Per-project permission check: {len(accessible)}/{len(tracked_projects)} projects still accessible")
    return sorted(accessible)


def update_user_registry(jira_url: str, username: str, password: str) -> List[str]:
    """
    Called on each successful login. Verifies that the user still has access to
    their previously tracked projects (removes any where access was revoked).
    Does NOT discover new projects — those are added when the user exports from
    the Jira connector module.

    Returns the list of project keys the user currently has access to.
    """
    jira_type = _detect_jira_type(jira_url)
    normalized_url = jira_url.rstrip("/")

    registry = _load_registry()

    # Ensure structure exists
    if jira_type not in registry:
        registry[jira_type] = {}
    if normalized_url not in registry[jira_type]:
        registry[jira_type][normalized_url] = {"users": {}}

    url_entry = registry[jira_type][normalized_url]
    if "users" not in url_entry:
        url_entry["users"] = {}

    username = username.lower()

    # Get existing tracked projects (empty for new users)
    existing_entry = url_entry.get("users", {}).get(username, {})
    tracked_projects = existing_entry.get("projects", [])

    # Verify access only for tracked projects (no API calls if list is empty)
    if tracked_projects:
        projects = _verify_tracked_projects(normalized_url, username, password, tracked_projects)
    else:
        projects = []

    # Update user entry
    now = datetime.now().isoformat(timespec="seconds")
    url_entry["users"][username] = {  # username is already lowercased above
        "username": username,
        "projects": projects,
        "last_login": now
    }

    _save_registry(registry)
    print(f"[INFO] Registry updated: {jira_type} / {normalized_url} / {username} → {len(projects)} projects")

    # Also update the per-URL jira_users cache file for user dropdowns
    _cache_url_users(normalized_url, username, password)

    return projects


def add_project_to_registry(jira_url: str, username: str, project_key: str) -> None:
    """
    Add a project to the user's tracked project list in the registry.
    Called when the user exports a project from the Jira connector module.

    This is the ONLY way projects get added to the registry — login only
    verifies/prunes existing projects.
    """
    jira_type = _detect_jira_type(jira_url)
    normalized_url = jira_url.rstrip("/")

    registry = _load_registry()

    # Ensure structure exists
    if jira_type not in registry:
        registry[jira_type] = {}
    if normalized_url not in registry[jira_type]:
        registry[jira_type][normalized_url] = {"users": {}}

    url_entry = registry[jira_type][normalized_url]
    if "users" not in url_entry:
        url_entry["users"] = {}

    username = username.lower()

    # Get or create user entry
    if username not in url_entry["users"]:
        url_entry["users"][username] = {
            "username": username,
            "projects": [],
            "last_login": datetime.now().isoformat(timespec="seconds")
        }

    user_entry = url_entry["users"][username]
    if project_key not in user_entry["projects"]:
        user_entry["projects"].append(project_key)
        user_entry["projects"].sort()
        _save_registry(registry)
        print(f"[INFO] Added project '{project_key}' to registry for {username} @ {normalized_url}")
    else:
        print(f"[DEBUG] Project '{project_key}' already tracked for {username} @ {normalized_url}")


def _cache_url_users(jira_url: str, username: str, password: str) -> None:
    """
    Fetch all users for this Jira URL and cache them in jira_users.json
    keyed by URL so that the confirm_predictions page shows only relevant users.
    """
    auth = HTTPBasicAuth(username, password)
    is_cloud = ".atlassian.net" in jira_url.lower()

    users = []
    if is_cloud:
        url = f"{jira_url.rstrip('/')}/rest/api/3/users/search?query=&maxResults=1000"
        try:
            resp = requests.get(url, auth=auth, timeout=15)
            if resp.ok:
                for u in resp.json():
                    display_name = u.get("displayName", "")
                    email = u.get("emailAddress", "")
                    account_id = u.get("accountId", "")
                    if email:
                        users.append(f"{display_name} [{email}]")
                    elif account_id:
                        users.append(f"{display_name} [{account_id}]")
                    else:
                        users.append(display_name)
        except requests.RequestException as e:
            print(f"[WARNING] Failed to fetch cloud users: {e}")
    else:
        url = f"{jira_url.rstrip('/')}/rest/api/latest/user/search?username=.&includeInactive=false"
        try:
            resp = requests.get(url, auth=auth, timeout=15)
            if resp.ok:
                for u in resp.json():
                    name = u.get("name", u.get("displayName", ""))
                    email = u.get("emailAddress", "")
                    if email:
                        users.append(f"{name} [{email}]")
                    else:
                        users.append(name)
        except requests.RequestException as e:
            print(f"[WARNING] Failed to fetch server users: {e}")

    # Save per-URL users cache
    cache = {}
    if os.path.exists(JIRA_USERS_FILE):
        try:
            with open(JIRA_USERS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                # Migrate from old flat list format to dict-by-url format
                if isinstance(existing, dict):
                    cache = existing
                # Old format was a flat list — keep it under "__legacy" key
                elif isinstance(existing, list):
                    cache = {"__legacy": existing}
        except (json.JSONDecodeError, OSError):
            pass

    normalized_url = jira_url.rstrip("/")
    cache[normalized_url] = users

    with open(JIRA_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Cached {len(users)} users for URL: {normalized_url}")


def get_user_projects(jira_url: str, username: str) -> List[str]:
    """
    Retrieve the list of projects the user has access to from the registry.
    Returns empty list if user not found.
    """
    jira_type = _detect_jira_type(jira_url)
    normalized_url = jira_url.rstrip("/")
    registry = _load_registry()

    url_entry = registry.get(jira_type, {}).get(normalized_url, {})
    user_entry = url_entry.get("users", {}).get(username.lower(), {})
    return user_entry.get("projects", [])


def get_users_for_url(jira_url: str) -> List[str]:
    """
    Get the cached list of Jira users for a specific URL.
    Used for user dropdowns in confirm_predictions.
    Falls back to flat list if old format or URL not found.
    """
    normalized_url = jira_url.rstrip("/")

    if not os.path.exists(JIRA_USERS_FILE):
        return []

    try:
        with open(JIRA_USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    # New per-URL format
    if isinstance(data, dict):
        if normalized_url in data:
            return data[normalized_url]
        # Fallback: return legacy flat list if present
        return data.get("__legacy", [])

    # Old flat list format (backward compat)
    if isinstance(data, list):
        return data

    return []


def filter_files_by_user_projects(
    files: List[str],
    jira_url: str,
    username: str
) -> List[str]:
    """
    Filter a list of filenames (e.g. database JSON files) to only include
    those whose project prefix matches the user's accessible projects.

    Database files follow the pattern: PROJECTKEY_YYYYMMDD_HHMMSS.json
    """
    projects = get_user_projects(jira_url, username)
    if not projects:
        # If no projects found in registry, don't filter (graceful degradation)
        return files

    filtered = []
    for f in files:
        # Extract project key from filename (everything before first underscore)
        basename = os.path.basename(f)
        parts = basename.split("_")
        if parts:
            file_project = parts[0]
            if file_project in projects:
                filtered.append(f)

    return filtered


def get_all_registry_data() -> dict:
    """Return the full registry (for admin/debugging purposes)."""
    return _load_registry()
