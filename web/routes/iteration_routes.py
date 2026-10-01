"""
Iteration routes: /consolidate_iterations, /toggle_ignore_flag
"""
import json
import os
import traceback

from flask import Blueprint, jsonify, request, session

import utils_pkg as utils
from services.iteration_service import consolidate_iterations_data
from config.constants import ITERATION_FOLDER

bp = Blueprint("iteration", __name__)


@bp.route("/consolidate_iterations", methods=["POST"])
def consolidate_iterations():
    """
    Consolidates all iteration files for the current project into a single JSON file
    in the ready_to_send folder. Returns the consolidated data for display in a modal,
    grouped by issue type. Only keeps one file per project, replacing if content changed.
    """
    try:
        data = request.get_json() or {}
        project_override = data.get("project")
        output_folder = data.get("output_folder") or ""
        result, status_code = consolidate_iterations_data(
            utils.model_config,
            project_override=project_override,
            output_folder=output_folder
        )
        result = _filter_out_sent_items(result, f"{output_folder}")
        return jsonify(result), status_code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def _filter_out_sent_items(result, output_folder):
    ready_to_send_folder = os.path.join(ITERATION_FOLDER, "ready_to_send")
    sent_filepath = os.path.join(ready_to_send_folder, f"{output_folder}_sent.json")
    sent_data = []
    if os.path.exists(sent_filepath):
        with open(sent_filepath, "r", encoding="utf-8") as f:
            sent_data = json.load(f)
    total_issue_keys = 0
    for k, v in result.get("predictions_by_issuetype", {}).items():
        for o in v:
            field_sent_data = list(filter(lambda x: x["field_name"] == o["field"], sent_data))
            field_sent_keys = list(map(lambda x: x["issuekey"], field_sent_data))
            o["issue_keys"] = list(filter(lambda issue_key: issue_key not in field_sent_keys, o["issue_keys"]))
            # Quick fix: remove sent item
            if not o["issue_keys"]:
                v.remove(o)
            else:
                total_issue_keys += len(o["issue_keys"])
    result["total_issue_keys"] = total_issue_keys
    return result

@bp.route("/delete_iteration_file", methods=["POST"])
def delete_iteration_file():
    """
    Deletes a specific iteration file by filename.
    Used when the consolidation modal is closed/canceled without pushing to Jira.
    """
    try:
        data = request.get_json() or {}
        filename = data.get("filename")
        
        if not filename:
            return jsonify({"error": "No filename provided"}), 400
        
        # Security: ensure filename doesn't contain path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"error": "Invalid filename"}), 400
        
        filepath = os.path.join(ITERATION_FOLDER, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found", "deleted": False}), 404
        
        os.remove(filepath)
        print(f"[INFO] Deleted iteration file: {filename}")
        
        return jsonify({"success": True, "deleted": True, "filename": filename}), 200
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@bp.route("/toggle_ignore_flag", methods=["POST"])
def toggle_ignore_flag():
    """
    Toggle the ignore flag for a specific issue+field combination.
    If flag exists, remove it (allowing push). If not, add it (preventing push).
    """
    if not session.get("auth"):
        return jsonify({"error": "Not authenticated"}), 401

    try:
        data = request.get_json() or {}
        filename = data.get("filename")
        issue_key = data.get("issue_key")
        field_name = data.get("field")
        reason = data.get("reason", "manual_override")

        if not issue_key or not field_name:
            return jsonify({"error": "Missing issue_key or field parameter"}), 400

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

        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {filepath}"}), 404

        with open(filepath, "r", encoding="utf-8") as f:
            consolidated_data = json.load(f)

        flag_key = f"{issue_key}|{field_name}"

        # Initialize ignore_flags if not present
        if "ignore_flags" not in consolidated_data:
            consolidated_data["ignore_flags"] = {}

        # Toggle the ignore flag
        if flag_key in consolidated_data["ignore_flags"]:
            # Flag exists - remove it (allow push)
            del consolidated_data["ignore_flags"][flag_key]
            action = "removed"
            new_state = "active"
        else:
            # Flag doesn't exist - add it (prevent push)
            consolidated_data["ignore_flags"][flag_key] = {
                "ignored": True,
                "reason": reason
            }
            action = "added"
            new_state = "ignored"

        # Save updated consolidated file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)

        return jsonify({
            "success": True,
            "action": action,
            "new_state": new_state,
            "message": f"Ignore flag {action} for {issue_key} - {field_name}"
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
