"""
Jira routes:
  /export_jira, /fields, /generate, /jira_viewer, /show_jira_viewer,
  /validate_push_issues, /push_to_jira
"""
import json
import os
import traceback
import threading
from copy import deepcopy
from datetime import datetime, date
from pathlib import Path

import requests
from flask import Blueprint, request, jsonify, render_template, flash, redirect, session
from requests.auth import HTTPBasicAuth

import utils_pkg as utils
from analysis.data_pre_analysis import get_predictable_fields, get_target_fields_matrix_per_project, \
    get_saved_target_fields_matrix_per_project, get_best_performance_per_project
from auth.user_registry import filter_files_by_user_projects, add_project_to_registry
from integrations.jira_client import (
    export_jira_issues, apply_prediction_json_to_jira, fetch_issue_fields,
    fetch_jira_fields, extract_custom_fields_mapping, fetch_projects,
    fetch_users, fetch_components_priorities_labels, fetch_issue_types,
    normalize_jira_url, resolve_custom_field_id, ExportCancelled
)
from nlp.centroid_manager import get_target_field_possible_values
from config.constants import (
    DEFAULT_FIELDS, DATABASES_FOLDER, ITERATION_FOLDER, CFG_INPUT_FILE, BASE_DIR,
    JIRA_COMPONENTS_PRIORITIES_FILE, DATABASES_SETTINGS_FOLDER, INFERABILITY_ANALYSIS
)
from services.iteration_service import remove_files_with_string
from web.routes.iteration_routes import _filter_out_sent_items
from web.shared_state import jira_export_progress

bp = Blueprint("jira", __name__)


# ---- helper functions (used by validate/push routes) ----

def transform_consolidated_to_jira_format(consolidated_data: dict, user: str) -> dict:
    """
    Transform consolidated file format to the format expected by apply_prediction_json_to_jira().
    Deduplicates issue keys per (field, value) pair to avoid duplicate updates.
    """
    # Group by (field_name, value) to deduplicate issue keys
    field_value_issues: dict[tuple, set] = {}

    for issue_type, predictions in consolidated_data.get("predictions_by_issuetype", {}).items():
        for pred in predictions:
            field_name = pred.get("field")
            value = pred.get("new_value")
            issue_keys = pred.get("issue_keys", [])
            tagged_issue_keys_set = pred.get("tagged_issue_keys_set", [])

            if not field_name or not value or not issue_keys:
                continue

            key = (field_name, value)
            if key not in field_value_issues:
                field_value_issues[key] = set()
            # field_value_issues[key].update(issue_keys)
            field_value_issues[key].update(tagged_issue_keys_set)

    # Build predictions_by_field from deduplicated data
    predictions_by_field = {}
    for (field_name, value), tagged_issue_keys_set in field_value_issues.items():
        if field_name not in predictions_by_field:
            predictions_by_field[field_name] = []
        issue_keys_set = [issue_key.split('_')[0] for issue_key in  tagged_issue_keys_set]
        predictions_by_field[field_name].append({
            "value": value,
            "issue_keys": list(issue_keys_set),
            "tagged_issue_keys": list(tagged_issue_keys_set)
        })

    target_fields = [
        {"field_name": field_name, "predictions": preds}
        for field_name, preds in predictions_by_field.items()
    ]

    return {
        "time_stamp": consolidated_data.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")),
        "user": user,
        "target_fields": target_fields
    }


def _get_description_lookup(db_path: str) -> dict:
    """
    Loads the database JSON file and creates a lookup dictionary mapping issue key to description.
    """
    if not db_path:
        return {}
    # Resolve relative paths against project BASE_DIR
    if not os.path.isabs(db_path):
        db_path = os.path.join(BASE_DIR, db_path)
    if not os.path.exists(db_path):
        return {}

    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            issues = json.load(f)

        lookup = {}
        for issue in issues:
            key = issue.get("key", "")
            description = issue.get("description", "") or ""
            if key:
                lookup[key] = description
        return lookup
    except Exception as e:
        print(f"Error loading database for description lookup: {e}")
        return {}


