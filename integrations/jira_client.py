import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Any, Tuple

import requests
from requests.auth import HTTPBasicAuth

from analysis.data_pre_analysis import get_target_fields_matrix
from config.constants import (
    DATABASES_FOLDER, PRIMITIVE_SCHEMA_TYPES, IFC_TARGET_FIELDS, IFC_FIELD_NAME,
    IFC_PREDICTIONS, IFC_VALUE, IFC_USER, IFC_TIME_STAMP, IFC_ISSUE_KEYS,
    DATABASES_SETTINGS_FOLDER, DEFAULT_FIELDS, JIRA_USERS_FILE, JIRA_COMPONENTS_PRIORITIES_FILE, IFC_TAGGED_ISSUE_KEYS
)
from utils_pkg.text_utils import extract_issue_key, extract_question_id_and_issue_key


# Helper function to chunk lists to avoid overly long parameters
def chunk_list(lst, chunk_size=50):
    """Split a list into chunks of specified size"""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


class ExportCancelled(Exception):
    """Raised when the user cancels a running Jira export."""
    pass


def _extract_text_from_adf(adf_node) -> str:
    """
    Recursively extract plain text from an ADF (Atlassian Document Format) structure.
    Jira Cloud API v3 returns description and other rich-text fields in ADF format.
    """
    if not isinstance(adf_node, dict):
        return str(adf_node) if adf_node else ""

    if adf_node.get("type") == "text":
        return adf_node.get("text", "")

    parts = []
    for child in adf_node.get("content", []):
        parts.append(_extract_text_from_adf(child))

    if adf_node.get("type") in ("paragraph", "heading", "bulletList", "orderedList", "listItem"):
        return "\n".join(parts)

    return "".join(parts)


# Reserved JQL words that need to be quoted
RESERVED_JQL_WORDS = {
    'access', 'and', 'or', 'not', 'in', 'is', 'order', 'by', 'from', 'to',
    'with', 'of', 'after', 'before', 'during', 'on', 'at', 'until'
}


def quote_jql_type(type_name):
    """Quote a JQL type name if it contains spaces or is a reserved word"""
    type_lower = type_name.lower()
    if " " in type_name or type_lower in RESERVED_JQL_WORDS:
        return f'"{type_name}"'
    return type_name


os.makedirs(DATABASES_FOLDER, exist_ok=True)
os.makedirs(DATABASES_SETTINGS_FOLDER, exist_ok=True)


def normalize_jira_url(url: str) -> str:
    """
    Normalize Jira base URL. For Jira Cloud (.atlassian.net), strip any context path
    (e.g., /jira) since Cloud REST API lives at the root domain.
    For Server/Data Center, keep the context path as-is.
    """
    url = url.rstrip("/")
    if ".atlassian.net" in url.lower():
        # Strip any path after the domain for Cloud (e.g., /jira, /jira/)
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return url


# Cache for the Epic Link custom field ID per Jira instance
_custom_field_id_cache: Dict[str, str] = {}


def resolve_custom_field_id(
        jira_base_url: str,
        auth: Tuple[str, str],
        custom_field: str
) -> str | None:
    jira_base_url = normalize_jira_url(jira_base_url)
    cache_key = jira_base_url.rstrip('/')
    if f"{cache_key}_{custom_field}" in _custom_field_id_cache:
        return _custom_field_id_cache[f"{cache_key}_{custom_field}"]

    url = f"{cache_key}/rest/api/latest/field"
    try:
        resp = requests.get(url, auth=auth, headers={"Content-Type": "application/json"}, timeout=20)
        if resp.ok:
            custom_fields = list(filter(lambda x: x["custom"], resp.json()))
            custom_field_names = list(map(lambda x: x["name"].lower(), custom_fields))
            custom_field_ids = list(map(lambda x: x["id"], custom_fields))
            lower_custom_field = custom_field.lower().replace('_', ' ')
            custom_fields_map = dict(zip(custom_field_names, custom_field_ids))
            field_id = custom_fields_map.get(lower_custom_field, custom_field)
            _custom_field_id_cache[f"{cache_key}_{custom_field}"] = field_id
            return field_id
    except Exception as e:
        print(f"[EXCEPTION] Failed to resolve '${custom_field}' field ID: {e}")

    return None


def resolve_epic_link_field_id(
        jira_base_url: str,
        auth: Tuple[str, str],
) -> str | None:
    """
    Discover the custom field ID for 'Epic Link' from the Jira instance.
    Results are cached per base URL to avoid repeated API calls.
    Returns the custom field ID (e.g. 'customfield_10014') or None if not found.
    """
    jira_base_url = normalize_jira_url(jira_base_url)
    cache_key = jira_base_url.rstrip('/')
    if cache_key in _custom_field_id_cache:
        return _custom_field_id_cache[cache_key]

    url = f"{cache_key}/rest/api/latest/field"
    try:
        resp = requests.get(url, auth=auth, headers={"Content-Type": "application/json"}, timeout=20)
        if resp.ok:
            for field in resp.json():
                if (field.get("name", "").lower() == "epic link"
                        and field.get("id", "").startswith("customfield_")):
                    field_id = field["id"]
                    _custom_field_id_cache[cache_key] = field_id
                    print(f"[INFO] Resolved Epic Link field ID: {field_id}")
                    return field_id
        print("[WARNING] Could not find 'Epic Link' custom field in Jira fields list")
    except Exception as e:
        print(f"[WARNING] Failed to resolve Epic Link field ID: {e}")

    return None


