"""
Config / data-analysis routes:
  /, /data_analysis, /run_data_analysis, /get_iterations_by_project,
  /view/<filename>, /data/<folder>, /audit/<folder>, /load_json
"""
import ast
import json
import os
from pathlib import Path

from flask import Blueprint, request, jsonify, render_template, current_app, session

import analysis.data_pre_analysis as data_pre_analysis
import utils_pkg as utils
from auth.user_registry import filter_files_by_user_projects
from config import FIELD_COMPLETION_FOLDER
from config.constants import (
    TOOLTIP_DICT, DATABASES_FOLDER, ITERATION_FOLDER,
    TRACEABILITY_ITERATION_TABLE_FILE, AUDIT_OUT_FILE_SUFFIX
)
from services.iteration_service import get_iterations_field_summary, field_summary_iteration_zero, apply_iterations

bp = Blueprint("config", __name__)


@bp.route("/")
def index():
    return render_template("index.html", tooltip=TOOLTIP_DICT)


@bp.route("/data_analysis")
def data_analysis():
    files = [f for f in os.listdir(DATABASES_FOLDER) if f.endswith(".json")]
    jira_url = session.get("jira_url", "")
    username = session.get("jira_username", "")
    if jira_url and username:
        files = filter_files_by_user_projects(files, jira_url, username)
    return render_template("data_analysis.html", files=files)


@bp.route("/get_iterations_by_project", methods=["POST"])
def get_iterations_by_project():
    data = request.get_json()
    project = data.get("project")
    traceability_path = os.path.join(ITERATION_FOLDER, f"{TRACEABILITY_ITERATION_TABLE_FILE}.json")

    if not os.path.exists(traceability_path):
        return jsonify({ "iterations": [], "totals": {} })

    with open(traceability_path, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    project_data = trace_data.get(project, {})
    return jsonify({
        "iterations": project_data.get("iterations", []),
        "totals": project_data.get("totals", {})
    })


@bp.route("/run_data_analysis", methods=["POST"])
def run_data_analysis():
    report_type = request.form.get("report_type")
    print(f"[DEBUG] report_type:", report_type)
    db_filename = request.form.get("filename", "")
    input_file = os.path.join(DATABASES_FOLDER, db_filename)
    project = utils.extract_project_key_from_filename(db_filename)
    output_folder = os.path.splitext(db_filename)[0]
    if report_type == "blocker_blocked_priority":
        json_path = data_pre_analysis.generate_blocker_blocked_priority_data(input_file, project, output_folder)
        return render_template(
            "blocker_blocked_priority.html",
            json_path=json_path,
            project=project
        )
    elif report_type == "parent_child_priority":
        json_path = data_pre_analysis.generate_parent_children_priority_data(input_file, project, output_folder)
        return render_template(
            "parent_children_priority.html",
            json_path=json_path,
            project=project
        )
    elif report_type == "parent_child_components":
        json_path = data_pre_analysis.generate_parent_children_components_data(input_file, project, output_folder)
        return render_template(
            "parent_children_components.html",
            json_path=json_path,
            project=project
        )
    elif report_type == "inheritance_rules":
        jira_issues = []
        if os.path.exists(input_file):
            with open(input_file, 'r', encoding='utf-8') as file:
                jira_issues = json.load(file)
        target_fields = ["epic_link", "components", "labels", "team"]
        inheritance_rules = data_pre_analysis.get_inheritance_rules_html(jira_issues, fields=target_fields)
        with open("templates/inheritance_rules.html", 'w') as file_object:
            file_object.write(f"<pre><h3>{project} Inheritance Rules</h3><hr>{inheritance_rules}")
        return render_template("inheritance_rules.html")
    return None


@bp.route("/view/<filename>")
def view_inferred(filename):
    if not filename.endswith(".html"):
        filename += ".html"
    try:
        return render_template(filename)
    except:
        return f"File '{filename}' not found in templates.", 404


@bp.route('/data/<folder>')
def get_json_data(folder):
    project = request.args["project"]
    json_file_path = os.path.join(current_app.root_path, folder, f"{project}_inferred.json")
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "JSON file not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Error decoding JSON"}), 500