def _normalize_description(desc) -> str:
    """
    Normalize a description value for comparison.
    Handles None, strings, ADF (Atlassian Document Format) dicts, and strips whitespace.
    """
    if desc is None:
        return ""
    # Jira Cloud API v3 returns description as ADF (dict with 'type': 'doc')
    if isinstance(desc, dict):
        # Extract plain text from ADF content
        return _extract_text_from_adf(desc).strip()
    if isinstance(desc, str):
        return desc.strip()
    return str(desc).strip()


def _extract_text_from_adf(adf_node) -> str:
    """
    Recursively extract plain text from an ADF (Atlassian Document Format) structure.
    """
    if not isinstance(adf_node, dict):
        return str(adf_node) if adf_node else ""

    # Text node
    if adf_node.get("type") == "text":
        return adf_node.get("text", "")

    # Recurse into content
    parts = []
    for child in adf_node.get("content", []):
        parts.append(_extract_text_from_adf(child))

    # Add newline for block-level elements
    if adf_node.get("type") in ("paragraph", "heading", "bulletList", "orderedList", "listItem"):
        return "\n".join(parts)

    return "".join(parts)


def _descriptions_differ(local_desc: str, jira_desc) -> bool:
    """
    Compare local DB description with Jira description.
    Returns True if they differ (meaning description was changed in Jira).
    """
    local_normalized = _normalize_description(local_desc)
    jira_normalized = _normalize_description(jira_desc)
    return local_normalized != jira_normalized


def _extract_field_display_value(field_value) -> str:
    """
    Extract a display-friendly string from a Jira field value.
    Handles lists of dicts, single dicts, and primitives.
    """
    if field_value is None:
        return ""
    if isinstance(field_value, list):
        if not field_value:
            return ""
        parts = []
        for item in field_value:
            if isinstance(item, dict):
                parts.append(item.get("name", item.get("value", str(item))))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    if isinstance(field_value, dict):
        return field_value.get("name", field_value.get("value", str(field_value)))
    return str(field_value)


def _is_field_empty(field_value) -> bool:
    """Check if a Jira field value is considered empty."""
    if field_value is None:
        return True
    if isinstance(field_value, list) and len(field_value) == 0:
        return True
    if isinstance(field_value, str) and field_value.strip() == "":
        return True
    return False

def _filter_non_empty_fields(consolidated_data: dict, jira_url: str, auth: tuple) -> dict:
    """
    Filter out predictions where:
    1. The target field is no longer empty in Jira
    2. The prediction has an ignore flag set (from description change or field populated)
    Returns a modified consolidated_data with only valid predictions.
    """
    # Get ignore flags from consolidated data
    ignore_flags = consolidated_data.get("ignore_flags", {})

    # Collect all unique (issue_key, field) pairs
    issue_field_map = {}  # {issue_key: set(fields)}

    for issue_type, predictions in consolidated_data.get("predictions_by_issuetype", {}).items():
        for pred in predictions:
            field_name = pred.get("field")
            for issue_key in pred.get("issue_keys", []):
                clean_key = issue_key.split(":")[0].strip() if ":" in issue_key else issue_key.strip()
                if clean_key not in issue_field_map:
                    issue_field_map[clean_key] = set()
                issue_field_map[clean_key].add(field_name)

    # Query Jira for field values
    non_empty_fields = {}  # {issue_key: set(non_empty_fields)}
    all_fields = set()
    for fields_set in issue_field_map.values():
        all_fields.update(fields_set)

    for issue_key in issue_field_map.keys():
        current_fields = fetch_issue_fields(jira_url, issue_key, list(all_fields), auth)
        non_empty = set()
        for field_name in issue_field_map[issue_key]:
            if not _is_field_empty(current_fields.get(field_name)):
                non_empty.add(field_name)
        if non_empty:
            non_empty_fields[issue_key] = non_empty

    # Filter predictions
    filtered_data = deepcopy(consolidated_data)
    filtered_predictions_by_issuetype = {}

    for issue_type, predictions in filtered_data.get("predictions_by_issuetype", {}).items():
        filtered_preds = []
        for pred in predictions:
            field_name = pred.get("field")
            # Filter issue keys that are still valid
            valid_keys = []
            for issue_key in pred.get("issue_keys", []):
                clean_key = issue_key.split(":")[0].strip() if ":" in issue_key else issue_key.strip()
                flag_key = f"{clean_key}|{field_name}"

                # Check if this issue+field has an ignore flag
                if flag_key in ignore_flags and ignore_flags[flag_key].get("ignored", False):
                    continue  # Skip this issue key - it's flagged to be ignored

                # Check if field is non-empty in Jira
                if clean_key in non_empty_fields and field_name in non_empty_fields[clean_key]:
                    continue  # Skip - field already populated

                valid_keys.append(issue_key)

            if valid_keys:
                filtered_pred = deepcopy(pred)
                filtered_pred["issue_keys"] = valid_keys
                filtered_preds.append(filtered_pred)

        if filtered_preds:
            filtered_predictions_by_issuetype[issue_type] = filtered_preds

    filtered_data["predictions_by_issuetype"] = filtered_predictions_by_issuetype
    return filtered_data