def export_jira_issues(
        jira_url,
        username,
        api_token,
        project_key,
        fields_to_include,
        issue_types,
        timestamp=None,
        is_open_source=False,
        custom_fields=None,
        include_comments=True,
        progress_callback=None,
        cancel_check=None,
        creation_date=None
):
    start_at = 0
    all_issues = []
    headers = {"Accept": "application/json"}
    jira_url = normalize_jira_url(jira_url)
    print(f"fields_to_include >>> {fields_to_include}")
    print(f"issue_types >>> {issue_types}")
    print(f"is_open_source >>> {is_open_source}")

    # Detect Jira Cloud vs Server - Cloud uses API v3, Server uses API v2
    is_cloud = ".atlassian.net" in jira_url.lower()
    api_version = "3" if is_cloud else "2"
    print(f"[DEBUG] Jira instance type: {'Cloud' if is_cloud else 'Server'}, API version: {api_version}")

    # For open source JIRA instances, no auth is needed
    auth = None if is_open_source else HTTPBasicAuth(username, api_token)
    try:
        print("[DEBUG] Starting issue type chunking")
        # Process issue types in chunks if they're too long
        issue_type_chunks = list(chunk_list(issue_types, 20)) if issue_types else [""]
        print(f"[DEBUG] Issue type chunks created: {len(issue_type_chunks)}")

        print("[DEBUG] Starting field chunking")
        # Process fields in chunks if they're too long
        field_chunks = list(chunk_list(fields_to_include, 50)) if fields_to_include else [["key"]]
    except Exception as e:
        print(f"[DEBUG] Error during chunking: {e}")
        import traceback
        traceback.print_exc()
        raise

    print(f"[DEBUG] About to start main loops")

    for issue_type_chunk in issue_type_chunks:
        print(f"[DEBUG] Processing issue type chunk: {issue_type_chunk[:5] if issue_type_chunk else 'EMPTY'}")
        issue_type_filter = ""
        if issue_type_chunk:
            # Use the new quoting function to handle reserved words and spaces
            quoted_types = [quote_jql_type(t) for t in issue_type_chunk]
            joined_types = ",".join(quoted_types)
            issue_type_filter = f" AND issuetype IN ({joined_types})"
            issue_type_filter += "" if creation_date is None else f' AND created >= "{creation_date}"'
            print(
                f"[DEBUG] Processing issue type chunk: {joined_types[:100]}{'...' if len(joined_types) > 100 else ''}")

        for field_chunk in field_chunks:
            print(f"[DEBUG] Processing field chunk of {len(field_chunk)} fields")

            start_at = 0  # Reset start_at for each field chunk (Server only)
            next_page_token = None  # Cloud pagination token
            chunk_issues = []
            fetched_count = 0  # Track total fetched for progress

            while True:
                if cancel_check and cancel_check():
                    raise ExportCancelled("Export cancelled by user")

                jql = f"project={project_key}{issue_type_filter}"
                fields_list = field_chunk

                print(f"[DEBUG] JQL: {jql[:200]}{'...' if len(jql) > 200 else ''}")
                print(f"[DEBUG] Fields count: {len(fields_list)}")

                try:
                    # executing rest api to get JIRA data
                    if is_cloud:
                        # Jira Cloud: Use /search/jql endpoint with GET + nextPageToken pagination
                        url = f"{jira_url}/rest/api/3/search/jql"
                        params = {
                            "jql": jql,
                            "maxResults": 100,
                            "fields": ",".join(fields_list)
                        }
                        # Use nextPageToken for pagination (startAt is ignored by this endpoint)
                        if next_page_token:
                            params["nextPageToken"] = next_page_token
                        print(
                            f"[DEBUG] Using Jira Cloud GET to /search/jql (token: {'yes' if next_page_token else 'first page'})")
                        response = requests.get(
                            url,
                            params=params,
                            headers=headers,
                            auth=auth,
                            timeout=30
                        )
                    else:
                        # Jira Server/Data Center: Use classic /search endpoint
                        url = f"{jira_url}/rest/api/2/search"
                        params = {
                            "jql": jql,
                            "startAt": start_at,
                            "maxResults": 100,
                            "fields": ",".join(fields_list)
                        }
                        total_url_length = len(url) + len(str(params))

                        if total_url_length > 2000:
                            print(f"[DEBUG] Using POST request (long URL: {total_url_length} chars)")
                            post_data = {
                                "jql": jql,
                                "startAt": start_at,
                                "maxResults": 100,
                                "fields": fields_list
                            }
                            response = requests.post(
                                url,
                                json=post_data,
                                headers=headers,
                                auth=auth,
                                timeout=30
                            )
                        else:
                            print(f"[DEBUG] Using GET request (URL length: {total_url_length} chars)")
                            response = requests.get(
                                url,
                                params=params,
                                headers=headers,
                                auth=auth,
                                timeout=30
                            )
                    if not response.ok:
                        print(f"[DEBUG] Response status: {response.status_code}")
                        print(f"[DEBUG] Response body: {response.text[:1000]}")
                    response.raise_for_status()
                    response_data = response.json()
                    print(f"[DEBUG] Response status: {response.status_code}")
                    print(
                        f"[DEBUG] Response data keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")
                except requests.exceptions.RequestException as e:
                    print(f"[DEBUG] Request failed: {e}")
                    raise Exception(f"Failed to connect to JIRA: {e}")

                data = response_data
                issues = data.get("issues", [])
                if not issues:
                    break

                fetched_count += len(issues)
                total_available = data.get("total", fetched_count)
                if progress_callback:
                    progress_callback(
                        phase="issues",
                        total=total_available,
                        fetched=fetched_count,
                        message=f"Fetching issues: {fetched_count}/{total_available}"
                    )

                for issue in issues:
                    fields = issue.get("fields", {})
                    issue_data = {}

                    # Always extract 'key' from top-level issue dict
                    issue_data["key"] = issue.get("key", "")

                    for field in field_chunk:
                        if field == "key":
                            continue  # Already extracted
                        if field == "issuelinks":
                            links = []
                            for link in fields.get("issuelinks", []):

                                link_type = ""
                                linked_issue = None

                                if (link.get("inwardIssue") is not None):
                                    link_type = link.get("type", {}).get("inward", "")
                                    linked_issue = link.get("inwardIssue")

                                if (link.get("outwardIssue") is not None):
                                    link_type = link.get("type", {}).get("outward", "")
                                    linked_issue = link.get("outwardIssue")

                                if linked_issue:
                                    links.append({
                                        "type": link_type.lower(),
                                        "key": linked_issue.get("key", "")
                                    })

                            issue_data["issuelinks"] = links
                            continue

                        val = fields.get(field, None)

                        # Handle ADF (Atlassian Document Format) for text fields like description
                        if isinstance(val, dict) and val.get("type") == "doc":
                            issue_data[field] = _extract_text_from_adf(val)
                        # Handle lists of dicts (e.g., components, fixVersions)
                        elif isinstance(val, list):
                            if val and isinstance(val[0], dict):
                                issue_data[field] = [v.get("name", v.get("value", "")) for v in val]
                            else:
                                issue_data[field] = val
                        # Handle single dicts (e.g., priority, parent, issuetype)
                        elif isinstance(val, dict):
                            issue_data[field] = val.get("name", val.get("value", val.get("key", "")))
                        else:
                            issue_data[field] = val

                    chunk_issues.append(issue_data)

                # Pagination: Cloud uses nextPageToken + isLast; Server uses startAt + total
                if is_cloud:
                    if data.get("isLast", False):
                        break
                    next_page_token = data.get("nextPageToken")
                    if not next_page_token:
                        # No more pages if token is absent
                        break
                else:
                    start_at += len(issues)
                    if "total" in data and start_at >= data["total"]:
                        break

            # Merge chunk issues with all issues, avoiding duplicates
            existing_keys = {issue["key"] for issue in all_issues}
            for issue in chunk_issues:
                if issue["key"] not in existing_keys:
                    all_issues.append(issue)
                    existing_keys.add(issue["key"])
                else:
                    # Merge fields for existing issue
                    existing_issue = next((i for i in all_issues if i["key"] == issue["key"]), None)
                    if existing_issue:
                        existing_issue.update(issue)

    if cancel_check and cancel_check():
        raise ExportCancelled("Export cancelled by user")

    # Fetch comments for all issues if requested
    comments_by_issue = {}
    if include_comments and all_issues:
        print(f"[DEBUG] Starting comment retrieval for {len(all_issues)} issues...")
        if progress_callback:
            progress_callback(phase="comments", total=len(all_issues), fetched=0,
                              message="Starting comment retrieval...")
        issue_keys = [issue["key"] for issue in all_issues]
        comments_by_issue = bulk_fetch_comments(jira_url, issue_keys, auth, is_open_source, include_comments,
                                                progress_callback=progress_callback, cancel_check=cancel_check)

        # Add comments to each issue
        for issue in all_issues:
            issue_key = issue["key"]
            issue["comments"] = comments_by_issue.get(issue_key, [])

        total_comments = sum(len(comments) for comments in comments_by_issue.values())
        print(f"[DEBUG] Retrieved {total_comments} total comments across {len(comments_by_issue)} issues")

    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"{project_key}_{timestamp}.json"
    filepath = os.path.join(DATABASES_FOLDER, filename)

    # Replace custom fields' IDs with Names
    # all_issues_ = [{custom_fields.get(k, k): v for k, v in d.items()} for d in all_issues]
    print("[DEBUG] custom_fields__:", custom_fields)
    all_issues_ = []
    for d in all_issues:
        item = {}
        for k, v in d.items():
            is_renamable = k in custom_fields and sum(
                1 for value in custom_fields.values() if value == custom_fields[k]) == 1
            item[custom_fields[k] if is_renamable else k] = v
        all_issues_.append(item)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(all_issues_, f, indent=2, ensure_ascii=False)

    # ---- Write settings file (adds project URL etc.) ----
    settings_filename = f"{project_key}_{timestamp}_settings.json"
    settings_path = os.path.join(DATABASES_SETTINGS_FOLDER, settings_filename)

    base_url = jira_url.rstrip("/")
    settings = {
        "projectKey": project_key,
        "jiraBaseUrl": base_url,
        "projectBrowseUrl": f"{base_url}/browse/",
        "exportedAt": timestamp,
        "totalIssues": len(all_issues),
        "includeComments": include_comments,
        "totalComments": sum(len(issue.get("comments", [])) for issue in all_issues) if include_comments else 0,
        "filters": {
            "issueTypes": issue_types or [],
            "fieldsIncluded": fields_to_include or []
        },
        "target_fields_matrix": get_target_fields_matrix(all_issues_)
    }

    try:
        with open(settings_path, "w", encoding="utf-8") as sf:
            json.dump(settings, sf, indent=2, ensure_ascii=False)
        print(f"Settings written to: {settings_path}")
    except OSError as e:
        print(f"Warning: could not write settings file: {e}")

    return filepath, len(all_issues)