@bp.route('/audit/<folder>')
def get_audit_json_data(folder):
    project = request.args["project"]
    # json_file_path = os.path.join(current_app.root_path, folder, f"{project}{AUDIT_OUT_FILE_SUFFIX}.json")
    json_file_path = os.path.join(current_app.root_path, FIELD_COMPLETION_FOLDER, f"{folder}.json")
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
            # Filter out irrelevant fields
            saved_target_fields_per_project, metadata = data_pre_analysis.get_saved_target_fields_matrix_per_project()
            target_fields = saved_target_fields_per_project.get(folder, {})
            if not target_fields:
                project_db_path = os.path.join(DATABASES_FOLDER, f"{folder}.json")
                target_field_matrix = data_pre_analysis.get_target_fields_matrix(jira_issues=None, project_db_path=project_db_path)
                target_fields = target_field_matrix.get("inferable_fields", [])
            data["data"] = [ item for item in data["data"] if item["field"] in target_fields]
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "JSON file not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Error decoding JSON"}), 500


@bp.route('/load_json')
def load_json():
    json_path = request.args["path"]
    llm_path = request.args.get("llmPath", None)
    selected_target_fields_str = request.args.get("selectedTargets", None)
    selected_target_fields = ast.literal_eval(selected_target_fields_str)
    selected_target_fields = [item.lower().replace(' ', '_') for item in selected_target_fields]
    print(f"[DEBUG] llm_path:", llm_path)
    print(f"[DEBUG] selected_target_fields:", selected_target_fields)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if "databases" not in json_path:
            return jsonify(data)
        else:
            # TODO: use constants
            iter_dir = str(Path(json_path).parent).replace("databases", "iterations")
            rejected_predictions_dict = apply_iterations(
                data,
                project_name=Path(json_path).stem,
                iteration_dir=iter_dir
            )
            print("[DEBUG] rejected_predictions_dict:", rejected_predictions_dict)
            target_fields = ["priority", "components", "labels", "team", "epic_link"]
            target_fields = selected_target_fields if selected_target_fields else target_fields
            for jira_issue in data:
                jira_issue["llm_conf"] = jira_issue.get("generated_description_confidence", None)
                if jira_issue.get("generated_description", None):
                    llm_diff = data_pre_analysis.compare_files_and_get_diff(
                        jira_issue["description"].split('\n') if jira_issue["description"] else "",
                        jira_issue["generated_description"].split('\n'),
                    )
                    filtered_llm_diff = list(filter(lambda line: not line.startswith("?"), llm_diff))
                    llm_diff_marked = list(map(
                        lambda line: f"<added>{line}</added>" if line.startswith("+") else line,
                        filtered_llm_diff
                    ))
                    llm_diff_marked = list(map(
                        lambda line: f"<removed>{line}</removed>" if line.startswith("-") else line,
                        llm_diff_marked
                    ))
                    multiline_llm_diff = "\n".join(llm_diff_marked)
                    jira_issue["llm_diff"] = multiline_llm_diff

                for field in target_fields:
                    rejected_predictions = rejected_predictions_dict.get(field, {}).get(jira_issue["key"], None)
                    rejected_predictions_str = f" {rejected_predictions} [R]" if rejected_predictions else ""
                    if not jira_issue.get(field):
                        jira_issue[field] = f"---{rejected_predictions_str}"
                    if field in jira_issue.get("inf_iter", {}):
                        inf_iter = jira_issue["inf_iter"][field]
                        jira_issue[field] = f"{jira_issue[field]} [I#{inf_iter + 1}]"
            return jsonify({"data": data})

    except FileNotFoundError:
        return jsonify({"error": "JSON file not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Error decoding JSON"}), 500