# ---- route handlers ----

@bp.route("/export_jira")
def export_jira():
    return render_template("export_jira.html")


@bp.route("/fields", methods=["POST"])
def fetch_fields():
    """
    Fetch Jira metadata (fields, projects, users, components, priorities, labels, issue types).
    Handles both Jira Cloud and Jira Server/Data Center.
    """
    jira_url = normalize_jira_url(request.form["jira_url"])
    username = request.form.get("username", "")
    api_token = request.form.get("api_token", "")
    is_open_source = request.form.get("open_source", "false") == "true"

    # Set up authentication
    auth = None if is_open_source else HTTPBasicAuth(username, api_token)

    # Detect Cloud vs Server for API version
    is_cloud = ".atlassian.net" in jira_url.lower()
    api_version = "3" if is_cloud else "2"

    # Verify credentials first (skip for open source)
    if not is_open_source:
        verify_url = f"{jira_url.rstrip('/')}/rest/api/{api_version}/myself"
        verify_resp = requests.get(verify_url, auth=auth)
        print(f"[DEBUG] Credential verification ({('Cloud' if is_cloud else 'Server')} API v{api_version}): {verify_resp.status_code}")
        if not verify_resp.ok:
            error_msg = f"Authentication failed (status {verify_resp.status_code}). Please verify your API token is valid."
            print(f"[ERROR] {error_msg}")
            print(f"[DEBUG] Response: {verify_resp.text[:300]}")
            return render_template("export_jira.html", error=error_msg)
        else:
            try:
                user_info = verify_resp.json()
                print(f"[DEBUG] Authenticated as: {user_info.get('displayName', 'Unknown')} ({user_info.get('emailAddress', 'no email')})")
            except Exception:
                print(f"[DEBUG] Credential verification OK but response not JSON: {verify_resp.text[:200]}")

    # Fetch fields (from jira_client)
    all_fields = fetch_jira_fields(jira_url, auth)
    if all_fields is None:
        return render_template("export_jira.html", error="Failed to fetch fields from JIRA.")

    # Extract custom fields mapping (from jira_client)
    custom_fields_dict = extract_custom_fields_mapping(all_fields)

    # Fetch projects (from jira_client)
    all_projects = fetch_projects(jira_url, auth, is_open_source, username)

    # Fetch users - skip for open source (from jira_client)
    if not is_open_source:
        fetch_users(jira_url, auth)

    # Fetch components, priorities, labels - skip for open source (from jira_client)
    if not is_open_source:
        fetch_components_priorities_labels(jira_url, auth, all_projects)

    # Fetch issue types (from jira_client)
    all_issue_types = fetch_issue_types(jira_url, auth)

    return render_template(
        "export_jira.html",
        all_fields=all_fields,
        custom_fields=custom_fields_dict,
        jira_url=jira_url,
        username=username,
        api_token=api_token,
        project_keys=all_projects,
        issue_types=all_issue_types,
        open_source="true" if is_open_source else "false"
    )