def bulk_fetch_comments(jira_url, issue_keys, auth, is_open_source=False, include_comments=True, max_workers=10,
                        progress_callback=None, cancel_check=None):
    """
    Fetch comments for multiple issues in parallel with progress tracking.

    Args:
        jira_url: Base JIRA URL
        issue_keys: List of issue keys
        auth: Authentication tuple or None for open source
        is_open_source: Whether this is an open source JIRA instance
        include_comments: Whether to fetch comments (can be disabled for performance)
        max_workers: Maximum number of parallel requests (default 10)

    Returns:
        Dictionary mapping issue_key -> list of comments
    """
    if not include_comments:
        return {}

    comments_by_issue = {}
    total_issues = len(issue_keys)

    print(f"[DEBUG] Starting to fetch comments for {total_issues} issues (parallel, {max_workers} workers)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_issue_comments, jira_url, key, auth, is_open_source): key
            for key in issue_keys
        }

        for i, future in enumerate(as_completed(futures), 1):
            if cancel_check and cancel_check():
                for pending in futures:
                    pending.cancel()
                raise ExportCancelled("Export cancelled during comment fetch")

            issue_key = futures[future]
            try:
                comments_by_issue[issue_key] = future.result()
            except Exception as e:
                print(f"Warning: Failed to fetch comments for {issue_key}: {e}")
                comments_by_issue[issue_key] = []

            if progress_callback and (i % 5 == 0 or i == total_issues):
                progress_callback(phase="comments", total=total_issues, fetched=i,
                                  message=f"Fetching comments: {i}/{total_issues}")
            if i % 50 == 0 or i == total_issues:
                print(f"[DEBUG] Fetching comments: {i}/{total_issues} issues processed")

    print(f"[DEBUG] Completed fetching comments for {total_issues} issues")
    return comments_by_issue


