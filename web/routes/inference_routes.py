"""
Inference routes:
  /confirmation, /field_summary, /process_csv, /confirmation_completed,
  /field_completion, /run_field_audit, /get_test_report, /confirm_predictions,
  /get_clustering_progress, /get_inference_progress, /abort_ml_predictions,
  /get_ml_predictions
"""
import copy
import json
import multiprocessing
import os
import queue
import shutil
import time
import traceback
from pathlib import Path

from flask import Blueprint, request, jsonify, render_template, flash, current_app, redirect, session

import analysis.data_pre_analysis as data_pre_analysis
import utils_pkg as utils
from config import INFERABILITY_ANALYSIS, FIELD_COMPLETION_FOLDER
from config.logger import Logger
from nlp.centroid_manager import (
    get_target_field_possible_values, compute_list_accuracy_score,
    list_items_to_boolean_fields, boolean_fields_to_list, compute_predictions_accuracy
)
from ml.model_selection import SupportedModels, infer_using_model
from ml.evaluation import evaluate_model_cv
from services.test_service import generate_test_results_json, select_random_issues_from_train_issues_to_test_inference
from services.iteration_service import (
    get_iterations_field_summary, generate_iteration_file, register_new_iteration_record,
    trigger_clustering_process, field_summary_iteration_zero,
    get_iteration_records_by_project, format_data_to_fit_confirmation_page, get_inference_json, apply_iterations,
    tag_rejected_predictions, get_saved_review_state, apply_sent_items_if_needed
)
from services.inference_pipeline import run_field_completion
from config.constants import (
    CFG_PROJECT, CFG_OUTPUT_FOLDER, CFG_FIELD_MODELS, CFG_CONFIDENCE_FIELD,
    FID_ORPHAN_COUNT, FID_TOTAL_CONFIDENCE, FID_TOTAL_ISSUE_COUNT,
    DATABASES_FOLDER, DATABASES_SETTINGS_FOLDER,
    ITERATION_FOLDER, ITERATION_PREFIX, TRACEABILITY_ITERATION_TABLE_FILE,
    AUDIT_OUT_FILE_SUFFIX, INFERENCE_OUT_FILE_SUFFIX,
    DEPENDENCY_MODEL_FOLDER, PREDICTIONS_FOLDER
)
from auth.user_registry import filter_files_by_user_projects, get_user_projects
from web.shared_state import inference_progress_dict, clustering_progress_dict, inference_threads_progress_dict, \
    iteration_progress_dict

global_inference_processes_progress_dict = {}
global_inference_processes = []
global_trace_entry_data = None
bp = Blueprint("inference", __name__)



@bp.route("/confirmation")
def confirmation():
    config = utils.model_config
    project = ""
    output_folder = ""
    question_count = 0
    total_issues_count = 0

    # Handle None config for testing
    if config is None:
        # Return default values for testing
        iteration_count = 0
        jira_users = []
        jira_base_url = ""
        iteration_information = {
            FID_TOTAL_CONFIDENCE: 0.0,
            FID_TOTAL_ISSUE_COUNT: 0,
            FID_ORPHAN_COUNT: 0
        }
    else:
        (iteration_count, jira_users, jira_base_url, question_count, iteration_information) = trigger_clustering_process(config)

    return render_template(
        "confirmation.html",
        iter=iteration_count,
        avg=f"{iteration_information[FID_TOTAL_CONFIDENCE]:.3f}",
        qst=question_count,
        total_issue=iteration_information[FID_TOTAL_ISSUE_COUNT] - iteration_information[FID_ORPHAN_COUNT],
        jira_users=jira_users,
        jira_base_url=jira_base_url,
        iteration_information=iteration_information
    )

@bp.route("/field_summary", methods=["GET", "POST"])
def field_summary():
    config = utils.model_config
    output_folder = ""
    if config is not None:
        project = config.get(CFG_PROJECT, CFG_PROJECT)
        output_folder = config.get(CFG_OUTPUT_FOLDER, project)
        field_models = config.get(CFG_FIELD_MODELS, {})  # type: ignore
        target_fields = list(field_models.keys())
        Logger.debug(f"target_fields from config: {target_fields}")
    else:
        # Handle JSON POST data for testing
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
            project = data.get("project", None)
            output_folder = data.get("output_folder", None)
            field = data.get("field", None)
            target_fields = [field] if field else None
        else:
            # Fallback to query parameters for backward compatibility
            project = request.args.get("project", None)
            output_folder = request.args.get("outFolder", None)
            target_fields = request.args.get("infFields", None)

    iteration_path = f"{ITERATION_FOLDER}/{TRACEABILITY_ITERATION_TABLE_FILE}.json"
    # audit_path = f"{output_folder}/{project}{AUDIT_OUT_FILE_SUFFIX}.json"
    audit_path = f"{FIELD_COMPLETION_FOLDER}/{output_folder}.json"

    try:
        response = get_iterations_field_summary(output_folder,iteration_path)
        print("[DEBUG] Service response:", response)
        print("[DEBUG] Response type:", type(response))
        if isinstance(response, str):
            print("[DEBUG] Using field_summary_iteration_zero")
            response =  field_summary_iteration_zero(target_fields, audit_path, project)
            print("[DEBUG] Zero response:", response)

        print("[DEBUG] Final response:", response)
        return jsonify(response), 200
    except Exception as e:
        print(f"[DEBUG] Exception in field_summary: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/process_csv", methods=["GET", "POST"])
def process_csv():
    if "question_json" in current_app.config.keys():
        result = current_app.config["question_json"]
    else:
        result = ""
    return jsonify(result)

@bp.route("/confirmation_completed", methods=["POST"])
def confirmation_completed():
    try:
        data = request.get_json(force=True) or {}
        results = data.get("results", {})
        meta = data.get("meta", {}) or {}
        is_save_iteration = meta.get("isSaveIteration", False)
        is_push_to_jira = meta.get("isPushToJira", False)
        disabled_checkboxes = meta.get("disabledCheckboxes", {})
        # tallies are used to check the review page hasn't changed before restoring the save state.
        review_page_tallies = meta.get("tallies", {})
        review_page_tallies_per_tab = meta.get("talliesPerTab", {})
        # print("[DEBUG] review_page_tallies:", review_page_tallies)
        # print("[DEBUG] review_page_tallies_per_tab:", review_page_tallies_per_tab)
        # print("[DEBUG] disabled_checkboxes:", disabled_checkboxes)

        # Safely coerce types
        def to_int(x, default=0):
            try:
                return int(x)
            except (TypeError, ValueError):
                return default

        total_approved = to_int(meta.get("totalApproved"), 0)
        question_issue_count = to_int(meta.get("questionIssueCount"), 0)
        q_number = to_int(meta.get("qNumber"), 0)
        user_name = meta.get("userName") or "empty"
        iteration_information = meta.get("iterationInformation") or {}
        project = meta.get("project") or ""
        output_folder = meta.get("outputFolder") or ""

        # Your existing logic, now using 'results'
        iteration_filename = generate_iteration_file(
            results, user_name,
            project_override=project if project else None,
            output_folder=output_folder if output_folder else None,
            is_save_iteration=is_save_iteration,
            review_page_tallies=review_page_tallies,
            review_page_tallies_per_tab=review_page_tallies_per_tab,
            is_push_to_jira=is_push_to_jira,
            disabled_checkboxes=disabled_checkboxes
        )
        inference_threads_progress_dict["iteration_filename"] = iteration_filename

        if is_save_iteration:
            return jsonify({
                "message": "Save action received.",
                "filename": None,
                "iteration_filename": iteration_filename
            }), 200
        else:
            global global_trace_entry_data
            dependency_model_path, global_trace_entry_data = register_new_iteration_record(
                total_approved, question_issue_count, q_number, user_name, results, iteration_information,
                project_override=project if project else None,
                is_skip_traceability_update = iteration_filename is None
            )
            return jsonify({
                "message": "Confirmation received.",
                "filename": dependency_model_path,
                "iteration_filename": iteration_filename
            }), 200


    except Exception as e:
        flash(f"Prediction confirmation failed: {str(e)}", "danger")
        print("[DEBUG] Exception:", str(e))
        return jsonify({"error": str(e)}), 400


@bp.route("/field_completion", methods=["POST", "GET"])
def field_completion():
    user_projects = get_user_projects(session.get("jira_url"), session.get("jira_username"))
    files = [f for f in os.listdir(DATABASES_FOLDER) if f.endswith(".json")]
    user_files = [f for f in files if f.split('_')[0] in user_projects]
    iter_files = list(map(lambda x: os.path.basename(x), Path(ITERATION_FOLDER).glob("*.json")))
    user_iter_files = [f for f in iter_files if files if f.split('_')[0] in user_projects]
    return render_template(
        "field_completion.html",
        files=user_files,
        iterations=user_iter_files
    )