@bp.route("/generate", methods=["POST"])
def generate():
    # try:
    jira_url = request.form["jira_url"]
    username = request.form.get("username", "")
    api_token = request.form.get("api_token", "")
    project_key = request.form["project_key"]
    selected_fields = request.form.getlist("fields")
    include_comments = "comment" in selected_fields
    selected_fields = [f for f in selected_fields if f != "comment"]
    issue_types = request.form.getlist("issuetype")
    is_open_source = request.form.get("open_source", "false") == "true"
    custom_fields = request.args.get("custom_fields")

    # Store export credentials in session so push_to_jira uses the same creds
    if not is_open_source:
        session["jira_url"] = normalize_jira_url(jira_url)
        session["jira_username"] = username
        session["jira_password"] = api_token

    if is_open_source:
        # For open source projects, handle URL-encoded custom fields with special characters
        try:
            import urllib.parse
            custom_fields = json.loads(urllib.parse.unquote(custom_fields))
        except (json.JSONDecodeError, TypeError):
            # Fallback: try simple replacement if URL decoding fails
            try:
                custom_fields = json.loads(custom_fields.replace("'", '"'))
            except (json.JSONDecodeError, TypeError):
                print("[DEBUG] Failed to parse custom_fields, using empty dict")
                custom_fields = {}
    else:
        # For non-open source projects, use original parsing method
        custom_fields = json.loads(custom_fields.replace("'", '"'))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{project_key}_{timestamp}.json"
    print(f"filename >> {filename}")

    export_jira_issues(
        jira_url=jira_url,
        username=username,
        api_token=api_token,
        project_key=project_key,
        fields_to_include=DEFAULT_FIELDS + selected_fields,
        issue_types=issue_types,
        timestamp=timestamp,
        is_open_source=is_open_source,
        custom_fields=custom_fields,
        include_comments=include_comments
    )

    # Register this project in the user's tracked project list
    if not is_open_source:
        add_project_to_registry(normalize_jira_url(jira_url), username, project_key)
        session["user_projects"] = session.get("user_projects", [])
        if project_key not in session["user_projects"]:
            session["user_projects"].append(project_key)

    flash(f"Import successful: {filename}", "success")

    # except Exception as e:
    #     flash(f"Import failed: {str(e)}", "danger")

    return redirect("/")


def _reset_export_progress():
    jira_export_progress.update({
        "status": "idle", "total": 0, "fetched": 0,
        "message": "", "phase": "", "error": None,
        "result_filename": None, "result_count": 0,
        "cancelled": False,
    })


def _export_progress_callback(phase, total, fetched, message):
    jira_export_progress.update({
        "phase": phase,
        "total": total,
        "fetched": fetched,
        "message": message,
    })


def _run_export_in_background(jira_url, username, api_token, project_key,
                              fields_to_include, issue_types, timestamp,
                              is_open_source, custom_fields, include_comments=True, creation_date=None):
    pending_filepath = os.path.join(DATABASES_FOLDER, f"{project_key}_{timestamp}.json")
    pending_settings_path = os.path.join(DATABASES_SETTINGS_FOLDER, f"{project_key}_{timestamp}_settings.json")

    def cancel_check():
        return jira_export_progress.get("cancelled", False)

    try:
        jira_export_progress["status"] = "running"
        jira_export_progress["message"] = "Starting JIRA export..."
        filepath, count = export_jira_issues(
            jira_url=jira_url,
            username=username,
            api_token=api_token,
            project_key=project_key,
            fields_to_include=fields_to_include,
            issue_types=issue_types,
            timestamp=timestamp,
            is_open_source=is_open_source,
            custom_fields=custom_fields,
            include_comments=include_comments,
            progress_callback=_export_progress_callback,
            cancel_check=cancel_check,
            creation_date=creation_date
        )
        jira_export_progress.update({
            "status": "done",
            "message": f"Export complete: {count} issues saved",
            "result_filename": os.path.basename(filepath),
            "result_count": count,
            "fetched": jira_export_progress["total"],
        })
    except ExportCancelled:
        for partial in [pending_filepath, pending_settings_path]:
            if os.path.exists(partial):
                try:
                    os.remove(partial)
                    print(f"[INFO] Removed partial export file: {partial}")
                except OSError as remove_err:
                    print(f"[WARNING] Could not remove partial file {partial}: {remove_err}")
        jira_export_progress.update({
            "status": "cancelled",
            "message": "Export cancelled by user.",
            "phase": "",
        })
    except Exception as e:
        traceback.print_exc()
        jira_export_progress.update({
            "status": "error",
            "message": str(e),
            "error": str(e),
        })