def fetch_issue_comments(jira_url, issue_key, auth, is_open_source=False):
    """
    Fetch all comments for a single issue from JIRA API.

    Args:
        jira_url: Base JIRA URL
        issue_key: Issue key (e.g., 'BOOK-4589')
        auth: Authentication tuple or None for open source
        is_open_source: Whether this is an open source JIRA instance

    Returns:
        List of comment dictionaries with author, body, created, updated fields
    """
    headers = {"Accept": "application/json"}
    api_version = "3" if ".atlassian.net" in jira_url.lower() else "2"
    url = f"{jira_url.rstrip('/')}/rest/api/{api_version}/issue/{issue_key}/comment"
    params = {
        "startAt": 0,
        "maxResults": 100,
        "expand": "renderedBody"
    }

    all_comments = []

    while True:
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                auth=auth,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()

            comments = data.get("comments", [])
            if not comments:
                break

            for comment in comments:
                comment_data = {
                    "id": comment.get("id", ""),
                    "author": comment.get("author", {}).get("displayName", ""),
                    "body": comment.get("body", ""),
                    "created": comment.get("created", ""),
                    "updated": comment.get("updated", ""),
                    "renderedBody": comment.get("renderedBody", "")
                }
                all_comments.append(comment_data)

            params["startAt"] += len(comments)
            if params["startAt"] >= data.get("total", 0):
                break

        except requests.exceptions.RequestException as e:
            print(f"Warning: Failed to fetch comments for {issue_key}: {e}")
            break

    return all_comments