@bp.route("/run_field_audit", methods=["POST"])
def run_field_audit():
    database_path = os.path.join(DATABASES_FOLDER, request.form.get("filename", ""))
    is_all_previous_iterations = request.form.get("isIterations", "") == "on"
    is_exclude_closed = request.form.get("isNoClosed", "") == "on"
    iteration_to_include = request.form.get("iteration")
    response = run_field_completion(database_path, is_all_previous_iterations, iteration_to_include, is_exclude_closed)
    return response

@bp.route('/get_test_report', methods=["POST"])
def get_test_report():
    if request.is_json:
        data = request.get_json(force=True) or {}
        inference_json_file = data.get("inferenceJsonFile", "test_inference.json")
        project = data.get("project", "TEST_PROJECT")
    else:
        # Fallback to form data for backward compatibility
        inference_json_file = request.form.get("inferenceJsonFile", "test_inference.json")
        project = request.form.get("project", "TEST_PROJECT")

    inference_test_json, test_summary_str = generate_test_results_json(inference_json_file)
    return render_template(
        "inference_test_table.html",
        json_path=inference_test_json,
        project=project,
        test_summary_str=test_summary_str
    )

def _filter_questions(data, selected_targets):

    filtered_question = {}
    for predicted_value, questions in data["question_json"].items():
        filtered_questions = [question for question in questions if not isinstance(question, dict) or question["field_name"] in selected_targets]
        filtered_question[predicted_value] = filtered_questions


    # TODO: add filters if needed.
    filtered_question_count = data["question_count"]
    filtered_iteration_information = data["iteration_information"]

    return filtered_question, filtered_question_count, filtered_iteration_information

@bp.route("/confirm_predictions", methods=["POST"])
def cluster_predictions(
        input_json,
        clustering_json,
        iter_count=None,
        selected_targets=None,
        selected_types_per_filed=None
):
    if selected_types_per_filed is None:
        selected_types_per_filed = {}

    clustering_progress_dict.update({
        "total": 0,
        "completed": [],
        "in_progress": None,
        "elapsed_time": 0,
        "metadata": None
    })
    inference_json, inferred_fields, metadata_per_field = get_inference_json(input_json, selected_targets)

    # Check if saved clustering file is valid if any
    if os.path.exists(clustering_json):
        with open(clustering_json, 'r', encoding='utf-8') as file:
            data = json.load(file)
            no_abort = data.get("params", {}).get("is_abort", None) is not True
            is_same_target = set(selected_targets).issubset((data.get("params", {}).get("inferred_fields", None)))
            is_same_types_per_field = is_same_target
            for k, v in data.get("params", {}).get("selected_types_per_filed", {}).items():
                is_same_types_per_field = is_same_types_per_field and  selected_types_per_filed.get(k) and set(v) == set(selected_types_per_filed.get(k))
            is_valid =  data.get("iter_count") == iter_count and no_abort and is_same_target and is_same_types_per_field
            if is_valid:
                Logger.info(f"Saved clustering file is valid.")
                filtered_question, filtered_question_count, filtered_iteration_information= _filter_questions(data, selected_targets)
                clustering_progress_dict.update({"total": 1, "completed": [""]})
                out_folder = data["output_folder"]
                params = data["params"]
                iter_count = data["iteration_count"]
                jira_users = data["jira_users"]
                jira_base_url = data["jira_base_url"]
                question_count = filtered_question_count
                iter_info = filtered_iteration_information
                current_app.config["question_json"] = filtered_question
                return out_folder, params, iter_count, jira_users, jira_base_url, question_count, iter_info

    clustering_progress_dict["metadata"] = metadata_per_field
    output_folder = os.path.basename(input_json).replace(".json", "")
    project = os.path.basename(input_json).split('_')[0]
    params = {
        "project": project,
        "input_json": input_json,
        "inference_json": inference_json,
        "output_folder": output_folder,
        "inferred_fields": inferred_fields,
        "clustering_progress_dict": clustering_progress_dict,
        "selected_types_per_filed": selected_types_per_filed
    }
    iteration_count, jira_users, jira_base_url, question_count, iteration_information, clusters_plus_fields = trigger_clustering_process(
        None, params)

    # Save clustering return value
    os.makedirs(Path(clustering_json).parent, exist_ok=True)
    with open(clustering_json, 'w', encoding='utf-8') as f:
        json.dump({
                "output_folder": output_folder,
                "params": params,
                "iteration_count": iteration_count,
                "jira_users": jira_users,
                "jira_base_url": jira_base_url,
                "question_count": question_count,
                "iteration_information": iteration_information,
                "iter_count": iter_count,
                "question_json": clusters_plus_fields
            }, f, indent=4
        )

    return output_folder, params, iteration_count, jira_users, jira_base_url, question_count, iteration_information

@bp.route("/confirm_predictions")
def frank_mockup():

    input_json = request.args.get("db", None)
    if input_json:
        output_folder, params, iteration_count, jira_users, jira_base_url, question_count, iteration_information = cluster_predictions(input_json)
    else:
        config = utils.model_config
        if config is None:
            # Handle None config for testing
            project = "TEST_PROJECT"
            output_folder = "TEST_PROJECT_20230501_120000"
            params = {
                "project": project,
                "output_folder": output_folder,
            }
            # Return default values for testing
            iteration_count = 0
            jira_users = []
            jira_base_url = ""
            question_count = 0
            iteration_information = {
                FID_TOTAL_CONFIDENCE: 0.0,
                FID_TOTAL_ISSUE_COUNT: 0,
                FID_ORPHAN_COUNT: 0
            }
        else:
            project = config.get(CFG_PROJECT, CFG_PROJECT)
            print("[DEBUG] project:", project)
            output_folder = config.get(CFG_OUTPUT_FOLDER, project)
            print("[DEBUG] output_folder:", output_folder)
            params = {
                "project": project,
                "output_folder": output_folder,
            }
            iteration_count, jira_users, jira_base_url, question_count, iteration_information = trigger_clustering_process(
                config)
        print("[DEBUG] question_count:", question_count)
        print("[DEBUG] iteration_information:", iteration_information)

    traceability_list = get_iteration_records_by_project(output_folder)
    # if config != None:
    #     project = config.get(CFG_PROJECT, CFG_PROJECT)
    #     traceability_list = get_iteration_records_by_project(output_folder)

    return render_template("confirm_predictions.html",
                            iter=iteration_count,
                            avg=f"{iteration_information[FID_TOTAL_CONFIDENCE]:.3f}",
                            qst=question_count,
                            total_issue=iteration_information[FID_TOTAL_ISSUE_COUNT] - iteration_information[
                                FID_ORPHAN_COUNT],
                            jira_users=jira_users,
                            jira_base_url=jira_base_url,
                            iteration_information=iteration_information,
                            iterations_data=traceability_list,
                            global_params=params)

def get_best_models_table(best_model_per_field_dict):
    head_html = "<thead><tr><th>Target Field</th><th>ML Model</th><th>Confidence</th><th>F1-Score</th></tr></thead>"
    body_html = ""
    for target_field, dict in best_model_per_field_dict.items():
        ml_model = dict.get("ml_model", None)
        confidence = 100 * dict.get("optimal_confidence", 0)
        fi_score = 100 * dict.get("optimal_confidence_f1_score", 0)
        body_html += f"<tr><td>{target_field}</td><td>{ml_model}</td><td>{confidence:.2f}%</td><td>{fi_score:.2f}%</td></tr>"
    body_html = f"<tbody>{body_html}</tbody>"
    table_html = f'<div class="container"><table class="table table-striped">{head_html}{body_html}</table></div>'
    return f"<pre>{table_html}</pre>"