@bp.route("/generate_async", methods=["POST"])
def generate_async():
    """Start JIRA export in a background thread and return immediately."""
    jira_url = request.form["jira_url"]
    username = request.form.get("username", "")
    api_token = request.form.get("api_token", "")
    project_key = request.form["project_key"]
    selected_fields = request.form.getlist("fields")
    include_comments = "comment" in selected_fields
    selected_fields = [f for f in selected_fields if f != "comment"]
    issue_types = request.form.getlist("issuetype")
    is_open_source = request.form.get("open_source", "false") == "true"
    custom_fields = request.args.get("custom_fields")
    included_item_age = request.form.get("item_age", None)
    creation_year = date.today().year - int(included_item_age) if included_item_age else None
    creation_date = f"{creation_year}-01-01" if creation_year else None

    # Store export credentials in session so push_to_jira uses the same creds
    if not is_open_source:
        session["jira_url"] = normalize_jira_url(jira_url)
        session["jira_username"] = username
        session["jira_password"] = api_token

    if is_open_source:
        try:
            import urllib.parse
            custom_fields = json.loads(urllib.parse.unquote(custom_fields))
        except (json.JSONDecodeError, TypeError):
            try:
                custom_fields = json.loads(custom_fields.replace("'", '"'))
            except (json.JSONDecodeError, TypeError):
                custom_fields = {}
    else:
        custom_fields = json.loads(custom_fields.replace("'", '"'))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    _reset_export_progress()
    jira_export_progress["status"] = "running"
    jira_export_progress["message"] = f"Starting export for {project_key}..."

    # Register this project in the user's tracked project list
    if not is_open_source:
        add_project_to_registry(normalize_jira_url(jira_url), username, project_key)
        session["user_projects"] = session.get("user_projects", [])
        if project_key not in session["user_projects"]:
            session["user_projects"].append(project_key)
    else:
        add_project_to_registry(normalize_jira_url(session["jira_url"]), session["jira_username"], project_key)
        session["user_projects"] = session.get("user_projects", [])
        if project_key not in session["user_projects"]:
            session["user_projects"].append(project_key)

    t = threading.Thread(
        target=_run_export_in_background,
        args=(jira_url, username, api_token, project_key,
              DEFAULT_FIELDS + selected_fields, issue_types, timestamp,
              is_open_source, custom_fields, include_comments, creation_date),
        daemon=True
    )
    t.start()

    return jsonify({"ok": True, "project_key": project_key, "timestamp": timestamp})


@bp.route("/get_jira_export_progress")
def get_jira_export_progress_route():
    return jsonify(jira_export_progress)


@bp.route("/cancel_jira_export", methods=["POST"])
def cancel_jira_export():
    """Signal the running background export to stop and clean up any partial files."""
    if jira_export_progress.get("status") == "running":
        jira_export_progress["cancelled"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "reason": "No export currently running"})


@bp.route("/jira_viewer")
def jira_viewer():
    files = [f for f in os.listdir(DATABASES_FOLDER) if f.endswith(".json")
             and "_predictions" not in f
             and "_test" not in f
             ]
    jira_url = session.get("jira_url", "")
    username = session.get("jira_username", "")
    if jira_url and username:
        files = filter_files_by_user_projects(files, jira_url, username)
    target_matrix_per_project = get_target_fields_matrix_per_project()
    saved_target_matrix_per_project, saved_params_per_project = get_saved_target_fields_matrix_per_project()
    best_performance_per_project = get_best_performance_per_project()
    return render_template(
        "jira_viewer.html",
        files=files,
        target_matrix_per_project=target_matrix_per_project,
        saved_target_matrix_per_project=saved_target_matrix_per_project,
        saved_params_per_project=saved_params_per_project,
        best_performance_per_project=best_performance_per_project
    )