def bulk_update_issues(
        updates: List[Dict[str, Any]],
        jira_base_url: str,
        auth: Tuple[str, str],
        user, time_stamp
) -> List[Dict[str, Any]]:
    """
    Apply a list of Jira issue field updates via the REST API.
    """
    jira_base_url = normalize_jira_url(jira_base_url)
    headers = {
        "Content-Type": "application/json",
        "X-Atlassian-Token": "no-check"  # Bypass CSRF protection on Jira Server
    }
    results = []
    # Detect Jira Cloud vs Server
    is_cloud = ".atlassian.net" in jira_base_url.lower()
    api_version = "3" if is_cloud else "2"
    # Track successful updates per issue key for consolidated comments
    successful_updates_by_issue: Dict[str, List[Tuple[str, str]]] = {}

    def stringify_value_for_comment(value: Any) -> str:
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    kvs = ", ".join(f"{k}={v}" for k, v in item.items())
                    parts.append(f"{{{kvs}}}")
                else:
                    parts.append(str(item))
            return "[" + ", ".join(parts) + "]"
        elif isinstance(value, dict):
            kvs = ", ".join(f"{k}={v}" for k, v in value.items())
            return "{" + kvs + "}"
        else:
            return str(value)

    for upd in updates:
        issue_key = upd["issuekey"]
        question_id = upd["question_id"]
        field = upd["field"]
        value = upd["value"]
        field_name = upd["field_name"]

        is_team_field = field_name.lower() in ["team", "devteam"]
        url = f"{jira_base_url.rstrip('/')}/rest/api/{api_version}/issue/{issue_key}"
        value = {"value": value["name"] if isinstance(value, dict) else value} if is_team_field else value
        payload = {"fields": {field: value}}
        print(f"  → PUT {url} | field={field} | value={value!r}")

        try:
            response = requests.put(url, json=payload, auth=auth, headers=headers, timeout=30)
            # If PUT returns 405 (Method Not Allowed), retry with POST + method override
            # This handles environments where a reverse proxy blocks PUT requests
            if response.status_code == 405:
                print(f"  → PUT returned 405, retrying with POST + X-HTTP-Method-Override")
                override_headers = {**headers, "X-HTTP-Method-Override": "PUT"}
                response = requests.post(url, json=payload, auth=auth, headers=override_headers, timeout=30)
        except Exception as e:
            print(f"  → Failed to send update to {issue_key}: {e}")
            results.append({
                "issuekey": issue_key,
                "question_id": question_id,
                "field": field,
                "field_name": field_name,
                "status": None,
                "response": f"request failed: {e}",
                "value": upd["value"]["name"]
            })
            continue

        # Interpret response
        if response.ok:
            print(f"  → Success: {issue_key} updated (HTTP {response.status_code})")
        else:
            print(f"  → Error: {issue_key} returned HTTP {response.status_code}: {response.text[:500]}")

        try:
            resp_json = response.json()
        except ValueError:
            resp_json = response.text

        # Track successful updates for consolidated comment later
        if response.status_code in (200, 204):
            formatted_value_str = stringify_value_for_comment(value)
            if issue_key not in successful_updates_by_issue:
                successful_updates_by_issue[issue_key] = []
            successful_updates_by_issue[issue_key].append((field, formatted_value_str))

        results.append({
            "issuekey": issue_key,
            "question_id": question_id,
            "field": field,
            "field_name": field_name,
            "status": response.status_code,
            "response": resp_json,
            "value": upd["value"] if not isinstance(upd["value"], dict) else upd["value"].get("name", None)
        })

    # Post a single consolidated comment per issue key
    for issue_key, field_updates in successful_updates_by_issue.items():
        field_lines = "; ".join(
            f"field '{fld}' to '{val}'" for fld, val in field_updates
        )
        if time_stamp:
            comment_body = (
                f"JFIP tool (user: {user}, timestamp: {time_stamp}) "
                f"updated {field_lines}."
            )
        else:
            comment_body = (
                f"JFIP tool (user: {user}) updated {field_lines}."
            )

        comment_url = f"{jira_base_url.rstrip('/')}/rest/api/{api_version}/issue/{issue_key}/comment"
        # Jira Cloud API v3 requires ADF (Atlassian Document Format) for comment body
        if api_version == "3":
            comment_payload = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": comment_body}
                            ]
                        }
                    ]
                }
            }
        else:
            comment_payload = {"body": comment_body}

        try:
            comment_resp = requests.post(comment_url, json=comment_payload, auth=auth, headers=headers, timeout=20)
            if comment_resp.ok:
                print(f"    → Comment added to {issue_key}: {comment_body!r}")
            else:
                print(
                    f"    → Failed to add comment to {issue_key}: HTTP {comment_resp.status_code}: {comment_resp.text}")
        except Exception as e:
            print(f"    → Exception while adding comment to {issue_key}: {e}")

    return results


def format_value_for_jira(field_name: str, raw_value: Any) -> Any:
    """
    Heuristic shaping of raw_value into the expected Jira REST shape for common fields.
    """
    single_name_object_fields = {"priority", "issuetype", "resolution", "security"}
    list_of_name_object_fields = {"components", "fixVersions", "versions"}

    # List-of-dicts fields (e.g., components, fixVersions)
    if field_name in list_of_name_object_fields:
        if isinstance(raw_value, list) and all(isinstance(i, dict) for i in raw_value):
            return raw_value  # already shaped
        values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
        return [{"name": v} for v in values]

    # Single object with name
    if field_name in single_name_object_fields:
        if isinstance(raw_value, dict):
            return raw_value
        return {"name": raw_value}

    # Labels (list of strings)
    if field_name == "labels":
        if isinstance(raw_value, list):
            return raw_value
        if isinstance(raw_value, str):
            return [l.strip() for l in raw_value.replace(",", " ").split()]
        return [str(raw_value)]

    # Fallback: pass through
    return raw_value