@bp.route('/get_iteration_progress')
def get_iteration_progress():
    is_abort = inference_threads_progress_dict.get("is_abort", None)
    has_iteration_started = "has_started" in iteration_progress_dict
    if not has_iteration_started:
        inference_threads_progress_dict["is_review_file_usable"] = False
        inference_threads_progress_dict["is_abort"] = None
        iteration_progress_dict.update({
            "1-Testing": {"progress": 0, "start_time": None},
            "2-Inferring": {"progress": 0, "start_time": None},
            "3-Clustering": {"progress": 0, "start_time": None},
        })
        return jsonify(iteration_progress_dict)

    proc_total_progress = 0
    for proc_id in global_inference_processes_progress_dict.get("ml_models", []):
        done_count = len(global_inference_processes_progress_dict[proc_id].get("done", []))
        value_count = global_inference_processes_progress_dict[proc_id].get("value_count", 1)
        proc_progress = done_count / value_count if value_count else 0
        proc_total_progress += proc_progress

    is_testing = global_inference_processes_progress_dict.get("is_testing")
    has_inference_started = "has_inference_started" in iteration_progress_dict

    ml_models_length = len(global_inference_processes_progress_dict.get("ml_models", []))
    inferring_progress = proc_total_progress / ml_models_length if ml_models_length else 0

    # Quick fix: if saved review files are being used
    is_review_file_usable = inference_threads_progress_dict["is_review_file_usable"]
    if not is_testing and is_review_file_usable and inferring_progress == 0 and has_inference_started:
        inferring_progress = 1

    if is_testing and inferring_progress > iteration_progress_dict["1-Testing"]["progress"]:
        iteration_progress_dict["1-Testing"]["progress"] = inferring_progress
    elif is_testing is False or has_inference_started:
        iteration_progress_dict["1-Testing"]["progress"] = 1

    if has_inference_started and inferring_progress > iteration_progress_dict["2-Inferring"]["progress"]:
        iteration_progress_dict["2-Inferring"]["progress"] = inferring_progress
    if not is_abort and iteration_progress_dict["3-Clustering"].get("start_time") is not None:
        iteration_progress_dict["2-Inferring"]["progress"] = 1

    clusterin_progress = len(clustering_progress_dict["completed"]) / (clustering_progress_dict.get("total", 0) or -1)
    clusterin_progress = 0 if iteration_progress_dict["2-Inferring"]["progress"] != 1 else clusterin_progress
    iteration_progress_dict["3-Clustering"]["progress"] = clusterin_progress

    # Add elapsed time
    for key in ["1-Testing", "2-Inferring", "3-Clustering"]:
        start_time = iteration_progress_dict[key].get("start_time", None)
        if start_time:
            stop_time = iteration_progress_dict[key].get("stop_time", time.perf_counter())
            iteration_progress_dict[key]["elapsed"] = elapsed_seconds_to_hms(stop_time - start_time)

    iteration_progress_dict_copy = dict(iteration_progress_dict)
    iteration_progress_dict_copy.pop("has_started", None)
    iteration_progress_dict_copy.pop("has_inference_started", None)
    iteration_progress_dict_copy.pop("target_fields", None)
    iteration_progress_dict_copy.pop("best_model_per_field", None)

    html_description = f"<pre><b>Target fields:</b> [{iteration_progress_dict.get('target_fields', None)}]<pre>"
    best_model_per_field = iteration_progress_dict.get("best_model_per_field", {})
    html_description = get_best_models_table(best_model_per_field) if best_model_per_field else html_description
    wait_message = "You request is being processed, please wait ..."
    stop_message = "Stopping ..."
    # is_abort = inference_threads_progress_dict.get("is_abort", None)
    spinner_wait_message = stop_message if is_abort else wait_message
    active_processes = [p for p in global_inference_processes if p.is_alive()]
    return jsonify({
        "progressbars": iteration_progress_dict_copy,
        "spinner_wait_message": spinner_wait_message,
        "text_description": None,
        "html_description": html_description,
        "active_processes": len(active_processes),
        "is_abort": is_abort
    })

@bp.route('/get_clustering_progress')
def get_clustering_progress():
    # Handle missing keys for testing
    in_progress = clustering_progress_dict.get("in_progress", None)
    total = clustering_progress_dict.get("total", 0)
    completed = clustering_progress_dict.get("completed", [])

    print("[DEBUG] in_progres:", in_progress)
    print("[DEBUG] total:", total)
    print("[DEBUG] completed:", len(clustering_progress_dict["completed"]))
    return jsonify(clustering_progress_dict)

@bp.route('/get_inference_progress')
def get_inference_progress():
    return jsonify(inference_threads_progress_dict)

@bp.route("/abort_ml_predictions", methods=["POST"])
def abort_ml_predictions():
    inference_threads_progress_dict["is_abort"] = True
    Logger.warning(f"sending abort to processes {inference_threads_progress_dict.get("ml_models", [])}")
    for ml_model in inference_threads_progress_dict.get("ml_models", []):
        inference_threads_progress_dict[ml_model]["is_abort"] = True
    return jsonify({}), 200

@bp.route("/abort_iteration", methods=["POST"])
def abort_iteration():
    # Terminate all active processes
    global global_inference_processes
    kill_count = 0
    for process in global_inference_processes:
        Logger.info(f"Terminating process {process.name} (PID {process.pid})")
        process.terminate()
        kill_count += 1
    Logger.info(f"Total terminated processes: {kill_count}")

    if kill_count:
        clustering_progress_dict["is_abort"] = True
        inference_threads_progress_dict["is_abort"] = True
        Logger.warning(f"sending abort to processes {inference_threads_progress_dict.get("ml_models", [])}")
        for ml_model in inference_threads_progress_dict.get("ml_models", []):
            inference_threads_progress_dict[ml_model]["is_abort"] = True

    return jsonify({"kill_count": kill_count}), 200