@bp.route("/show_jira_viewer", methods=["POST"])
def show_jira_viewer():

    filename = request.form['filename']
    project_json = f"{DATABASES_FOLDER}/{filename}"
    project = request.form['filename'].split('_')[0]
    field_gird_dict = json.loads(request.form['fieldGridDict'])
    accuracy_per_field = field_gird_dict['accuracyPerField'].get(project, {})
    field_gird_path = f'{INFERABILITY_ANALYSIS}/{filename.replace(".json", "_grid.json")}'
    acceptable_labeled_data_ratio = request.form['labeledDataRatio']
    min_test_data_size = request.form['minTestDataSize']
    print("[DEBUG] field_gird_path:", field_gird_path)
    print("[DEBUG] min_test_data_size:", min_test_data_size)
    print("[DEBUG] acceptable_labeled_data_ratio:", acceptable_labeled_data_ratio)
    print("[DEBUG] accuracy_per_project_per_field:", field_gird_dict['accuracyPerField'])

    # Save parameters
    Path(INFERABILITY_ANALYSIS).mkdir(parents=True, exist_ok=True)
    with open(field_gird_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "data": field_gird_dict["data"],
                "metadata": {
                    "acceptable_labeled_data_ratio": int(acceptable_labeled_data_ratio),
                    "min_test_data_size": int(min_test_data_size),
                    "disabled_fields": field_gird_dict["metadata"],
                    "accuracy_per_field": accuracy_per_field
                }
            },
            file, ensure_ascii=False, indent=4
        )

    # predictable_fields = list(map(lambda x: x.title().replace('_', ' '), get_predictable_fields(project_json)))
    selected_fields = field_gird_dict["data"].keys()
    disabled_fields = field_gird_dict["metadata"]
    target_fields = [field for field in  selected_fields if field not in disabled_fields]
    target_fields = list(map(lambda x: x.title().replace('_', ' '), target_fields))

    data = {}
    if Path(JIRA_COMPONENTS_PRIORITIES_FILE).exists():
        with open(JIRA_COMPONENTS_PRIORITIES_FILE, 'r') as f:
            data = json.load(f)

    possible_values = get_target_field_possible_values(
        project_json,
        ["labels", "epic_link"]
    )
    flat_labels = []
    [flat_labels.extend(sublist) for sublist in possible_values[0].get("labels_values", [])]

    fields_possible_values = {
        "components": data.get(project, []),
        "priority": data.get("priorities", []),
        "labels": flat_labels,
        "epic_link": possible_values[0].get("epic_link_values", [])
    }
    best_model_per_field = {}
    performance_file = project_json.replace("databases", "performances")
    if Path(performance_file).is_file():
        with open(performance_file, 'r') as file:
            perf_dict = json.load(file)
            best_model_per_field = perf_dict["best_model_per_field"]
    return render_template(
        "jira_viewer_table.html",
        project_json=project_json,
        project = project,
        fields_possible_values = fields_possible_values,
        target_fields = sorted(target_fields),
        best_model_per_field = best_model_per_field,
        field_gird_dict = field_gird_dict
    )