def fetch_issue_fields(
        jira_base_url: str,
        issue_key: str,
        fields: List[str],
        auth: Tuple[str, str],
        field_name_map: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """
    Fetch specific fields from a Jira issue.
    field_name_map: optional dict mapping friendly names to Jira API field IDs,
                    e.g. {"epic_link": "customfield_10014"}.
    Returns a dict with field names (using friendly names if mapped) and their current values.
    """
    jira_base_url = normalize_jira_url(jira_base_url)
    # Translate friendly names → Jira API field IDs for the request
    reverse_map: Dict[str, str] = {}
    api_fields: List[str] = []
    for f in fields:
        if field_name_map and f in field_name_map:
            api_name = field_name_map[f]
            reverse_map[api_name] = f
            api_fields.append(api_name)
        else:
            api_fields.append(f)

    fields_param = ",".join(api_fields)
    api_version = "3" if ".atlassian.net" in jira_base_url.lower() else "2"
    url = f"{jira_base_url.rstrip('/')}/rest/api/{api_version}/issue/{issue_key}?fields={fields_param}"
    try:
        resp = requests.get(url, auth=auth, headers={"Content-Type": "application/json"}, timeout=20)
        if not resp.ok:
            print(f"  → Warning: failed to fetch fields for {issue_key}: HTTP {resp.status_code}")
            return {}
        data = resp.json()
        raw_fields = data.get("fields", {}) or {}

        # Translate Jira API field IDs back to friendly names in the result
        if reverse_map:
            result: Dict[str, Any] = {}
            for k, v in raw_fields.items():
                result[reverse_map.get(k, k)] = v
            return result
        return raw_fields
    except Exception as e:
        print(f"  → Exception fetching fields for {issue_key}: {e}")
        return {}


def fetch_editmeta_fields(
        jira_base_url: str,
        issue_key: str,
        auth: Tuple[str, str],
) -> Dict[str, Any]:
    """
    Retrieve the editmeta.fields block for a given issue (contains schema info).
    Returns a mapping of field_key -> field metadata (including 'schema').
    """
    jira_base_url = normalize_jira_url(jira_base_url)
    api_version = "3" if ".atlassian.net" in jira_base_url.lower() else "2"
    url = f"{jira_base_url.rstrip('/')}/rest/api/{api_version}/issue/{issue_key}/editmeta"
    try:
        resp = requests.get(url, auth=auth, headers={"Content-Type": "application/json"}, timeout=20)
        if not resp.ok:
            print(f"  → Warning: failed to fetch editmeta for {issue_key}: HTTP {resp.status_code}")
            return {}
        data = resp.json()
        return data.get("fields", {}) or {}
    except Exception as e:
        print(f"  → Exception fetching editmeta for {issue_key}: {e}")
        return {}


def shape_value_using_schema(field_name: str, raw_value: Any, fields_meta: Dict[str, Any]) -> Any:
    """
    Shape raw_value into the expected Jira REST shape based solely on editmeta schema,
    without hardcoding specific field names.

    Fallback: return raw_value unchanged if metadata is missing or unrecognized.
    """
    field_meta = fields_meta.get(field_name)
    if not field_meta:
        return raw_value  # unknown field, give raw

    schema = field_meta.get("schema", {}) or {}
    schema_type = schema.get("type", "")
    schema_items = schema.get("items", "")

    # ---- Array case ----
    if schema_type == "array":
        # If raw_value is a comma-separated string, split into individual values
        if isinstance(raw_value, str) and "," in raw_value:
            raw_value = [v.strip() for v in raw_value.split(",") if v.strip()]

        # Array of primitives (labels, simple lists)
        if isinstance(schema_items, str) and schema_items.lower() in PRIMITIVE_SCHEMA_TYPES:
            if isinstance(raw_value, (list, tuple)):
                return [v for v in raw_value]
            else:
                return [raw_value]

        # Array of complex objects: assume list of {"name": ...}
        def wrap(v):
            if isinstance(v, dict):
                return v
            return {"name": v}

        if isinstance(raw_value, (list, tuple)):
            return [wrap(v) for v in raw_value]
        else:
            return [wrap(raw_value)]

    # ---- Non-array scalar ----
    if isinstance(schema_type, str) and schema_type.lower() in PRIMITIVE_SCHEMA_TYPES:
        return raw_value  # primitive scalar, keep as-is

    # ---- Object-like: assume expects an object with "name" if not already dict ----
    if isinstance(raw_value, dict):
        return raw_value
    return {"name": raw_value}


def apply_prediction_json_to_jira(
        prediction_json: Dict[str, Any],
        jira_base_url: str,
        auth: Tuple[str, str],
) -> List[Dict[str, Any]]:
    """
    Transforms the structured prediction JSON into per-issue updates for any field
    by introspecting Jira editmeta, then delegates to bulk_update_issues.
    """
    jira_base_url = normalize_jira_url(jira_base_url)
    updates: List[Dict[str, Any]] = []
    user = prediction_json.get(IFC_USER, "unknown")
    time_stamp = prediction_json.get(IFC_TIME_STAMP)

    # Resolve epic_link custom field ID if any target field uses it
    epic_link_field_id = None
    for target in prediction_json.get(IFC_TARGET_FIELDS, []):
        if target[IFC_FIELD_NAME] == "epic_link":
            epic_link_field_id = resolve_epic_link_field_id(jira_base_url, auth)
            break

    # cache per-issue editmeta so we don't refetch repeatedly
    issue_schemas: Dict[str, Dict[str, Any]] = {}

    for target in prediction_json.get(IFC_TARGET_FIELDS, []):
        field_name = target[IFC_FIELD_NAME]

        # Translate custom field to the actual Jira custom field ID
        jira_field_name = resolve_custom_field_id(jira_base_url, auth, field_name)

        for pred in target.get(IFC_PREDICTIONS, []):
            raw_value = pred[IFC_VALUE]
            # issue_keys_list = pred.get(IFC_ISSUE_KEYS, [])
            tagged_issue_keys_list = pred.get(IFC_TAGGED_ISSUE_KEYS, [])
            print("tagged_issue_keys_list:", tagged_issue_keys_list)

            for issue_key_quest_id_string in tagged_issue_keys_list:
                # issue_key = extract_issue_key(issue_key_string)
                issue_key = issue_key_quest_id_string.split("_q")[0]
                question_id = f"q{issue_key_quest_id_string.split('_q')[1]}"
                print("issue_key, question_id:", issue_key, question_id)
                if issue_key not in issue_schemas:
                    issue_schemas[issue_key] = fetch_editmeta_fields(jira_base_url, issue_key, auth)

                # Epic Link value is a plain string (the epic's key); bypass editmeta shaping
                is_epic_link = field_name == "epic_link"
                if is_epic_link:
                    shaped_value = raw_value
                else:
                    shaped_value = shape_value_using_schema(jira_field_name, raw_value, issue_schemas[issue_key])

                updates.append({
                    "issuekey": issue_key,
                    "field": jira_field_name,
                    "field_name": field_name,
                    "value": shaped_value,
                    "user": user,
                    "time_stamp": time_stamp,
                    "question_id": question_id
                })

    return bulk_update_issues(updates, jira_base_url, auth, user, time_stamp)


# -------- Jira metadata fetching functions --------

def fetch_jira_fields(jira_url: str, auth) -> list | None:
    """
    Fetch all fields from Jira and filter out default fields.
    Returns list of dicts with 'id' and 'name' keys, or None on failure.
    """
    jira_url = normalize_jira_url(jira_url)
    url = f"{jira_url.rstrip('/')}/rest/api/latest/field"
    print(f"[DEBUG] Fetching fields from: {url}")
    response = requests.get(url, auth=auth)
    print(f"[DEBUG] Fields response status: {response.status_code}")

    if not response.ok:
        print(f"[DEBUG] Fields error: {response.text[:500]}")
        return None

    raw_fields = response.json()
    print(f"[DEBUG] Raw fields count: {len(raw_fields)}")

    fields = sorted(raw_fields, key=lambda f: f.get("name", "").lower())
    result = [
        {"id": f["id"], "name": f["name"]}
        for f in fields
        if f["id"] not in DEFAULT_FIELDS
    ]
    print(f"[DEBUG] Filtered fields count: {len(result)}")
    return result


def extract_custom_fields_mapping(all_fields: list) -> dict:
    """
    Extract custom fields (customfield_*) and create ID->name mapping.
    Returns dict mapping field ID to normalized field name.
    """
    custom_fields = [f for f in all_fields if f["id"].startswith("customfield_")]
    mapping = {f["id"]: f["name"].replace(' ', '_').lower() for f in custom_fields}
    print("[DEBUG] custom_fields_mapping:", mapping)
    return mapping


def fetch_projects(jira_url: str, auth, is_open_source: bool = False, username: str = "") -> list:
    """
    Fetch project keys from Jira.
    For open source instances, parses comma-separated project keys from username field.
    Handles both Jira Cloud and Jira Server/Data Center.
    """
    if is_open_source and username:
        return sorted([p.strip() for p in username.split(",") if p.strip()])

    base_url = jira_url.rstrip('/')

    # Try /rest/api/3/project first (Jira Cloud returns array)
    url = f"{base_url}/rest/api/3/project"
    print(f"[DEBUG] Fetching projects from: {url}")
    print(f"[DEBUG] Auth type: {type(auth)}, username: {auth.username if auth else 'None'}")
    resp = requests.get(url, auth=auth)
    print(f"[DEBUG] Projects response status: {resp.status_code}")
    if not resp.ok:
        print(f"[DEBUG] Projects error response: {resp.text[:500]}")

    if resp.ok:
        data = resp.json()
        if isinstance(data, list):
            projects = [p["key"] for p in data]
            print(f"[DEBUG] Fetched {len(projects)} projects from Jira API v3")
            return sorted(projects)
        elif isinstance(data, dict) and "values" in data:
            projects = [p["key"] for p in data["values"]]
            print(f"[DEBUG] Fetched {len(projects)} projects from Jira API v3 (paginated)")
            return sorted(projects)

    # Fallback to /rest/api/latest/project
    url = f"{base_url}/rest/api/latest/project"
    print(f"[DEBUG] Fallback: Fetching projects from: {url}")
    resp = requests.get(url, auth=auth)

    if resp.ok:
        data = resp.json()
        if isinstance(data, list):
            projects = [p["key"] for p in data]
        elif isinstance(data, dict) and "values" in data:
            projects = [p["key"] for p in data["values"]]
        else:
            print(f"[WARNING] Unexpected projects response format: {type(data)}")
            projects = []
        print(f"[DEBUG] Fetched {len(projects)} projects from Jira API (fallback)")
        return sorted(projects)

    print(f"[WARNING] Failed to fetch projects: {resp.status_code} - {resp.text[:200]}")
    return []


def fetch_users_cloud(jira_url: str, auth) -> list | None:
    """
    Fetch users from Jira Cloud API v3.
    Returns list of formatted user strings, or None if endpoint not available.
    """
    url = f"{jira_url.rstrip('/')}/rest/api/3/users/search?query=&maxResults=1000"
    resp = requests.get(url, auth=auth)

    if not resp.ok:
        return None

    users = []
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
    return users


def fetch_users_server(jira_url: str, auth) -> list:
    """
    Fetch users from Jira Server/Data Center API.
    Returns list of formatted user strings.
    """
    url = f"{jira_url.rstrip('/')}/rest/api/latest/user/search?username=.&includeInactive=false"
    resp = requests.get(url, auth=auth)

    if not resp.ok:
        return []

    users = []
    for u in resp.json():
        name = u.get("name", u.get("displayName", ""))
        email = u.get("emailAddress", "")

        if email:
            users.append(f"{name} [{email}]")
        else:
            users.append(name)
    return users


def fetch_users(jira_url: str, auth, save_to_file: bool = True) -> list:
    """
    Fetch users from Jira, trying Cloud API first, then falling back to Server API.
    Optionally saves results to JIRA_USERS_FILE.
    """
    # Try Cloud endpoint first
    users = fetch_users_cloud(jira_url, auth)

    # Fallback to Server endpoint if Cloud failed
    if users is None:
        users = fetch_users_server(jira_url, auth)

    if save_to_file:
        with open(JIRA_USERS_FILE, "w", encoding="utf-8") as outfile:
            json.dump(users, outfile, indent=4, ensure_ascii=False)

    return users


def fetch_components_for_projects(jira_url: str, auth, projects: list) -> dict:
    """
    Fetch components for each project.
    Returns dict mapping project key to list of component names.
    """
    components = {}
    for project in projects:
        url = f"{jira_url.rstrip('/')}/rest/api/latest/project/{project}/components"
        resp = requests.get(url, auth=auth)

        if resp.ok:
            components[project] = [c["name"] for c in resp.json()]
        else:
            print(f"[WARNING] Failed to fetch components for {project}: {resp.status_code}")
            components[project] = []

    return components


def fetch_priorities(jira_url: str, auth) -> list:
    """
    Fetch priority values from Jira.
    Returns list of priority names.
    """
    url = f"{jira_url.rstrip('/')}/rest/api/latest/priority"
    resp = requests.get(url, auth=auth)

    if resp.ok:
        return [p["name"] for p in resp.json()]

    print(f"[WARNING] Failed to fetch priorities: {resp.status_code}")
    return []


def fetch_labels(jira_url: str, auth) -> list:
    """
    Fetch labels from Jira.
    Note: /rest/api/latest/label may not exist on Jira Cloud.
    Returns list of label names, or empty list if not available.
    """
    url = f"{jira_url.rstrip('/')}/rest/api/latest/label"
    resp = requests.get(url, auth=auth)

    if not resp.ok:
        print(
            f"[INFO] Labels endpoint not available (status {resp.status_code}) - labels will be extracted from issues")
        return []

    label_data = resp.json()

    # Handle different response formats
    if isinstance(label_data, list):
        return [x.get("name", x) if isinstance(x, dict) else x for x in label_data]
    elif isinstance(label_data, dict) and "values" in label_data:
        return label_data["values"]

    return []


def fetch_components_priorities_labels(jira_url: str, auth, projects: list, save_to_file: bool = True) -> dict:
    """
    Fetch components, priorities, and labels from Jira.
    Optionally saves results to JIRA_COMPONENTS_PRIORITIES_FILE.
    Returns the combined dict.
    """
    data = fetch_components_for_projects(jira_url, auth, projects)
    data["priorities"] = fetch_priorities(jira_url, auth)
    data["labels"] = fetch_labels(jira_url, auth)

    if save_to_file:
        with open(JIRA_COMPONENTS_PRIORITIES_FILE, "w", encoding="utf-8") as outfile:
            json.dump(data, outfile, indent=4, ensure_ascii=False)

    return data


def fetch_issue_types(jira_url: str, auth) -> list:
    """
    Fetch issue types from Jira.
    Returns sorted list of unique issue type names.
    """
    url = f"{jira_url.rstrip('/')}/rest/api/latest/issuetype"
    resp = requests.get(url, auth=auth)

    if resp.ok:
        # Use set() to deduplicate - Jira Cloud returns duplicates across schemes
        return sorted(set(it["name"] for it in resp.json()))

    print(f"[WARNING] Failed to fetch issue types: {resp.status_code}")
    return []


# -------- example usage --------
if __name__ == "__main__":
    sample_input = {
        "time_stamp": "20250730_162831",
        "user": "autogen",
        "target_fields": [
            {
                "field_name": "components",
                "predictions": [
                    {
                        "value": "Component 02",
                        "issue_keys": [
                            "J01-5: My First Story 01"
                        ],
                        "keywords": ["def", "cant", "paste", "object", "e"]
                    }
                ]
            },
            {
                "field_name": "fixVersions",
                "predictions": [
                    {
                        "value": "JP_Version_01",
                        "issue_keys": [
                            "J01-6: My First Story 01"
                        ],
                        "keywords": ["def", "cant", "paste", "object", "e"]
                    }
                ]
            }
        ]
    }

    jira_url = "http://192.168.10.172:8080"  # replace with your Jira base URL
    credentials = ("Armando", "Armando")  # replace with real credentials

    results = apply_prediction_json_to_jira(sample_input, jira_url, credentials)
    for r in results:
        print(f"Issue {r['issuekey']}: status={r['status']} response={r['response']}")