def elapsed_seconds_to_hms(elapsed_seconds):
    hours, remainder = divmod(elapsed_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

@bp.route('/save_grid_parameters' , methods=["POST"])
def save_grid_parameters():
    data = request.get_json()
    filename = data['filename']
    project_json = f"{DATABASES_FOLDER}/{filename}"
    project = data['filename'].split('_')[0]
    field_gird_dict = json.loads(data['fieldGridDict'])
    accuracy_per_field = field_gird_dict['accuracyPerField'].get(project, {})
    field_gird_path = f'{INFERABILITY_ANALYSIS}/{filename.replace(".json", "_grid.json")}'
    acceptable_labeled_data_ratio = data['labeledDataRatio']
    min_test_data_size = data['minTestDataSize']
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
    return {"project_json": project_json}, 200

@bp.route("/run_inference_iteration", methods=["GET"])
def run_inference_iteration():
    global global_inference_processes_progress_dict
    # Init/Reset progress dicts
    Logger.info(f"Initializing progress ...")
    inference_threads_progress_dict["is_abort"] = False
    inference_threads_progress_dict["is_review_file_usable"] = False
    clustering_progress_dict["is_abort"] = False
    clustering_progress_dict["completed"] = []
    iteration_progress_dict.pop("has_inference_started", None)
    iteration_progress_dict.update({"has_started": True})
    iteration_progress_dict.update({
        "1-Testing": {"progress": 0},
        "2-Inferring": {"progress": 0},
        "3-Clustering": {"progress": 0}
    })
    iteration_progress_dict.update({"best_model_per_field": {}})

    supported_models = "RANDOM_FOREST, LOGISTIC, MLP, SGD, LINEAR_SVC"
    Logger.info(f"supported_models: {supported_models}")
    project_json = request.args["db"]
    project_key = Path(project_json).stem
    selected_target_grid, metadata_per_project = data_pre_analysis.get_saved_target_fields_matrix_per_project()
    selected_target_fields = list(selected_target_grid[project_key].keys())
    disabled_fields = metadata_per_project[project_key]["disabled_fields"]
    selected_target_fields = [field for field in selected_target_fields if field not in disabled_fields]
    predictable_fields = selected_target_fields
    predictable_fields_str = ", ".join(predictable_fields)
    target_fields = predictable_fields_str
    iteration_progress_dict.update({"target_fields": target_fields})
    performance_file = project_json.replace("databases", "performances")
    clustering_file = project_json.replace("databases", "clustering")

    # 1- Run tests to identify the most adequate ML model per field (results JSON saved in 'performances' dir.)
    is_performance_cache = None
    iteration_progress_dict["1-Testing"]["start_time"] = time.perf_counter()
    if Path(performance_file).is_file():
        with open(performance_file, 'r') as file:
            perf_dict = json.load(file)
            is_performance_cache = set(selected_target_fields).issubset(list(perf_dict["best_model_per_field"].keys()))

    if not is_performance_cache:
        Logger.warning(f"{performance_file} unfound or outdated.")
        Logger.info(f"Testing ML models {supported_models} to evaluate performance ...")
        inference_threads_progress_dict["is_testing"] = True
        global_inference_processes_progress_dict["is_testing"] = True
        request_args = {
            "projectJson": project_json,
            "selected_target_grid": selected_target_grid[project_key],
            "targetField": target_fields,
            "mlModel": supported_models,
            "isSplitDataToTest": "true",
            "metadata": metadata_per_project[project_key]   # accuracy threshold
        }
        response, status = run_ml_predictions(request_args)
    else:
        Logger.info(f"Performance file {performance_file} was found.")
    iteration_progress_dict["1-Testing"]["stop_time"] = time.perf_counter()

    # 2- Infer target fields using the most adequate ML model (using JSON saved in 'performances' dir.)
    # predictions are saved in predictions/review
    best_model_dict = {}
    if Path(performance_file).is_file():
        iteration_progress_dict["2-Inferring"]["start_time"] = time.perf_counter()
        Logger.info(f"Predicting target fields {target_fields} ...")
        with open(performance_file, 'r') as file:
            perf_dict = json.load(file)
            best_model_dict = perf_dict["best_model_per_field"]
            iteration_progress_dict["best_model_per_field"] = best_model_dict

        inference_threads_progress_dict["is_testing"] = False
        inference_threads_progress_dict["ml_models"] = []
        global_inference_processes_progress_dict["is_testing"] = False
        global_inference_processes_progress_dict["ml_models"] = []
        iteration_progress_dict.update({"has_inference_started": True})

        request_args = {
            "projectJson": project_json,
            "selected_target_grid": selected_target_grid[project_key],
            "targetField": target_fields,
            "mlModel": supported_models,
            "metadata": metadata_per_project[project_key],
            "best_model_dict": best_model_dict
        }

        # Check saved predictions are usable
        is_review_file_usable = check_saved_review_file_is_usable(request_args)
        inference_threads_progress_dict["is_review_file_usable"] = is_review_file_usable
        if is_review_file_usable:
            Logger.info(f"Saved review file is usable.")
        else:
            run_ml_predictions(request_args)  # Predictions are saved in predictions/review

        iteration_progress_dict["2-Inferring"]["stop_time"] = time.perf_counter()

    # 3- Cluster predictions saved in predictions/review.
    iteration_file = inference_threads_progress_dict.get("iteration_filename", None)
    is_abort = inference_threads_progress_dict.get("is_abort", None)
    Logger.warning(f"iteration_file: {iteration_file}")
    if is_abort and iteration_file:
        iter_file_path = Path(os.path.join(str(ITERATION_FOLDER), iteration_file))
        Logger.warning(f"Removing aborted iteration file: {iter_file_path} ...")
        iter_file_path.unlink(missing_ok=True)
        remove_traceability_entry(project_key, global_trace_entry_data)

    iteration_progress_dict["3-Clustering"]["start_time"] = time.perf_counter()
    Logger.info(f"Clustering confident predictions ...")
    project_basename = Path(project_json).stem
    iteration_count = 1 + len([str(file) for file in Path("iterations").glob(f"*{project_basename}*.json")])
    output_folder, params, _, jira_users, jira_base_url, question_count, iteration_information = cluster_predictions(
        project_json,
        clustering_file,
        iteration_count,
        selected_target_fields,
        selected_target_grid[project_key]
    )
    traceability_list = get_iteration_records_by_project(output_folder)
    iteration_progress_dict["3-Clustering"]["stop_time"] = time.perf_counter()

    # Cosmetic: sync with progress bars (100%)
    sleep_count, max_sleep_time = 0, 5
    while sleep_count < max_sleep_time and iteration_progress_dict.get("3-Clustering", {}).get("progress", 0) < 1:
        time.sleep(1)
        sleep_count += 1
    time.sleep(1)

    # Add perf. info.
    params.update({"best_model_per_field": best_model_dict})
    iteration_progress_dict.pop("has_started", None)
    iteration_progress_dict.pop("has_inference_started", None)
    inference_threads_progress_dict["is_abort"] = False
    if is_abort and  iteration_count == 1 and question_count == 0:
        return redirect("/jira_viewer")

    return render_template("confirm_predictions.html",
                            iter=iteration_count,
                            avg=f"{iteration_information[FID_TOTAL_CONFIDENCE]:.3f}",
                            qst=question_count,
                            total_issue=iteration_information[FID_TOTAL_ISSUE_COUNT] - iteration_information[
                                FID_ORPHAN_COUNT],
                            jira_users=jira_users,
                            jira_base_url=jira_base_url,
                            iteration_information=iteration_information,
                            iterations_data=traceability_list,
                            global_params=params,
                            saved_review_state=get_saved_review_state(project_key, is_abort))


@bp.route("/get_ml_predictions", methods=["GET"])
def start_ml_predictions():
    Logger.debug(f"request.args: {dict(request.args)}")
    return run_ml_predictions(request.args)

def remove_traceability_entry(project_key, trace_entry_data):
    iteration_path = f"{ITERATION_FOLDER}/{TRACEABILITY_ITERATION_TABLE_FILE}.json"
    file_path = Path(iteration_path)
    if file_path.exists() and trace_entry_data:
        timestamp = trace_entry_data["timestamp"]
        questions_number = trace_entry_data["questions_number"]
        with open(file_path, "r", encoding="utf-8") as file:
            traceability_dict = json.load(file)
            iterations = traceability_dict.get(project_key, {}).get("iterations", [])
            if iterations:
                filtered_iterations = [item for item in iterations if item["time_stamp"] != timestamp]
                traceability_dict[project_key]["iterations"] = filtered_iterations

                removed_iterations = [item for item in iterations if item["time_stamp"] == timestamp]
                removed_approved = sum([item["approved"] for item in removed_iterations])
                removed_predictions = sum([item["predictions"] for item in removed_iterations])
                traceability_dict[project_key]["totals"]["approved"] -= removed_approved
                traceability_dict[project_key]["totals"]["predictions"] -= removed_predictions
                traceability_dict[project_key]["totals"]["questions"] -= questions_number

                if  traceability_dict[project_key]["totals"]["approved"] == 0:
                    Logger.warning(f"Removing project_key: {project_key} ...")
                    traceability_dict.pop(project_key, None)

                with open(file_path, "w", encoding="utf-8") as file:
                    json.dump(traceability_dict, file, ensure_ascii=False, indent=4)


def check_saved_review_file_is_usable(request_args):
    target_fields = request_args["targetField"].split(',')
    target_fields = [tf.strip() for tf in target_fields]
    project_basename = Path(request_args["projectJson"]).stem
    iteration_count = 1 + len([str(file) for file in Path("iterations").glob(f"*{project_basename}*.json")])
    review_dir = "predictions/review"
    prediction_file = request_args["projectJson"].replace("databases", review_dir)
    is_usable = False
    if os.path.exists(prediction_file):
        is_usable = True
        with open(prediction_file, "r", encoding="utf-8") as file:
            review_dict = json.load(file)
            metadata = review_dict["metadata"]
            for target_field in target_fields:
                is_usable = is_usable and metadata.get(target_field, {}).get("iteration_count", None) == iteration_count
                selected_types = request_args['selected_target_grid'][target_field]
                saved_selected_types =  metadata.get(target_field, {}).get("selected_target_grid", [])
                is_same_types = set(selected_types) == set(saved_selected_types)
                is_usable = is_usable and is_same_types
    return is_usable


def run_ml_predictions(request_args):
    result_queue = queue.Queue()
    inference_threads_progress_dict["is_abort"] = False
    ml_models = request_args["mlModel"].split(',')
    best_model_dict = request_args.get("best_model_dict", None)
    is_split_data_to_test = request_args.get("isSplitDataToTest", "false") == "true"
    target_fields = request_args["targetField"].split(',')
    proc_count = min(os.cpu_count(), len(ml_models) * len(target_fields))
    proc_count = proc_count if best_model_dict is None else min(os.cpu_count(), len(target_fields))
    proc_indexes = list(range(proc_count))
    proc_names = list(map(lambda x: f"{x}", proc_indexes))
    inference_threads_progress_dict["ml_models"] = proc_names
    for thread_name in proc_names:
        inference_threads_progress_dict[thread_name] = copy.deepcopy(inference_progress_dict)

    request_args_dict = dict(request_args)
    get_ml_predictions(request_args_dict, inference_progress_dict, result_queue)
    is_abort = inference_threads_progress_dict.get("is_abort", None)
    if is_abort:
        return {}, None

    if best_model_dict:
        prediction_dict, _, _, _, _, _, _ = result_queue.get()
        # Remove previous files in any
        review_dir = "predictions/review"
        prediction_file_stem = Path(request_args_dict["projectJson"]).stem
        Logger.info(f"Deleting predictions/review ...")
        for file_path in Path(review_dir).glob(f"*{prediction_file_stem}*"):
            if file_path.is_file():
                Logger.info(f"Deleting review file: {file_path.name} ...")
                file_path.unlink()

        for target_filed, data in prediction_dict.items():
            for ml_model, prediction_list_status in data.items():
                prediction_list, status = prediction_list_status
                prediction_file = request_args_dict["projectJson"].replace("databases", review_dir)
                prediction_file = prediction_file.replace(".json", f"_{target_filed}.json")
                request_args_dict.update({"targetField": target_filed})
                predictions = format_data_to_fit_confirmation_page(prediction_list, request_args_dict)
                min_confidence = best_model_dict.get(target_filed, {}).get("optimal_confidence", 0)
                project_json = request_args["projectJson"]
                selected_types = request_args["selected_target_grid"][target_filed]
                project_basename = Path(project_json).stem
                iteration_count = 1 + len([str(file) for file in Path("iterations").glob(f"*{project_basename}*.json")])
                os.makedirs(review_dir, exist_ok=True)
                with open(prediction_file, "w", encoding="utf-8") as json_file:
                    json.dump({
                        "data": predictions,
                        "metadata": {
                            "min_confidence": min_confidence,
                            "ml_model": ml_model,
                            "iteration_count": iteration_count,
                            "selected_target_grid": selected_types
                        }
                    }, json_file, indent=4)
        return prediction_dict, None

    elif len(target_fields) == 1 and len(ml_models) == 1:
        data, status, accuracy_per_model, f1_score_per_model, optimal_conf_per_model,  optimal_f1_per_model, optimal_percent_per_model = result_queue.get()
        if status == 200:
            Logger.debug(f"accuracy_per_model: {accuracy_per_model}")
            Logger.debug(f"optimal_conf_per_model: {optimal_conf_per_model}")
            Logger.debug(f"optimal_percent_per_model: {optimal_percent_per_model}")
            # Format and save predictions for confirmation page
            if len(ml_models) == 1 and not is_split_data_to_test:
                # TODO: add constants for directories
                out_dir = "predictions/review"
                os.makedirs(out_dir, exist_ok=True)
                prediction_file = request_args_dict["projectJson"].replace("databases", out_dir)
                prediction_file = prediction_file.replace(".json", f"_{request_args_dict['targetField']}.json")
                predictions = format_data_to_fit_confirmation_page(data, request_args_dict)
                Logger.debug(f'request_args_dict["minConfidence"]: {request_args_dict.get("minConfidence", 0)}')
                with open(prediction_file, "w", encoding="utf-8") as json_file:
                    json.dump({
                        "data": predictions,
                        "metadata": {
                            "min_confidence": int(request_args_dict.get("minConfidence", 0)) / 100,
                            "ml_model": request_args_dict["mlModel"]            }
                    }, json_file, indent=4)

            return jsonify({
                "data": data,
                "accuracy_per_model": accuracy_per_model,
                "f1_score_per_model": f1_score_per_model,
                "optimal_conf_per_model": optimal_conf_per_model,
                "optimal_f1_per_model": optimal_f1_per_model,
                "optimal_percent_per_model": optimal_percent_per_model
            }), status
        else:
            return jsonify(data), status
    else:
        # Data per field per model
        prediction_dict, accuracy_dict, f1_score_dict, optimal_conf_dict, optimal_f1_dict, optimal_percent_dict, best_model_per_field = result_queue.get()
        if is_split_data_to_test and not inference_threads_progress_dict["is_abort"]:
            # Save performance per field per model
            # TODO: add constants for directories
            performance_dir = "performances"
            os.makedirs(performance_dir, exist_ok=True)
            performance_file = request_args_dict["projectJson"].replace("databases", performance_dir)
            perf_data = {
                "accuracy": accuracy_dict,
                "f1_score": f1_score_dict,
                "optimal_confidence": optimal_conf_dict,
                "optimal_confidence_f1": optimal_f1_dict,
                "confident_predictions_percentage": optimal_percent_dict,
                "best_model_per_field": best_model_per_field,
                "selected_types_per_field": request_args["selected_target_grid"]
            }

            with open(performance_file, 'w', encoding='utf-8') as f:
                json.dump(perf_data, f, indent=4, ensure_ascii=False)

        return jsonify({"err_msg": "Multiple Target Fields!"}), 500


# @bp.route("/get_ml_predictions", methods=["GET"])
def get_ml_predictions(request_args_dict, inference_progress_dict, result_queue):
    ml_models = request_args_dict["mlModel"]
    inference_progress_dict["ml_progress"] = None
    inference_progress_dict["ml_progress"] = 0
    ml_models_list = ml_models.split(',')
    best_model_dict = request_args_dict.get("best_model_dict", None)
    Logger.info(f"Running multiple ML models: {ml_models_list}")
    first_ml_predictions_per_field, best_ml_predictions_per_field, shown_ml_predictions_per_field = {}, {}, {}
    accuracy_per_field_per_model = {}
    fi_score_per_field_per_model = {}
    optimal_confidence_per_field_per_model = {}
    optimal_f1_score_per_field_per_model = {}
    optimal_precent_per_field_per_model = {}
    best_model_per_field = {}

    predictions_per_field_per_model = run_inference_processes(ml_models_list, request_args_dict)
    is_abort = inference_threads_progress_dict.get("is_abort", None)
    if is_abort:
        return

    for target_field, predictions_per_model in predictions_per_field_per_model.items():
        best_ml_score = None
        accuracy_per_field_per_model[target_field] = {}
        fi_score_per_field_per_model[target_field] = {}
        optimal_f1_score_per_field_per_model[target_field] = {}
        optimal_confidence_per_field_per_model[target_field] = {}
        optimal_precent_per_field_per_model[target_field] = {}
        for ml_model, ml_predictions in predictions_per_model.items():
            acceptable_accuracy_per_field = request_args_dict.get("metadata", {}).get("accuracy_per_field", {})
            acceptable_accuracy = acceptable_accuracy_per_field.get(target_field, 90) or 90
            acceptable_labeled_data_ratio = request_args_dict.get("metadata", {}).get("acceptable_labeled_data_ratio", 10)
            Logger.debug(f"{target_field} acceptable_accuracy: {acceptable_accuracy}")
            Logger.debug(f"{target_field} acceptable_labeled_data_ratio: {acceptable_labeled_data_ratio}")
            perf_metrics = compute_predictions_accuracy(
                ml_predictions[0],
                25,
                int(acceptable_accuracy) / 100,
            )

            # During benchmark/test runs, use out-of-fold CV to choose the
            # winning classifier. The legacy 80/20 split remains available for
            # the UI test report, but no longer decides model selection alone.
            cv_metrics = None
            if request_args_dict.get("isSplitDataToTest", "false") == "true":
                try:
                    with open(
                        request_args_dict["projectJson"],
                        "r",
                        encoding="utf-8",
                    ) as cv_file:
                        cv_issues = json.load(cv_file)

                    selected_types = request_args_dict.get(
                        "selected_target_grid", {}
                    ).get(target_field, [])
                    if selected_types:
                        cv_issues = [
                            issue
                            for issue in cv_issues
                            if issue.get("issuetype") in selected_types
                        ]

                    struct_fields = [
                        field.strip()
                        for field in request_args_dict.get(
                            "sFields", ""
                        ).split(",")
                        if field.strip()
                        and field.strip() != target_field
                    ]
                    cv_metrics = evaluate_model_cv(
                        cv_issues,
                        model_type=SupportedModels[ml_model].value,
                        target_field=target_field,
                        structured_fields=struct_fields,
                        n_splits=5,
                        target_score=int(acceptable_accuracy) / 100,
                    )
                    if cv_metrics.get("status") != "ok":
                        cv_metrics = None
                except Exception as exc:
                    Logger.error(
                        "Cross-validation failed for "
                        f"{target_field}/{ml_model}: {exc}"
                    )

            if cv_metrics:
                cv_base = cv_metrics["metrics"]
                reported_accuracy = cv_base.get(
                    "jaccard_samples",
                    cv_base.get("balanced_accuracy")
                    or cv_base.get("accuracy"),
                )
                reported_f1 = cv_base.get(
                    "f1_macro",
                    cv_base.get("f1_micro", 0.0),
                )
                optimal_confidence = cv_metrics[
                    "optimal_confidence"
                ]
                optim_f1_score = reported_f1
                optim_percent = 100 * cv_metrics["coverage"]
                meets_target = cv_metrics["meets_target"]
                # Business objective: meet quality first, then maximise
                # automation coverage, then F1 and balanced/Jaccard accuracy.
                ml_score = (
                    int(meets_target),
                    cv_metrics["coverage"],
                    reported_f1,
                    reported_accuracy or 0.0,
                )
            else:
                reported_accuracy = perf_metrics.get(
                    "basic_accuracy", 0.0
                )
                reported_f1 = perf_metrics.get("f1_score", 0.0)
                optimal_confidence = perf_metrics.get(
                    "optimal_confidence", 0.0
                )
                optim_f1_score = perf_metrics.get(
                    "optimal_f1_score", 0.0
                )
                optim_percent = perf_metrics.get(
                    "optimal_confidence_predictions_precent",
                    0.0,
                )
                meets_target = perf_metrics.get(
                    "meets_target_accuracy", False
                )
                ml_score = (
                    int(bool(meets_target)),
                    optim_percent / 100,
                    optim_f1_score,
                    reported_accuracy or 0.0,
                )

            accuracy_per_field_per_model[target_field][
                ml_model
            ] = reported_accuracy
            fi_score_per_field_per_model[target_field][
                ml_model
            ] = reported_f1
            optimal_confidence_per_field_per_model[target_field][
                ml_model
            ] = optimal_confidence
            optimal_f1_score_per_field_per_model[target_field][
                ml_model
            ] = optim_f1_score
            optimal_precent_per_field_per_model[target_field][
                ml_model
            ] = optim_percent

            accuracy_per_confidence = perf_metrics.get(
                "accuracy_per_confidence", None
            )
            first_ml_model = next(iter(predictions_per_model))
            first_ml_predictions_per_field[target_field] = (
                ml_predictions
                if ml_model == first_ml_model
                else first_ml_predictions_per_field
            )
            if best_ml_score is None or ml_score > best_ml_score:
                best_ml_score = ml_score
                best_ml_predictions_per_field[
                    target_field
                ] = ml_predictions
                best_model_per_field[target_field] = {
                    "ml_model": ml_model,
                    "optimal_confidence": optimal_confidence,
                    "optimal_confidence_f1_score": (
                        optim_f1_score
                    ),
                    "confident_predictions_percentage": (
                        optim_percent
                    ),
                    "accuracy_per_confidence": (
                        accuracy_per_confidence
                    ),
                    "cross_validation": cv_metrics,
                }

        if best_ml_predictions_per_field.get(target_field, None) is None:
            shown_ml_predictions_per_field[target_field] = first_ml_predictions_per_field.get(target_field, None)
        else:
            shown_ml_predictions_per_field[target_field] = best_ml_predictions_per_field.get(target_field)

    target_field_list = list(predictions_per_field_per_model.keys())
    Logger.debug(f"predictions_per_field_per_model: {predictions_per_field_per_model}")
    ml_model_list = predictions_per_field_per_model[target_field_list[0]].keys() if target_field_list else []
    if best_model_dict is None and len(target_field_list) == 1 and len(ml_model_list) == 1:
        target_field = list(predictions_per_field_per_model.keys())[0]
        if isinstance(shown_ml_predictions_per_field[target_field], tuple):
            data, status = shown_ml_predictions_per_field[target_field]
        else:
            Logger.debug(f"shown_ml_predictions_per_field[target_field]: {shown_ml_predictions_per_field[target_field]}")
            data, status = list(predictions_per_field_per_model[target_field].values())[0]
        result_queue.put((data,
                          status,
                          accuracy_per_field_per_model[target_field],
                          fi_score_per_field_per_model[target_field],
                          optimal_confidence_per_field_per_model[target_field],
                          optimal_f1_score_per_field_per_model[target_field],
                          optimal_precent_per_field_per_model[target_field]
                          ))
    else:
        result_queue.put((predictions_per_field_per_model,
                          accuracy_per_field_per_model,
                          fi_score_per_field_per_model,
                          optimal_confidence_per_field_per_model,
                          optimal_f1_score_per_field_per_model,
                          optimal_precent_per_field_per_model,
                          best_model_per_field
                          ))

def wrapper(
        proc_index,
        ml_list_to_process_lock,
        predictions_per_field_per_model,
        ml_list_to_process,
        ml_models,
        request_args_dict,
        inference_threads_progress_dict
):

    while True:
        idx, target_field = None, None
        with ml_list_to_process_lock:
            if ml_list_to_process:
                Logger.debug(f"ml_list_to_process: {ml_list_to_process}")
                idx, target_field = ml_list_to_process.pop(0)
                ml_model = ml_models[idx]
                if target_field not in predictions_per_field_per_model:
                    predictions_per_field_per_model[target_field] = {}
        if  idx is None:
            break
        else:
            # ml_model = ml_models[idx]
            new_request_args_dict= copy.deepcopy(request_args_dict)
            new_request_args_dict["mlModel"] = ml_model
            new_request_args_dict["targetField"] = target_field
            new_request_args_dict["lock"] = ml_list_to_process_lock

            # proc_index = f"{idx}_{target_field}"
            # if proc_index not in inference_threads_progress_dict:
            #     inference_threads_progress_dict[f"{proc_index}"] = multiprocessing.Manager().dict()
            # inference_threads_progress_dict[f"{proc_index}"]["ml_progress"] = 0
            # inference_threads_progress_dict[f"{proc_index}"]["value_count"] = 0
            # inference_threads_progress_dict[f"{proc_index}"]["done"] = []
            # inference_threads_progress_dict[f"{proc_index}"]["in_progress"] = None
            Logger.info(f"Running process {proc_index}: ml_model {ml_model}, target_field {target_field}")
            inference_threads_progress_dict[f"{proc_index}"] = {}
            ml_predictions = get_ml_predictions__(new_request_args_dict,
                                                  inference_threads_progress_dict, f"{proc_index}")
            Logger.debug(
                f"target_field: {target_field}, ml_model: {ml_models[idx].strip()}, len(ml_predictions[0]): {len(ml_predictions[0])}")
            local_inner = predictions_per_field_per_model[target_field]
            local_inner[ml_models[idx].strip()] = ml_predictions
            with ml_list_to_process_lock:
                predictions_per_field_per_model[target_field] = local_inner

def run_inference_processes(ml_models, request_args_dict):
    global global_inference_processes_progress_dict
    global global_inference_processes
    global_inference_processes = []
    target_fields = request_args_dict["targetField"].replace(' ', '').split(',')
    best_model_dict = request_args_dict.get("best_model_dict", None)
    ml_list_to_process = []
    for target_field in target_fields:
        if best_model_dict is None:
            for ml_index in list(range(len(ml_models))):
                ml_list_to_process.append((ml_index, target_field))
        else:
            Logger.info(f"best_model_dict.keys(): {best_model_dict.keys()}")
            if target_field in best_model_dict:
                best_model = best_model_dict[target_field]["ml_model"]
                best_model_index = [x.strip() for x in ml_models].index(best_model)
                ml_list_to_process.append((best_model_index, target_field))
            else:
                Logger.error(f"{target_field} not in best_model_dict!")
    ml_list_to_process_lock =  multiprocessing.Lock()

    # Create processes
    manager = multiprocessing.Manager()
    global_predictions_per_field_per_model = manager.dict()
    global_ml_list_to_process =  manager.list(ml_list_to_process)
    global_ml_models = manager.list(ml_models)
    global_request_args_dict = manager.dict(request_args_dict)
    proc_count = min(os.cpu_count(), len(ml_list_to_process))
    start_time = time.perf_counter()

    global_inference_processes_progress_dict = manager.dict(inference_threads_progress_dict)
    for proc_index in range(proc_count):
        manager_dict = manager.dict({"ml_progress": 0, "value_count": 0, "done": [], "in_progress": None})
        global_inference_processes_progress_dict.update({str(proc_index): manager_dict})

        proc = multiprocessing.Process(
            target=wrapper,
            args=(
                proc_index,
                ml_list_to_process_lock,
                global_predictions_per_field_per_model,
                global_ml_list_to_process,
                global_ml_models,
                global_request_args_dict,
                global_inference_processes_progress_dict
            ))

        global_inference_processes.append(proc)
        Logger.info(f"Starting process {proc_index} name: {proc.name} ...")
        proc.start()

    # Wait for all processes to finish
    for proc in global_inference_processes:
        proc.join()

    print(f"\nAll processes completed. (elapsed: {int(time.perf_counter() - start_time)} sec.)")

    return global_predictions_per_field_per_model

def get_ml_predictions__(request_args, progress_dict=None, proc_index=None):

    lock = request_args["lock"]
    with lock:
        inference_progress_dict_ = progress_dict[proc_index]
        inference_progress_dict_.update({
            "value_count": 0,
            "done": [],
            "in_progress": None
        })
        progress_dict[proc_index] = inference_progress_dict_

    is_target_field_a_list = False
    try:
        target_field = request_args["targetField"]
        project_json = request_args["projectJson"]
        is_apply_inheritance = request_args.get("isApplyInheritanceRules", "false") == "true"
        target_issue_key = request_args.get("issueKey", None)
        is_split_data_to_test = request_args.get("isSplitDataToTest", "false") == "true"
        is_llm = request_args.get("isLlm", "false") == "true"
        request_args_dict = dict(request_args)

        # TODO: add endpoints to GET LLM json file
        with open(project_json, 'r', encoding='utf-8') as file:
            jira_issues = json.load(file)

            # Expose jira_issues reference
            inference_progress_dict_["jira_issues"] = jira_issues
            progress_dict[proc_index] = inference_progress_dict_

            # Apply iterations
            iter_dir = str(Path(project_json).parent).replace("databases", "iterations")
            rejected_predictions = apply_iterations(jira_issues, Path(project_json).stem, iter_dir)
            # print("[DEBUG] rejected_predictions:", rejected_predictions)

            is_target_field_a_list = isinstance(jira_issues[0][target_field], list)
            if is_llm:
                Logger.info("Injecting LLM summary & description ...")
                llm_desc_count = len(list(filter(lambda x: "generated_description" in x, jira_issues)))
                llm_sum_count = len(list(filter(lambda x: "generated_summary" in x, jira_issues)))
                for jira_issue in jira_issues:
                    if jira_issue.get("generated_summary_confidence", 0) > 0:
                        jira_issue["summary"] = jira_issue.get("generated_summary", "summary")
                    if jira_issue.get("generated_description_confidence", 0) > 0:
                        jira_issue["description"] = jira_issue.get("generated_description", "description")

        if is_target_field_a_list:
            inference_progress_dict_["is_multi"] = True
            progress_dict[proc_index] = inference_progress_dict_
            possible_values_tuple = get_target_field_possible_values(project_json,[target_field])
            possible_values = possible_values_tuple[0][f"{target_field}_values"]
            flattened_possible_values = [item for sublist in possible_values for item in sublist]
            unique_flattened_possible_values = list(set(flattened_possible_values))

            # Inheritance
            inheritance_rules = []
            inheritance_predictions = []
            if is_apply_inheritance:
                Logger.debug(f"Getting inheritance rules ...")
                inheritance_rules = data_pre_analysis.get_inheritance_rules(jira_issues, fields=[target_field])
                Logger.debug(f"inheritance_rules: {inheritance_rules}")
            if inheritance_rules:
                Logger.info(f"[DEBUG] Applying inheritance rules ...")
                updated_issues_per_filed = data_pre_analysis.apply_inheritance_rules(
                    jira_issues,
                    matching_rules_per_field=inheritance_rules
                )
                inheritance_predictions = updated_issues_per_filed.get(target_field, [])

            # Random tests
            test_data = []
            if is_split_data_to_test:
                labeled_data = list(filter(lambda x: x[target_field], jira_issues))
                test_data = select_random_issues_from_train_issues_to_test_inference(
                    labeled_data,
                    target_field,
                    test_issues_percentage=0.2, # Test data size is 20% of labeled data
                    test_rand_seed=912,
                    issues_to_exclude=None  # [("issuetype", "Epic")]
                )
                test_data = list(map(lambda x: {"key": x["key"], target_field: x[target_field]}, test_data))

                # unset test_data items to be considered unlabeled data
                for test_item in test_data:
                    jira_issue = list(filter(lambda x: x["key"] == test_item["key"], jira_issues))[0]
                    jira_issue[target_field] = []

            jira_issues = list_items_to_boolean_fields(jira_issues, flattened_possible_values, target_field)

            predictions_per_value = {}
            inference_progress_dict_["value_count"] = len(unique_flattened_possible_values)
            progress_dict[proc_index] = inference_progress_dict_
            start_time = time.perf_counter()
            for value in unique_flattened_possible_values:
                # Abort if needed
                if inference_progress_dict_.get("is_abort", None):
                    break

                Logger.debug(f"Processing target_value: {value}")
                inference_progress_dict_["in_progress"] = f"{value}|{request_args['mlModel']}"
                progress_dict[proc_index] = inference_progress_dict_
                # DEBUG
                labeled_data = list(filter(lambda x: x[target_field], jira_issues))
                Logger.debug(f"len(labeled_data): {len(labeled_data)}")
                # Bugfix: Error message: The number of classes has to be greater than one; got 1 class
                classes = list(map(lambda x: x[value], jira_issues))
                classes = list(filter(lambda x: x, classes))
                classes_unique = list(set(classes))

                if len(classes_unique) > 1:
                    ml_predictions = get_ml_predictions_(
                        request_args_dict, jira_issues,
                        target_value=value,
                        is_target_field_a_list=is_target_field_a_list,
                        actual_target_field=target_field
                    )
                    predictions_per_value[value] = ml_predictions
                else:
                    Logger.debug(f"value '{value}' is skipped.")

                with lock:
                    inference_progress_dict_ = progress_dict[proc_index]
                    inference_progress_dict_["done"].append(value)
                    inference_progress_dict_["elapsed_time"] = int(time.perf_counter() - start_time)
                    progress_dict[proc_index] = inference_progress_dict_

            prediction_list = boolean_fields_to_list(
                predictions_per_value
            )

            # Tag rejected to exclude them in the clustering phase
            tag_count = tag_rejected_predictions(target_field, prediction_list, rejected_predictions)
            Logger.debug(f"'{target_field}' previously rejected count: {tag_count}")

            # Append Inheritance predictions:
            i_prediction_list = []
            for inheritance_prediction in inheritance_predictions:
                match_list = list(filter(lambda x: x["issue_key"] == inheritance_prediction[0], prediction_list))
                if len(match_list) == 0:
                    Logger.debug(f"Appending inheritance_prediction: {inheritance_prediction[0]}")
                    new_item = prediction_list[0].copy()
                    new_item.update({
                        "issue_key": inheritance_prediction[0],
                        "prediction": inheritance_prediction[1],
                        "confidence": 1.0,
                        "prediction_source": "inheritance_rule"
                    })
                    i_prediction_list.append(new_item)
                else:
                    Logger.debug(f"[DEBUG] {inheritance_prediction[0]} already exists")
                    match_list[0]["confidence"] = 1.0
                    match_list[0]["prediction_source"] = "inheritance_rule"

            prediction_list.extend(i_prediction_list)
            if is_split_data_to_test:
                test_data_keys = list(map(lambda x: x["key"], test_data))
                for prediction in prediction_list:
                    if prediction["issue_key"] in test_data_keys:
                        test = list(filter(lambda x: x["key"] == prediction["issue_key"], test_data))[0]
                        prediction["expected"] = test[target_field]
                        prediction["is_split_test"] = True
                        prediction["accuracy_score"] = compute_list_accuracy_score(
                            expected_list=test[target_field],
                            actual_list=prediction["prediction"]
                        )
                        prediction["confident_accuracy_score"] = compute_list_accuracy_score(
                            expected_list=test[target_field],
                            actual_list=prediction.get("confident_prediction", [])
                        )

            if target_issue_key:
                prediction_list = list(filter(lambda x: x["issue_key"] == target_issue_key, prediction_list))
                issue_dict = prediction_list[0]
                issue_key_prediction = {
                    "prediction": issue_dict["prediction"],
                    "confidence": issue_dict["confidence"],
                    "confidence_list": issue_dict["confidence_list"],
                    "expected": issue_dict["expected"],
                    "model": issue_dict["model"],
                    "accuracy": issue_dict["accuracy"],
                    "accuracy_score": issue_dict.get("accuracy_score", None),
                    "is_split_test": issue_dict["is_split_test"]
                }
                return issue_key_prediction, 200
            return prediction_list, 200

        else:
            inference_progress_dict_["is_multi"] = False
            inference_progress_dict_["value_count"] = 1
            inference_progress_dict_["in_progress"] = f"{target_field}|{request_args['mlModel']}"
            progress_dict[proc_index] = inference_progress_dict_
            start_time = time.perf_counter()
            predictions =  get_ml_predictions_(request_args, jira_issues)

            # Tag rejected to exclude them in the clustering phase
            tag_count = tag_rejected_predictions(target_field, predictions, rejected_predictions)
            Logger.debug(f"'{target_field}' previously rejected count: {tag_count}")
            with lock:
                inference_progress_dict_ = progress_dict[proc_index]
                inference_progress_dict_["done"].append(target_field)
                inference_progress_dict_["elapsed_time"] = int(time.perf_counter() - start_time)
                progress_dict[proc_index] = inference_progress_dict_
            return predictions, 200

    except Exception as e:
        traceback.print_exc()
        Logger.error(f"Exception: {e}")
        return {"err_msg": str(e)}, 500

def get_ml_predictions_(
        request_args, jira_issues,
        target_value=None,
        is_target_field_a_list=False,
        actual_target_field=None
):
    ml_model = request_args["mlModel"].strip()
    target_issue_key = request_args.get("issueKey", None)
    target_field = request_args["targetField"] if target_value is None else target_value
    selected_target_grid = request_args["selected_target_grid"]
    project_json = request_args["projectJson"]
    gold_project_json = request_args.get("goldProjectJson", "")
    is_llm = request_args.get("isLlm", "false") == "true"
    Logger.debug(f"project_json: {project_json}")
    Logger.debug(f"is_llm: {is_llm}")
    is_apply_inheritance = request_args.get("isApplyInheritanceRules", "false") == "true"
    is_apply_inheritance_by_caller = is_apply_inheritance
    Logger.debug(f"is_apply_inheritance: {is_apply_inheritance}")
    struct_fields = [
        field.strip()
        for field in request_args.get("sFields", "").split(",")
        if field.strip()
    ]
    struct_fields.sort()
    Logger.debug(f"struct_fields: {struct_fields}")
    is_split_data_to_test = request_args.get("isSplitDataToTest", "false") == "true"
    Logger.debug(f"is_split_data_to_test: {is_split_data_to_test}")

    struct_fields_suffix = "" if not struct_fields else '_'.join(struct_fields)
    struct_fields_suffix = "" if not struct_fields_suffix else f"_{struct_fields_suffix}"
    llm_suffix = "" if not is_llm else f"_llm"
    split_data_suffix = "" if not is_split_data_to_test else f"_test"
    tf_suffix = f"_{target_field.replace(' ', '')}"
    prediction_file_suffix = f"_predictions{tf_suffix}{struct_fields_suffix}{split_data_suffix}{llm_suffix}"
    test_file_suffix = f"_tests{struct_fields_suffix}{llm_suffix}"
    project_predictions_json = project_json.replace(".json", f"{prediction_file_suffix}.json")
    project_tests_json = project_json.replace(".json", f"{test_file_suffix}.json")
    prediction_subfolder = f"{PREDICTIONS_FOLDER}/{Path(project_json).stem}/{SupportedModels[ml_model].value}"
    os.makedirs(prediction_subfolder, exist_ok=True)
    project_predictions_json = project_predictions_json.replace(DATABASES_FOLDER, prediction_subfolder)
    project_tests_json = project_tests_json.replace(DATABASES_FOLDER, prediction_subfolder)
    # Tests and selective inference are handled by the caller function for multi-value fields
    if is_target_field_a_list:
        target_issue_key = None
        is_split_data_to_test = False

    if is_apply_inheritance:
        project_predictions_json = project_predictions_json.replace(f".json", "_i.json")
        project_tests_json = project_tests_json.replace(f".json", "_i.json")
        is_apply_inheritance = False if is_target_field_a_list else is_apply_inheritance

    project_predictions = {}
    project_test_data = {}
    if os.path.exists(project_predictions_json):
        modification_timestamp = os.path.getmtime(project_json)
        with open(project_predictions_json, 'r', encoding='utf-8') as file:
            project_predictions = json.load(file)
            labeled_data_size = len([i for i in jira_issues if target_field in i and i[target_field]])
            if modification_timestamp != project_predictions["timestamp"]:
                Logger.debug("timestamps mismatch!")
                project_predictions = {}
            elif labeled_data_size != project_predictions["labeled_data_size"]:
                Logger.debug("labeled_data_size mismatch!")
                project_predictions = {}
            else:
                Logger.debug("[DEBUG] timestamps & labeled_data_size match!")

        if is_split_data_to_test:
            if False and os.path.exists(project_tests_json):
                with open(project_tests_json, 'r', encoding='utf-8') as file:
                    project_test_data = json.load(file)
            else:
                project_test_data[ml_model] = {}

    train_predict_time = 0
    labeled_data_size, unlabeled_data_size = None, None
    selected_model_name, selected_model_accuracy = (ml_model, None)

    is_use_saved_predictions = project_predictions and ml_model in project_predictions and target_field in project_predictions[ml_model]
    Logger.debug(f"is_use_saved_predictions: {is_use_saved_predictions}")
    if not is_use_saved_predictions:
        start_time = time.perf_counter()
        Logger.info(f"Inferring field '{target_field}' using ML model '{ml_model}' ...")
        if ml_model in project_predictions:
            project_predictions[ml_model][target_field] = {}
            if is_split_data_to_test:
                if ml_model not in project_test_data:
                    project_test_data[ml_model] = {}
                project_test_data[ml_model][target_field] = {}
        else:
            project_predictions[ml_model] = {}
            if is_split_data_to_test:
                project_test_data[ml_model] = {}
        inheritance_predictions = []

        target_fields = ["epic_link", "components", "labels", "priority", "team"]
        inheritance_rules = []
        if is_apply_inheritance:
            Logger.info(f"[DEBUG] Getting inheritance rules ...")
            inheritance_rules = data_pre_analysis.get_inheritance_rules(jira_issues, fields=target_fields)

        if inheritance_rules:
            Logger.info(f"[DEBUG] Applying inheritance rules ...")
            updated_issues_per_filed = data_pre_analysis.apply_inheritance_rules(
                jira_issues,
                matching_rules_per_field=inheritance_rules
            )
            inheritance_predictions = updated_issues_per_filed.get(target_field, [])

        inheritance_keys = list(map(lambda x: x[0], inheritance_predictions))
        inheritance_keys_uniq = list(set(inheritance_keys))
        Logger.debug(f"len(inheritance_keys): {len(inheritance_keys)}")
        Logger.debug(f"len(inheritance_keys_uniq): {len(inheritance_keys_uniq)}")

        labeled_data_size = len([i for i in jira_issues if target_field in i and i[target_field]])
        unlabeled_data_size = len([i for i in jira_issues if target_field in i and not i[target_field]])
        issues_to_exclude = [("issuetype", "Epic")] if target_field == "epic_link" else None

        # Make sure pushed/sent items are applied to be used as labeled data
        applied_sent_items = apply_sent_items_if_needed(jira_issues, project_json)
        Logger.debug(f"applied_sent_items: {applied_sent_items}")

        # TODO: filter jira_issues according to selected issue types
        selected_issue_type = selected_target_grid.get(actual_target_field if actual_target_field else target_field)
        Logger.info(f"Filtering jira_issues according to {target_field}'s selected types: {selected_issue_type}")
        Logger.info(f"Unfiltered jira_issues: {len(jira_issues)}")
        jira_issues = [item for item in jira_issues if item["issuetype"] in selected_issue_type]
        Logger.info(f"Filtered jira_issues: {len(jira_issues)}")
        predictions = infer_using_model(
            jira_issues,
            model_type=SupportedModels[selected_model_name].value,
            target_field=target_field,
            structured_fields=struct_fields,
            issues_to_exclude=issues_to_exclude,
            is_test=is_split_data_to_test,
            test_rand_seed = 911
        )
        # Add inheritance predications
        predictions[0].extend(inheritance_predictions)
        prediction_keys = list(map(lambda x: x[0], predictions[0]))
        prediction_keys_uniq = list(set(prediction_keys))

        test_data = predictions[3]
        if is_split_data_to_test:
            test_data = list(map(lambda x: [x["key"], x[target_field], 1.1], test_data))

        project_predictions[ml_model][target_field] = predictions
        project_predictions["timestamp"] = os.path.getmtime(project_json) if os.path.exists(project_json) else 0
        project_predictions["labeled_data_size"] = labeled_data_size

        if is_split_data_to_test:
            project_test_data[ml_model][target_field] = test_data

        # Save/Update prediction file
        with open(project_predictions_json, "w", encoding="utf-8") as f:
            json.dump(project_predictions, f, indent=4)  # indent for pretty-printing

        # Save/Update test file
        if is_split_data_to_test:
            with open(project_tests_json, "w", encoding="utf-8") as f:
                json.dump(project_test_data, f, indent=4)  # indent for pretty-printing

        end_time = time.perf_counter()
        train_predict_time = end_time - start_time
        Logger.info(f"ML Train/Predict time: {train_predict_time:.6f} seconds")

    prediction = None
    confidence = None
    predictions = project_predictions[ml_model][target_field]
    Logger.debug(f"Nmber of predictions: {len(predictions[0])}")

    prediction_dicts = []

    gold_db_json = gold_project_json
    gold_db = gold_db_json.replace(f"{DATABASES_FOLDER}/", "").split('_')[0]
    trunc_db = project_json.replace(f"{DATABASES_FOLDER}/", "").split('_')[0]

    if os.path.exists(gold_db_json):
        with open(gold_db_json, 'r', encoding='utf-8') as file:
            gold_jira_issues = json.load(file)
    else:
        gold_jira_issues = []

    for prediction_tuple in predictions[0]:
        issue_key = prediction_tuple[0]
        if prediction_tuple:
            prediction = prediction_tuple[1]
            confidence = prediction_tuple[2]

        # Add Expected values from Gold DB
        expected_value = None
        is_split_test = None
        if gold_db:
            gold_issue_key = issue_key.replace(trunc_db, gold_db)
            gold_issues = list(filter(lambda x: x["key"] == gold_issue_key, gold_jira_issues))
            gold_issue = gold_issues[0] if len(gold_issues) == 1 else {}
            is_split_test = False
            expected_value = gold_issue.get(target_field, None)
            if expected_value is not None and target_field == "epic_link":
                expected_value = str(expected_value).replace(gold_db, trunc_db)

        elif is_split_data_to_test:
            project_test_data[ml_model][target_field] = list(
                map(lambda x: [x["key"], x[target_field], 1.1], predictions[3]))
            split_test_dicts = list(filter(lambda x: x[0] == issue_key, project_test_data[ml_model][target_field]))
            if split_test_dicts:
                is_split_test = True
                expected_value = split_test_dicts[0][1]

        # TODO: separate model-related info
        prediction_dicts.append({
                                    "issue_key": issue_key,
                                    "prediction": prediction,
                                    "confidence": confidence,
                                    "expected": expected_value,
                                    "model": selected_model_name,
                                    "accuracy": selected_model_accuracy,
                                    "labeled_data_size": labeled_data_size,
                                    "unlabeled_data_size": unlabeled_data_size,
                                    "train_predict_time": f"{train_predict_time:.3f} sec",
                                    "is_apply_inheritance": is_apply_inheritance_by_caller,
                                    "is_split_test": is_split_test,
                                    "is_llm": is_llm
                                }
        )
        prediction_dicts = list({d['issue_key']: d for d in prediction_dicts}.values())

    if target_issue_key is None:
        return prediction_dicts
    else:
        issue_dict = list(filter(lambda x: x["issue_key"] == target_issue_key, prediction_dicts))[0]
        issue_key_prediction = {
            "prediction": issue_dict["prediction"],
            "confidence": issue_dict["confidence"],
            "expected": issue_dict["expected"],
            "model": issue_dict["model"],
            "accuracy": issue_dict["accuracy"],
            "is_split_test": issue_dict["is_split_test"]
        }
        return issue_key_prediction