@bp.route("/validate_push_issues", methods=["POST"])
def validate_push_issues():
    """
    Validate issues before pushing to Jira.
    Checks if target fields are still empty in Jira AND if descriptions have changed.
    Updates the consolidated file with ignore flags for issues that should be skipped.
    Returns list of issues that will be omitted with their omission reasons.
    """
    if not session.get("auth"):
        return jsonify({"error": "Not authenticated"}), 401

    jira_url = normalize_jira_url(session.get("jira_url", ""))
    username = session.get("jira_username")
    password = session.get("jira_password")

    if not all([jira_url, username, password]):
        return jsonify({"error": "Missing Jira credentials in session"}), 400

    try:
        data = request.get_json() or {}
        filename = data.get("filename")

        ready_to_send_folder = os.path.join(ITERATION_FOLDER, "ready_to_send")

        if filename:
            filepath = os.path.join(ready_to_send_folder, filename)
        else:
            files = sorted(
                [f for f in os.listdir(ready_to_send_folder) if f.endswith(".json")],
                reverse=True
            )
            if not files:
                return jsonify({"error": "No consolidated files found"}), 404
            filepath = os.path.join(ready_to_send_folder, files[0])
            filename = files[0]

        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {filepath}"}), 404

        with open(filepath, "r", encoding="utf-8") as f:
            consolidated_data = json.load(f)

            # Filter out sent items
            output_folder = filepath.split("_consolidated")[0]
            consolidated_data = _filter_out_sent_items(consolidated_data, f"{output_folder}")

        # Get local DB path for description comparison
        db_path = data.get("db_path", "")
        if not db_path:
            db_path = utils.model_config.get(CFG_INPUT_FILE, "") if utils.model_config else ""
        local_descriptions = _get_description_lookup(db_path)

        # Collect all unique (issue_key, field) pairs and their predicted values
        issue_field_predictions = {}  # {issue_key: {field: predicted_value}}

        for issue_type, predictions in consolidated_data.get("predictions_by_issuetype", {}).items():
            for pred in predictions:
                field_name = pred.get("field")
                new_value = pred.get("new_value")
                issue_keys = pred.get("issue_keys", [])

                for issue_key in issue_keys:
                    clean_key = issue_key.split(":")[0].strip() if ":" in issue_key else issue_key.strip()
                    if clean_key not in issue_field_predictions:
                        issue_field_predictions[clean_key] = {}
                    issue_field_predictions[clean_key][field_name] = new_value

        # Query Jira for each issue and check field values + descriptions
        auth = (username, password)
        omitted_issues = []
        valid_count = 0

        # Get all unique fields to query, plus description for comparison
        all_fields = set()
        for fields_dict in issue_field_predictions.values():
            all_fields.update(fields_dict.keys())
        all_fields.add("description")
        all_fields = list(map(lambda x: resolve_custom_field_id(jira_url, auth, x), all_fields))

        # Track issues with changed descriptions (all their predictions should be ignored)
        issues_with_changed_description = set()

        # First pass: identify issues with changed descriptions
        for issue_key in issue_field_predictions.keys():
            current_fields = fetch_issue_fields(jira_url, issue_key, list(all_fields), auth)
            jira_description = current_fields.get("description")
            local_description = local_descriptions.get(issue_key, "")

            if _descriptions_differ(local_description, jira_description):
                issues_with_changed_description.add(issue_key)

        # Initialize ignore_flags in consolidated data if not present
        if "ignore_flags" not in consolidated_data:
            consolidated_data["ignore_flags"] = {}

        # Second pass: check field values and build omitted list
        for issue_key, fields_to_check in issue_field_predictions.items():
            current_fields = fetch_issue_fields(jira_url, issue_key, list(all_fields), auth)

            for field_name, predicted_value in fields_to_check.items():
                field_name = resolve_custom_field_id(jira_url, auth, field_name)
                current_value = current_fields.get(field_name)
                flag_key = f"{issue_key}|{field_name}"

                # Check if description changed - flag ALL predictions for this issue
                if issue_key in issues_with_changed_description:
                    omitted_issues.append({
                        "issue_key": issue_key,
                        "field": field_name,
                        "predicted_value": predicted_value,
                        "current_value": _extract_field_display_value(current_value) if current_value else "",
                        "reason": "description_changed"
                    })
                    consolidated_data["ignore_flags"][flag_key] = {
                        "ignored": True,
                        "reason": "description_changed"
                    }
                # Check if field is no longer empty
                elif not _is_field_empty(current_value):
                    omitted_issues.append({
                        "issue_key": issue_key,
                        "field": field_name,
                        "predicted_value": predicted_value,
                        "current_value": _extract_field_display_value(current_value),
                        "reason": "field_populated"
                    })
                    consolidated_data["ignore_flags"][flag_key] = {
                        "ignored": True,
                        "reason": "field_populated"
                    }
                else:
                    valid_count += 1
                    # Remove ignore flag if it was previously set but now valid
                    if flag_key in consolidated_data["ignore_flags"]:
                        del consolidated_data["ignore_flags"][flag_key]

        # Save updated consolidated file with ignore flags
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)

        return jsonify({
            "success": True,
            "omitted_issues": omitted_issues,
            "omitted_count": len(omitted_issues),
            "valid_count": valid_count,
            "description_changed_count": len(issues_with_changed_description)
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@bp.route("/push_to_jira", methods=["POST"])
def push_to_jira():
    """
    Push consolidated predictions to Jira.
    Expects JSON body with 'filename' (optional) to specify which consolidated file to push.
    Uses session credentials for Jira authentication.
    """
    # Remove temporary iteration file once done with it.
    rem_count = remove_files_with_string(ITERATION_FOLDER, "_pushed")
    print(f"[INFO] {rem_count} '*_pushed.json' file(s) removed.")

    if not session.get("auth"):
        return jsonify({"error": "Not authenticated"}), 401

    jira_url = normalize_jira_url(session.get("jira_url", ""))
    username = session.get("jira_username")
    password = session.get("jira_password")

    if not all([jira_url, username, password]):
        return jsonify({"error": "Missing Jira credentials in session"}), 400

    try:
        data = request.get_json() or {}
        filename = data.get("filename")

        ready_to_send_folder = os.path.join(ITERATION_FOLDER, "ready_to_send")

        if filename:
            filepath = os.path.join(ready_to_send_folder, filename)
        else:
            files = sorted(
                [f for f in os.listdir(ready_to_send_folder) if f.endswith(".json")],
                reverse=True
            )
            if not files:
                return jsonify({"error": "No consolidated files found in ready_to_send folder"}), 404
            filepath = os.path.join(ready_to_send_folder, files[0])

        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {filepath}"}), 404

        with open(filepath, "r", encoding="utf-8") as f:
            consolidated_data = json.load(f)

        auth = (username, password)

        # Filter out predictions where target fields are no longer empty
        filtered_data = _filter_non_empty_fields(consolidated_data, jira_url, auth)
        jira_format = transform_consolidated_to_jira_format(filtered_data, username)

        if not jira_format.get("target_fields"):
            return jsonify({"error": "No predictions to push (all fields already populated)"}), 400

        results = apply_prediction_json_to_jira(jira_format, jira_url, auth)
        print("[DEBUG] results[0]:", results[0])

        # Update sent file
        sent_filepath = f"{filepath.split('_consolidated')[0]}_sent.json"
        sent_data = []
        if os.path.exists(sent_filepath):
            with open(sent_filepath, "r", encoding="utf-8") as f:
                sent_data = json.load(f)
        ok_results = list(filter(lambda result: result.get("status", 0) in (200, 204), results))
        sent_data.extend(ok_results)
        with open(sent_filepath, "w", encoding="utf-8") as file:
            json.dump(sent_data, file, indent=2, ensure_ascii=False)
        
        success_count = sum(1 for r in results if r.get("status") in (200, 204))
        failed_count = len(results) - success_count
        
        # Build detailed per-issue results for the frontend summary modal
        successful_items = []
        failed_items = []
        for r in results:
            item = {
                "issuekey": r.get("issuekey", ""),
                "field": r.get("field", ""),
                "field_name": r.get("field_name", ""),
                "question_id": r.get("question_id", "")
            }
            if r.get("status") in (200, 204):
                successful_items.append(item)
            else:
                # Extract error detail from response
                resp = r.get("response", "")
                if isinstance(resp, dict):
                    errors = resp.get("errors", {})
                    error_messages = resp.get("errorMessages", [])
                    detail = "; ".join(
                        [f"{k}: {v}" for k, v in errors.items()] + list(error_messages)
                    ) or json.dumps(resp)
                else:
                    detail = str(resp)
                item["status_code"] = r.get("status")
                item["error"] = detail
                failed_items.append(item)
        
        return jsonify({
            "success": True,
            "success_count": success_count,
            "failed_count": failed_count,
            "successful_items": successful_items,
            "failed_items": failed_items
        }), 200
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
