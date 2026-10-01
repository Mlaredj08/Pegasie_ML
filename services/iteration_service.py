import glob

from flask import current_app, jsonify, request
import os
import pandas as pd
import json
from datetime import datetime
from collections import defaultdict
import utils_pkg as utils
from config import IFC_QUESTION_INDEX, ITERATION_READY_TO_SEND, FIELD_COMPLETION_FOLDER
from config.logger import Logger
# from reporting.audit_generator import get_missing_data_by_field
import reporting
from services.clustering_service import cluster_predictions
from config.constants import IRO_ITERATION, CFG_INPUT_FILE, FID_APPROVED, IRO_QUESTIONS, ARO_INCOMPLETE, IRO_REJECTED, \
    SAVED_ITERATION_FOLDER, IFC_TAGGED_ISSUE_KEYS, IRO_PUSHED
from pathlib import Path
from config.constants import CFG_INPUT_FILE, IRO_FIELD, FID_ISSUE_COUNT, FID_TOTAL_ISSUE_COUNT, FID_AVG_ACCURACY, \
    FID_TOTAL_CONFIDENCE, FID_ORPHAN_COUNT, \
    FID_QUESTION_COUNT, DEPENDENCY_MODEL_FOLDER, FID_AVAILABLE_ISSUES, IFC_ORIGINAL_VALUE, \
    TRACEABILITY_ITERATION_TABLE_FILE, JIRA_USERS_FILE, DATABASES_SETTINGS_FOLDER, \
    CFG_PROJECT, IFC_STATUS, FQS_PREDICTED_VALUE, IRO_CUMULATIVE_APPROVED, CFG_OUTPUT_FOLDER, IRO_USER, \
    IFC_CHANGED_KEYWORDS_LIST, IFC_NEW_KEYWORDS, \
    CFG_FIELD_MODELS, IRO_QUESTIONS_NUMBER, CFG_CONFIDENCE_FIELD, INFERENCE_OUT_FILE_SUFFIX, AUDIT_OUT_FILE_SUFFIX, \
    ITERATION_FOLDER, IRO_ITERATION, IRO_TIME_STAMP, \
    IRO_PREDICTIONS, IRO_CONFIDENCE, IRO_APPROVED, IRO_REMAINING, IRO_COMPLETION, IFC_TIME_STAMP, IFC_USER, \
    IFC_TARGET_FIELDS, IFC_VALUE, IFC_ISSUE_KEYS, IFC_KEYWORDS, \
    IFC_FIELD_NAME, IFC_PREDICTIONS
from services.processing_data_service import group_predictions_from_inferred
from utils_pkg.text_utils import extract_issue_key, extract_question_id_and_issue_key


def apply_iterations_to_db(main_db_path, iterations_folder, output_path, iteration_file=""):
    """
    - main_db_path: Path to the original db JSON file
    - iterations_folder: Folder containing iteration JSON files
    - output_path: Path to save the updated duplicated DB
    """
    config = utils.model_config
    project = ""
    if config != None:
        project = config.get(CFG_PROJECT, CFG_PROJECT)
    # Load main DB
    with open(main_db_path, 'r', encoding='utf-8') as f:
        main_db = json.load(f)

    # Make a deep copy to avoid modifying original in memory
    updated_db = [dict(issue) for issue in main_db]

    # Get all iteration files
    db_file_stem = Path(main_db_path).stem
    iteration_files = [f for f in os.listdir(iterations_folder) if f.endswith('.json') and f.startswith(db_file_stem)]

    if len(iteration_files) > 0:

        for file_name in iteration_files:
            # If iteration_file is specified
            if iteration_file not in file_name:
                continue

            print(f"\nAPPLYING ITERATION CHANGES FROM: {file_name}")
            iteration_path = os.path.join(iterations_folder, file_name)
            with open(iteration_path, 'r', encoding='utf-8') as f:
                iteration_data = json.load(f)

            target_fields = iteration_data.get("target_fields", [])
            for field_entry in target_fields:
                field_name = field_entry.get("field_name")
                predictions = field_entry.get("predictions", [])

                for prediction in predictions:
                    value = prediction.get("value")
                    issue_keys = prediction.get("issue_keys", [])

                    for issue in updated_db:
                        if issue["key"] in list(map(lambda x: x.split('_')[0], issue_keys)):
                            if field_name not in issue or not isinstance(issue[field_name], list):
                                # If field doesn't exist or is not a list, set it directly
                                issue[field_name] = value if not isinstance(issue[field_name], list) else [value]
                            else:
                                # If it's a list (e.g., components), add value if not present
                                if value not in issue[field_name]:
                                    issue[field_name].append(value)

    # Save updated DB
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(updated_db, f, indent=2, ensure_ascii=False)

def calculate_column_count(file_path):
    try:
        df = pd.read_csv(file_path)
        return len(df)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return 0


def count_issue_keys_by_field(data, target_field_name):
    """
    Parameters:
        data (dict): The parsed JSON object.
        target_field_name (str): The field name to search for (e.g., "components").
    Returns:
        int: Total number of issue keys under the given field.
    """
    for field in data.get("target_fields", []):
        if field.get("field_name") == target_field_name:
            return sum(len(pred.get("issue_keys", [])) for pred in field.get("predictions", []))
    return 0


def count_files_by_extension(folder_path, extension, project):
    count = 0
    try:
        for filename in os.listdir(folder_path):
            if filename.endswith(extension) and filename.startswith(project) and os.path.isfile(
                    os.path.join(folder_path, filename)):
                count += 1
    except FileNotFoundError:
        print(f"Error: Folder '{folder_path}' not found.")
        return -1
    return count


def issues_and_accuracy_by_field(json_path: str, confidence_choice: float, accepted_issue_count=0) -> dict:
    p = Path(json_path)
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    sums = defaultdict(float)
    counts = defaultdict(int)

    total_issue_count = 0
    total_confidence_sum = 0

    for row in payload.get("data", []):
        field = row.get("field")
        if not isinstance(field, str) or not field:
            continue

        # Get accuracy, safely as float
        try:
            acc = float(row.get("accuracy", 0.0))
        except (TypeError, ValueError):
            continue  # skip invalid accuracies

        # Skip if below confidence threshold
        if acc < confidence_choice:
            continue
        total_issue_count += 1
        total_confidence_sum = total_confidence_sum + acc

        counts[field] += 1
        sums[field] += acc

    # confidence_average = total_confidence_sum/total_issue_count
    result = {
        f: {
            FID_ISSUE_COUNT: c,
            FID_AVG_ACCURACY: round(sums[f] / c, 4) if c else 0.0,
        }
        for f, c in counts.items()
    }
    result.update({
        FID_TOTAL_ISSUE_COUNT: total_issue_count,
        FID_TOTAL_CONFIDENCE: (total_confidence_sum / total_issue_count) if total_issue_count else 0,
        FID_ORPHAN_COUNT: total_issue_count - accepted_issue_count
    })
    return result


def count_approved_issues_per_field(confirmed_data: dict) -> dict:
    result = {}
    for field, items in confirmed_data.items():
        if not isinstance(items, list):
            continue
        total = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("status") != FID_APPROVED:
                continue
            tickets = item.get("tickets")
            # tickets should be a list (of lists) of strings
            if not isinstance(tickets, list):
                continue
            total += len(tickets)
            # for group in tickets:
            #     if isinstance(group, list):
            #         # count only string-like entries
            #         total += sum(1 for t in group if isinstance(t, str) and t.strip())
        result[field] = total
    return result


def register_new_iteration_record(
        total_approved,
        q_issue_count,
        questions_number,
        user,
        confirmed_data,
        iteration_information,
        project_override=None,
        is_skip_traceability_update=False
):
    config = utils.model_config
    project = ""
    output_folder = ""
    project_single = ""
    total_issue_count = 0
    field_models = {}
    fields_to_count = []

    if config is not None:
        field_models = config.get(CFG_FIELD_MODELS, {})
        output_folder = config.get(CFG_OUTPUT_FOLDER, project)
        project = config.get(CFG_OUTPUT_FOLDER, project)
        project_single = config.get(CFG_PROJECT, CFG_PROJECT)
        confidence_choice = config.get(CFG_CONFIDENCE_FIELD, project)
        file_timestamp = output_folder.replace(config.get("project", ""), "")
        dependency_model_file = f"{config.get('project', 'unknown')}_model{file_timestamp}.json"
    else:
        # Fallback when config is None (e.g., when using ?db= parameter flow)
        project = project_override or ""
        project_single = project_override or ""
        output_folder = project_override or ""
        file_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dependency_model_file = f"{project_override or 'unknown'}_model_{file_timestamp}.json"

    # audit_path = f"{output_folder}/{project_single}{AUDIT_OUT_FILE_SUFFIX}.json"
    audit_path = f"{FIELD_COMPLETION_FOLDER}/{output_folder}.json"

    approved_count_per_field = count_approved_issues_per_field(confirmed_data)

    for field in iteration_information:
        if field in approved_count_per_field:
            # Only set approved count if the field value is a dict
            if isinstance(iteration_information[field], dict):
                iteration_information[field][FID_APPROVED] = approved_count_per_field[field]

    # confidence_avg = calculate_column_average(csv_path, False) * 100
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    iteration_count = count_files_by_extension(ITERATION_FOLDER, ".json", project_single)

    # -----------------------------------
    # Load or initialize traceability file
    # -----------------------------------
    traceability_path = os.path.join(ITERATION_FOLDER, f"{TRACEABILITY_ITERATION_TABLE_FILE}.json")

    if os.path.exists(traceability_path):
        with open(traceability_path, "r", encoding="utf-8") as f:
            trace_data = json.load(f)
    else:
        trace_data = {}

    # Initialize project entry if missing or invalid (could be None from corrupted file)
    if project not in trace_data or not isinstance(trace_data.get(project), dict):
        trace_data[project] = {
            "iterations": [],
            "totals": {
                "questions": 0,
                "predictions": 0,
                "approved": 0
            }
        }
    # -----------------------------------
    # Build the record for traceability
    # -----------------------------------
    for field in iteration_information:
        # Skip non-dict fields (like confidence_avg, orphan_count, total_issue_count)
        if not isinstance(iteration_information[field], dict):
            continue
        if field in approved_count_per_field:
            field_approved = iteration_information[field].get(FID_APPROVED, 0)
            if iteration_count == 1:
                cumulative_approved_predictions = field_approved
            else:
                cumulative_approved_predictions = get_all_approved(trace_data, field, project) + field_approved

            # Try to get audit data, but handle case where config is None or file doesn't exist
            remaining_fields_to_infer = 0
            percentage = 0
            if config is not None and os.path.exists(audit_path):
                audit_field_data = reporting.get_missing_data_by_field(audit_path, field)
                if audit_field_data:
                    remaining_fields_to_infer = audit_field_data.get(ARO_INCOMPLETE,
                                                                     0) - cumulative_approved_predictions
                    incomplete_count = audit_field_data.get(ARO_INCOMPLETE, 0)
                    percentage = (
                                             cumulative_approved_predictions / incomplete_count) * 100 if incomplete_count > 0 else 0

            object_to_add = {
                IRO_ITERATION: iteration_count,
                IRO_USER: user,
                IRO_TIME_STAMP: timestamp,
                IRO_FIELD: field,
                IRO_QUESTIONS_NUMBER: iteration_information[field].get(FID_QUESTION_COUNT, 0),
                IRO_PREDICTIONS: iteration_information[field].get(FID_AVAILABLE_ISSUES, 0),
                IRO_CONFIDENCE: f"{iteration_information[field].get(FID_AVG_ACCURACY, 0):.2f}",
                IRO_APPROVED: iteration_information[field].get(IRO_APPROVED, 0),
                IRO_CUMULATIVE_APPROVED: cumulative_approved_predictions,
                IRO_REMAINING: remaining_fields_to_infer,
                IRO_COMPLETION: f"{percentage:.2f}"
            }
            total_issue_count += iteration_information[field].get(FID_AVAILABLE_ISSUES, 0)
            trace_data[project]["iterations"].append(object_to_add)

    # Update totals inside the same structure
    trace_data[project]["totals"][IRO_QUESTIONS] += int(questions_number)
    trace_data[project]["totals"][IRO_PREDICTIONS] += int(total_issue_count)
    trace_data[project]["totals"][IRO_APPROVED] += int(total_approved)

    # Save back the unified traceability file
    if not is_skip_traceability_update:
        with open(traceability_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2)
        Logger.info(f"Traceability and totals successfully updated for project '{project}'.")
    else:
        Logger.info(f"Traceability file was not updated.")

    iteration_data = {
        "timestamp": timestamp,
        "questions_number": int(questions_number),
        "total_issue_count": int(total_issue_count),
        "total_approved": int(total_approved)
    }
    return dependency_model_file, iteration_data


def get_all_approved(data: dict, field: str, project: str) -> int:
    project_data = data.get(project)
    if not isinstance(project_data, dict):
        return 0
    # filter only iterations matching the field
    iterations = [it for it in project_data.get("iterations", []) if it.get("field") == field]
    # sum approved
    cumulative_approved_predictions = sum(it.get(FID_APPROVED, 0) for it in iterations)

    return cumulative_approved_predictions


def format_data_to_fit_confirmation_page(data, request_args):
    with open(request_args["projectJson"], 'r', encoding='utf-8') as file:
        jira_issues = json.load(file)

    prediction_list = []
    for item in data:
        issue = list(filter(lambda x: item.get("issue_key", None) == x["key"], jira_issues))[0]
        prediction_list.append({
            "key": item["issue_key"],
            "summary": issue["summary"],
            "field": request_args["targetField"],
            "prediction": item["prediction"],
            "accuracy": item["confidence"],
            "text": "",
            "top_keywords": [],
            "contribution_range": {"min": -1, "max": 1},
            "issuetype": issue["issuetype"],
            "previously_rejected": item.get("previously_rejected", None)
        })
    return prediction_list


def get_inference_json(input_json, selected_target_fields):
    start_string = os.path.basename(input_json).replace(".json", "")
    pattern = os.path.join("predictions/review", f"{start_string}_*.json")
    json_files = glob.glob(pattern)
    all_predictions = []
    inferred_fields = []
    metadata_per_field = {}
    for file_path in json_files:
        if any(target_field in file_path for target_field in selected_target_fields):
            with open(file_path, 'r', encoding='utf-8') as file:
                predictions = json.load(file)
                if predictions["data"]:
                    inferred_fields.append(predictions["data"][0]["field"])
                    all_predictions.extend(predictions["data"])
                    metadata_per_field[predictions["data"][0]["field"]] = predictions["metadata"]

    inference_json = f"predictions/review/{start_string}.json"
    os.makedirs(os.path.dirname(inference_json), exist_ok=True)
    with open(inference_json, "w", encoding="utf-8") as f:
        # avg_confidence = sum(list(map(lambda x: x["accuracy"], all_predictions))) / len(all_predictions)
        json.dump({"data": all_predictions, "metadata": metadata_per_field}, f, indent=2, ensure_ascii=False)

    return inference_json, inferred_fields, metadata_per_field


def trigger_clustering_process(config, params=None):
    confidence_choice = 0.6
    clustering_progress_dict = None
    if params is None:
        project = config.get(CFG_PROJECT, CFG_PROJECT)
        output_folder = config.get(CFG_OUTPUT_FOLDER, project)
        input_file = config.get(CFG_INPUT_FILE)
        confidence_choice = config.get(CFG_CONFIDENCE_FIELD, project)

        json_path = f"{output_folder}/{project}{INFERENCE_OUT_FILE_SUFFIX}.json"
        print("[DEBUG] json_path:", json_path)
        input_path = input_file
        print("[DEBUG] input_path:", input_path)
        target_field = list(config['field_models'].keys())
    else:
        clustering_progress_dict = params["clustering_progress_dict"]
        json_path = params["inference_json"]
        input_file = params["input_json"]
        output_folder = params["output_folder"]
        target_field = params["inferred_fields"]
        project = input_file.split("_")[0]
        input_path = input_file

    if not json_path or not os.path.exists(json_path):
        return jsonify({"error": "json file not found. here:" + json_path}), 400

    # target_field = list(config['field_models'].keys())
    field_values = extract_fields_values(input_file, target_field)

    avg_confidence = None
    not_predictable = []
    rejected_predictions = []
    unconfident_predictions = []
    if params is None:
        clusters, accepted_issue_count, question_count, field_information = group_predictions_from_inferred(
            json_path=json_path,
            input_file=input_path
        )
    else:
        # TODO: Insert new clustering function call here
        selected_types_per_filed = params["selected_types_per_filed"]
        clustering_tuple = cluster_predictions(json_path, input_file, clustering_progress_dict,
                                               selected_types_per_filed)
        clustering_info, avg_confidence, not_predictable, rejected_predictions, unconfident_predictions = clustering_tuple
        clusters, accepted_issue_count, question_count, field_information = clustering_info

    clusters_plus_fields = with_field_values_meta(clusters, field_values)
    if not_predictable:
        clusters_plus_fields.setdefault("__meta", {})["not_predictable"] = [
            {
                "key": p["key"],
                "summary": p["summary"],
                "field": p["field"],
                "prediction": p["prediction"],
                "confidence": p.get("accuracy")
            }
            for p in not_predictable
        ]

    clusters_plus_fields.setdefault("__meta", {})["rejected_predictions"] = [
        {
            "key": p["key"],
            "summary": p["summary"],
            "field": p["field"],
            "prediction": p["prediction"],
            "confidence": round(p["accuracy"], 3)
        }
        for p in rejected_predictions
    ]

    clusters_plus_fields.setdefault("__meta", {})["unconfident_predictions"] = [
        {
            "key": p["key"],
            "summary": p["summary"],
            "field": p["field"],
            "prediction": p["prediction"],
            "confidence": round(p["accuracy"], 3)
        }
        for p in unconfident_predictions
    ]
    current_app.config["question_json"] = clusters_plus_fields

    iteration_information = issues_and_accuracy_by_field(json_path, confidence_choice, accepted_issue_count)
    # Adjust confidence if params
    if params:
        iteration_information[FID_TOTAL_CONFIDENCE] = avg_confidence

    confidence_avg = iteration_information[FID_TOTAL_CONFIDENCE]
    for field in field_information:
        if field in iteration_information:
            iteration_information[field][FID_QUESTION_COUNT] = field_information[field][FID_QUESTION_COUNT]
            iteration_information[field][FID_AVAILABLE_ISSUES] = field_information[field][FID_AVAILABLE_ISSUES]

    if confidence_avg != None:
        confidence_avg = confidence_avg * 100
    else:
        confidence_avg = 0

    iteration_count = count_files_by_extension(ITERATION_FOLDER, ".json", project) + 1
    settings_file_path = f"{DATABASES_SETTINGS_FOLDER}/{output_folder}_settings.json"
    with open(settings_file_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    jira_base_url = settings.get("jiraBaseUrl")

    # Load users for the specific Jira URL (per-URL cache format)
    jira_users = []
    if os.path.exists(JIRA_USERS_FILE):
        with open(JIRA_USERS_FILE, 'r', encoding='utf-8') as file:
            users_data = json.load(file)
        if isinstance(users_data, dict):
            # New per-URL format: try exact URL match, then fallback
            jira_users = users_data.get(jira_base_url, users_data.get("__legacy", []))
        elif isinstance(users_data, list):
            # Legacy flat list format
            jira_users = users_data

    return iteration_count, jira_users, jira_base_url, question_count, iteration_information, clusters_plus_fields


def with_field_values_meta(clusters: dict, field_values: list) -> dict:
    # non-mutating; keep existing structure intact
    meta = {**clusters.get("__meta", {}), "field_values": field_values}
    return {**clusters, "__meta": meta}


def get_iteration_records_by_project(project_name):
    traceability_path = os.path.join(ITERATION_FOLDER, f"{TRACEABILITY_ITERATION_TABLE_FILE}.json")

    if not os.path.exists(traceability_path):
        print(f"Traceability file not found at: {traceability_path}")
        return []

    with open(traceability_path, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    return trace_data.get(project_name, [])


def generate_iteration_file(
        confirmed_data,
        user="autogen",
        project_override=None,
        output_folder=None,
        is_save_iteration=None,
        review_page_tallies=None, # TODO: remove if unused.
        review_page_tallies_per_tab=None,
        is_push_to_jira=None,
        disabled_checkboxes=None
):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config = utils.model_config
    project = ""
    if project_override:
        project = project_override
    elif config != None:
        project = config.get(CFG_PROJECT, CFG_PROJECT)

    # Derive output_folder from config when not explicitly provided
    if not output_folder and config is not None:
        output_folder = config.get(CFG_OUTPUT_FOLDER, project)

    changed_keywords_list = []  # NEW LIST

    result = {
        IFC_TIME_STAMP: timestamp,
        IFC_USER: user,
        "output_folder": output_folder or "",
        IFC_TARGET_FIELDS: [],
        IFC_CHANGED_KEYWORDS_LIST: changed_keywords_list  # include in result
    }

    for field_name, entries in confirmed_data.items():
        predictions_by_value = defaultdict(
            lambda: {
                IFC_ISSUE_KEYS: [],
                IFC_TAGGED_ISSUE_KEYS: []
            }
        )
        rejected_predictions_by_value = defaultdict(
            lambda: {
                IFC_ISSUE_KEYS: [],
                IFC_TAGGED_ISSUE_KEYS: []
            }
        )

        status = None
        original_value = None
        for entry in entries:
            value = entry.get("predictedValue")
            original_value = entry.get("originalPredictedValue")
            keyword_str = entry.get(IFC_KEYWORDS, "")
            new_keyword_str = entry.get(IFC_NEW_KEYWORDS, "")
            status = entry.get(IFC_STATUS, "")

            keywords = [kw.strip() for kw in keyword_str.split(",") if kw.strip()]
            new_keywords = [kw.strip() for kw in new_keyword_str.split(",") if kw.strip()]

            tickets_str = entry.get("tickets", "")
            question_index = entry.get("questionIndex")

            if isinstance(tickets_str, str):
                tickets = [t.strip() for t in tickets_str.split(",") if t.strip()]
            elif isinstance(tickets_str, list):
                # Flatten in case there are nested lists
                tickets = []
                for t in tickets_str:
                    if isinstance(t, str):
                        tickets.append(t.strip())
                    elif isinstance(t, list):
                        tickets.extend([x.strip() for x in t if isinstance(x, str)])
            else:
                tickets = []
            # tagged_tickets = [f"{question_index}_{ticket.split('_')[0]}" for ticket in tickets]
            tagged_tickets = [f"{question_index}|{ticket.split('_')[0]}" for ticket in tickets]

            if status == IRO_APPROVED:
                predictions_by_value[value][IFC_ISSUE_KEYS].extend(tickets)
                predictions_by_value[value][IFC_TAGGED_ISSUE_KEYS].extend(tagged_tickets)
            if status == IRO_REJECTED:
                rejected_predictions_by_value[value][IFC_ISSUE_KEYS].extend(tickets)
                rejected_predictions_by_value[value][IFC_TAGGED_ISSUE_KEYS].extend(tagged_tickets)

            # Add to changed_keywords_list
            changed_keywords_list.append({
                IFC_FIELD_NAME: field_name,
                FQS_PREDICTED_VALUE: value,
                IFC_STATUS: status,
                IFC_KEYWORDS: keywords,
                IFC_NEW_KEYWORDS: new_keywords
            })

        for value, data in predictions_by_value.items():
            data[IFC_ISSUE_KEYS] = list(dict.fromkeys(data[IFC_ISSUE_KEYS]))
            data[IFC_TAGGED_ISSUE_KEYS] = list(dict.fromkeys(data[IFC_TAGGED_ISSUE_KEYS]))

        for value, data in rejected_predictions_by_value.items():
            data[IFC_ISSUE_KEYS] = list(dict.fromkeys(data[IFC_ISSUE_KEYS]))
            data[IFC_TAGGED_ISSUE_KEYS] = list(dict.fromkeys(data[IFC_TAGGED_ISSUE_KEYS]))

        predictions_list = [
            {
                IFC_VALUE: value,
                IFC_ORIGINAL_VALUE: original_value,
                IFC_ISSUE_KEYS: data[IFC_ISSUE_KEYS],
                IFC_TAGGED_ISSUE_KEYS: data[IFC_TAGGED_ISSUE_KEYS]
                # keywords are no longer here
            }
            for value, data in predictions_by_value.items()
        ]

        rejected_predictions_list = [
            {
                IFC_VALUE: value,
                IFC_ORIGINAL_VALUE: original_value,
                IFC_ISSUE_KEYS: data[IFC_ISSUE_KEYS],
                IFC_TAGGED_ISSUE_KEYS: data[IFC_TAGGED_ISSUE_KEYS]
                # keywords are no longer here
            }
            for value, data in rejected_predictions_by_value.items()
        ]

        # Remove redundant info.
        if is_save_iteration:
            [item.pop(IFC_ISSUE_KEYS) for item in predictions_list]
            [item.pop(IFC_ISSUE_KEYS) for item in rejected_predictions_list]
        elif is_push_to_jira:
            [item.pop(IFC_TAGGED_ISSUE_KEYS) for item in rejected_predictions_list]
        else:
            [item.pop(IFC_TAGGED_ISSUE_KEYS) for item in predictions_list]
            [item.pop(IFC_TAGGED_ISSUE_KEYS) for item in rejected_predictions_list]


        result[IFC_TARGET_FIELDS].append({
            IFC_FIELD_NAME: field_name,
            IFC_PREDICTIONS: predictions_list,
            "rejected_predictions": rejected_predictions_list
        })

    # Write to JSON file — use output_folder as prefix so each db is scoped independently
    file_prefix = output_folder if output_folder else project

    run_iteration_filename = f"{file_prefix}_{IRO_ITERATION}_{timestamp}.json"
    push_iteration_filename = f"{file_prefix}_{IRO_ITERATION}_{timestamp}_{IRO_PUSHED}.json"
    save_iteration_filename = f"{file_prefix}_{IRO_ITERATION}.json"
    iteration_filename = save_iteration_filename if is_save_iteration else run_iteration_filename
    iteration_filename = push_iteration_filename if is_push_to_jira else iteration_filename
    iteration_folder = SAVED_ITERATION_FOLDER if is_save_iteration else ITERATION_FOLDER
    Path(iteration_folder).mkdir(parents=True, exist_ok=True)
    run_iteration_path = os.path.join(ITERATION_FOLDER, run_iteration_filename)
    save_iteration_path = os.path.join(SAVED_ITERATION_FOLDER, save_iteration_filename)
    push_iteration_path = os.path.join(ITERATION_FOLDER, push_iteration_filename)
    iteration_path = save_iteration_path if is_save_iteration else run_iteration_path
    iteration_path = push_iteration_path if is_push_to_jira else iteration_path

    # Remove saved_iteration related file if any
    if not is_save_iteration and not is_push_to_jira:
        bak_iteration_file = f"{save_iteration_path}.bak"
        if Path(bak_iteration_file).is_file():
            Logger.debug(f"Removing iteration .bak file: {bak_iteration_file}")
            Path(bak_iteration_file).unlink(missing_ok=True)
        if Path(save_iteration_path).is_file():
            Logger.debug(f"Renaming saved iteration file: {save_iteration_path}")
            os.rename(save_iteration_path, f"{save_iteration_path}.bak")
    else:
        # Include review_page_tallies
        result["review_page_tallies"] = review_page_tallies
        result["review_page_tallies_per_tab"] = review_page_tallies_per_tab
        result["disabled_checkboxes"] = disabled_checkboxes

    if result.get(IFC_TARGET_FIELDS, None):
        with open(iteration_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"JSON file successfully written to: {iteration_folder}")
        return iteration_filename
    else:
        print(f"No JSON file was written: no result to save.")
        return None


def retrieve_keyword_feedback(field_name):
    feedback_keywords = []
    iteration_files = [f for f in os.listdir(ITERATION_FOLDER) if f.endswith('.json')]
    for file_name in iteration_files:
        with open(os.path.join(ITERATION_FOLDER, file_name), 'r', encoding='utf-8') as f:
            iteration_data = json.load(f)
            for item in iteration_data.get("changed_keywords_list", []):
                if item["field_name"] == field_name:
                    added_keywords = list(set(item["new_keywords"]) - set(item["keywords"]))
                    removed_keywords = list(set(item["keywords"]) - set(item["new_keywords"]))
                    feedback_keywords.append({
                        "predicted_value": item["predicted_value"],
                        "field_name": field_name,
                        # "keywords": item["keywords"],
                        # "new_keywords": item["new_keywords"],
                        "added_keywords": added_keywords,
                        "removed_keywords": removed_keywords
                    })

    # Reformat the structure
    feedback_keywords_dict = {}
    if feedback_keywords:
        feedback_keywords_dict[field_name] = {"added_keywords": None, "removed_keywords": None}
        for key in ["added_keywords", "removed_keywords"]:
            keywords_list = list(map(lambda x: x[key], feedback_keywords))
            # Flatten the list of lists
            flattened_list = []
            for sublist in keywords_list:
                flattened_list.extend(sublist)
            merged_keywords_list = list(set(flattened_list))

            feedback_keywords_dict[field_name][key] = merged_keywords_list

    return feedback_keywords_dict, feedback_keywords


def extract_fields_values(json_path, target_fields):
    if not json_path or not os.path.exists(json_path):
        raise FileNotFoundError(f"Database file not found: '{json_path}'. It may have been deleted.")
    # Load JSON file
    with open(json_path, "r", encoding="utf-8") as f:
        issues = json.load(f)

    result = []
    for field in target_fields:
        values = set()

        for issue in issues:
            if field in issue:
                val = issue[field]
                if isinstance(val, list):
                    values.update(val)
                elif val is not None:
                    values.add(val)

        result.append({
            "field_name": field,
            "list_of_values": sorted(values)
        })

    return result


def to_int(x, default=0):
    try:
        # numbers may arrive as strings like "0.73" or "120"
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x).strip()
        if s == "":
            return default
        # try int first
        try:
            return int(s)
        except ValueError:
            # fallback: float then int
            return int(float(s))
    except Exception:
        return default


def get_iterations_field_summary(project, path):
    if not path or not os.path.exists(path):
        return f"error: JSON file path not provided or not found. path={path}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return "error: Failed to read JSON: {e}"

    # Allow flexibility: if project key not provided/found, try to infer the only top-level key
    project_keys = list(raw.keys()) if isinstance(raw, dict) else []
    if not project and len(project_keys) == 1:
        project = project_keys[0]

    if project not in raw:
        return f"error: Project '{project}' not found in JSON."

    project_obj = raw[project]
    iterations = project_obj.get("iterations", [])
    if not isinstance(iterations, list):
        return "error: Invalid JSON shape: 'iterations' must be a list."

    # Group iterations by field
    by_field = {}
    for item in iterations:
        field = item.get("field")
        if not field:
            # skip rows without field
            continue
        by_field.setdefault(field, []).append(item)

    fields_out = {}
    overall_initial = 0
    overall_cum_approved = 0

    for field_name, items in by_field.items():
        # Find iteration 1 record for this field -> initial_total = approved(itr1) + remaining(itr1)
        # If more than one "iteration==1" exists, pick the first occurrence (or any).
        itr1 = None
        for it in items:
            if to_int(it.get("iteration")) == 1:
                itr1 = it
                break
        if itr1 is None:
            # If iteration 1 does not exist for this field, we can't compute a proper initial total.
            # Fall back to using the *earliest* iteration by number as the "initial".
            earliest = min(items, key=lambda x: to_int(x.get("iteration"), 10 ** 9))
            itr1 = earliest

        init_approved = to_int(itr1.get("approved"), 0)
        init_remaining = to_int(itr1.get("remaining"), 0)
        initial_total = init_approved + init_remaining

        # Latest iteration for this field (max iteration number)
        latest = max(items, key=lambda x: to_int(x.get("iteration"), -10 ** 9))
        cumulative_approved = to_int(latest.get("cumulative_approved"), 0)

        completion_pct = (cumulative_approved / initial_total * 100.0) if initial_total > 0 else 0.0

        fields_out[field_name] = {
            "initial_total": initial_total,
            "cumulative_approved": cumulative_approved,
            "completion_pct": round(completion_pct, 2)
        }

        overall_initial += initial_total
        overall_cum_approved += cumulative_approved

    overall_completion = (overall_cum_approved / overall_initial * 100.0) if overall_initial > 0 else 0.0

    response = {
        "project": project,
        "fields": fields_out,
        "overall": {
            "initial_total": overall_initial,
            "cumulative_approved": overall_cum_approved,
            "completion_pct": round(overall_completion, 2)
        },
        "meta": {
            "iterations_count": len(iterations),
            "fields_count": len(fields_out),
            "notes": "completion_pct = cumulative_approved / initial_total * 100 (not capped)."
        }
    }
    return response


def field_summary_iteration_zero(target_fields, audit_path, project):
    fields_out = {}
    overall_initial = 0
    overall_cum_approved = 0

    # Early exit if audit file doesn't exist - return valid empty structure
    if not audit_path or not os.path.exists(audit_path):
        return {
            "project": project,
            "fields": {},
            "overall": {
                "initial_total": 0,
                "cumulative_approved": 0,
                "completion_pct": 0.0
            },
            "meta": {
                "iterations_count": 0,
                "fields_count": 0,
                "notes": "No audit data available yet; baseline not computed. Run an iteration to generate audit data."
            }
        }

    for field in target_fields:
        field_data = reporting.get_missing_data_by_field(audit_path, field)
        if not field_data:
            continue

        # The incomplete count = how many items are missing initially
        incomplete = field_data.get(ARO_INCOMPLETE) or 0
        initial_total = incomplete
        cumulative_approved = 0
        completion_pct = 0.0

        fields_out[field] = {
            "initial_total": initial_total,
            "cumulative_approved": cumulative_approved,
            "completion_pct": completion_pct
        }

        overall_initial += initial_total

    response = {
        "project": project,
        "fields": fields_out,
        "overall": {
            "initial_total": overall_initial,
            "cumulative_approved": overall_cum_approved,
            "completion_pct": 0.0
        },
        "meta": {
            "iterations_count": 0,
            "fields_count": len(fields_out),
            "notes": "Initial baseline before any iteration; all cumulative_approved = 0."
        }
    }
    return response


def consolidate_iterations_data(config, project_override=None, output_folder=None):
    """
    Consolidates all iteration files for a specific database into a single JSON file
    in the ready_to_send folder. Returns a dict with the consolidated data for display,
    grouped by issue type. Only keeps one file per database, replacing if content changed.

    Args:
        config: The model configuration (may be None)
        project_override: Optional project name to use when config is None
        output_folder: Database identifier (e.g. DEMO_20260511_180403) to scope
                       consolidation to a specific database export. When provided,
                       only iteration files belonging to this database are included.

    Returns:
        tuple: (result_dict, status_code) where result_dict contains the response data
    """
    # Create ready_to_send folder if it doesn't exist
    ready_to_send_folder = os.path.join(ITERATION_FOLDER, "ready_to_send")
    os.makedirs(ready_to_send_folder, exist_ok=True)

    # Derive output_folder from config when not explicitly provided
    if not output_folder and config is not None:
        output_folder = config.get(CFG_OUTPUT_FOLDER, "")

    if config is not None:
        project = config.get(CFG_PROJECT, "")
        if not project:
            return {"error": "No project key found in configuration"}, 400
        db_path = config.get(CFG_INPUT_FILE, "")
        issuetype_lookup = utils.get_issuetype_lookup(db_path)
    else:
        project = project_override or ""
        issuetype_lookup = {}

    # --- Determine the file prefix used to filter iteration files ---
    # Use output_folder (db identifier) when available for precise scoping;
    # fall back to project name for backward compatibility.
    file_prefix = output_folder if output_folder else project

    if file_prefix:
        iteration_files = [
            f for f in os.listdir(ITERATION_FOLDER)
            if f.endswith('.json')
               and f.startswith(f"{file_prefix}_")
               and f"_{IRO_ITERATION}_" in f
        ]
    else:
        # No prefix available — fallback: infer from most recent iteration file
        all_iteration_files = [
            f for f in os.listdir(ITERATION_FOLDER)
            if f.endswith('.json')
               and f"_{IRO_ITERATION}_" in f
               and TRACEABILITY_ITERATION_TABLE_FILE not in f
               and not f.startswith("_")
        ]
        if not all_iteration_files:
            return {"error": "No iteration files found"}, 404

        latest_file = sorted(all_iteration_files, reverse=True)[0]
        file_prefix = latest_file.split(f"_{IRO_ITERATION}_")[0]
        project = project or file_prefix.split('_')[0]

        iteration_files = [f for f in all_iteration_files if f.startswith(f"{file_prefix}_")]

    if not iteration_files:
        return {"error": f"No iteration files found for {file_prefix}"}, 404

    # Consolidate predictions from all files, grouped by issue type
    # Structure for deduplication: { (issuetype, field, new_value): set(issue_keys) }
    predictions_dedup = {}

    for file_name in iteration_files:
        file_path = os.path.join(ITERATION_FOLDER, file_name)
        with open(file_path, 'r', encoding='utf-8') as f:
            iteration_data = json.load(f)

        target_fields = iteration_data.get("target_fields", [])
        for field_entry in target_fields:
            field_name = field_entry.get("field_name", "")
            predictions = field_entry.get("predictions", [])

            for prediction in predictions:
                new_value = prediction.get("value", "")
                # issue_keys = prediction.get("issue_keys", [])
                tagged_issue_keys = prediction.get("tagged_issue_keys", [])

                for key in tagged_issue_keys:
                    if isinstance(key, str):
                        # clean_key = extract_issue_key(key)
                        question_id, clean_key = extract_question_id_and_issue_key(key)
                        if clean_key:
                            issuetype = issuetype_lookup.get(clean_key, "Unknown")
                            dedup_key = (issuetype, field_name, new_value)
                            if dedup_key not in predictions_dedup:
                                predictions_dedup[dedup_key] = set()
                            # predictions_dedup[dedup_key].add(clean_key)
                            predictions_dedup[dedup_key].add((clean_key, question_id))

    # Convert deduplicated data to final structure
    # Structure: { issuetype: [ {field, new_value, issue_keys} ] }
    predictions_by_issuetype = {}
    total_issue_keys = 0

    for (issuetype, field_name, new_value), issue_keys_quest_id_dict in predictions_dedup.items():
    # for (issuetype, field_name, new_value), issue_keys_set in predictions_dedup.items():
        if issuetype not in predictions_by_issuetype:
            predictions_by_issuetype[issuetype] = []

        issue_keys_set = [item[0] for item in issue_keys_quest_id_dict]
        tagged_issue_keys_set = [f"{item[0]}_{item[1]}" for item in issue_keys_quest_id_dict]
        predictions_by_issuetype[issuetype].append({
            "field": field_name,
            "new_value": new_value,
            "issue_keys": sorted(list(issue_keys_set)),
            "tagged_issue_keys_set": tagged_issue_keys_set
        })
        total_issue_keys += len(issue_keys_set)

    # Prepare consolidated data (without timestamp for comparison)
    new_consolidated_content = {
        "project": project,
        "predictions_by_issuetype": predictions_by_issuetype,
        "total_issue_keys": total_issue_keys
    }

    # Find existing consolidated file for this database (scoped by file_prefix)
    existing_files = [
        f for f in os.listdir(ready_to_send_folder)
        if f.endswith('.json') and f.startswith(f"{file_prefix}_consolidated")
    ]

    existing_file_path = None
    existing_filename = None
    content_changed = True

    if existing_files:
        # Use the first (should be only one per project)
        existing_filename = existing_files[0]
        existing_file_path = os.path.join(ready_to_send_folder, existing_filename)

        try:
            with open(existing_file_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)

            # Compare content (excluding timestamp)
            existing_content = {
                "project": existing_data.get("project"),
                "predictions_by_issuetype": existing_data.get("predictions_by_issuetype"),
                "total_issue_keys": existing_data.get("total_issue_keys")
            }

            if existing_content == new_consolidated_content:
                content_changed = False
        except Exception:
            content_changed = True

    if content_changed:
        # Delete all existing consolidated files for this database
        for old_file in existing_files:
            old_path = os.path.join(ready_to_send_folder, old_file)
            try:
                os.remove(old_path)
            except Exception:
                pass

        # Create new consolidated file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        consolidated_filename = f"{file_prefix}_consolidated_{timestamp}.json"
        consolidated_path = os.path.join(ready_to_send_folder, consolidated_filename)

        consolidated_data = {
            "project": project,
            "timestamp": timestamp,
            "predictions_by_issuetype": predictions_by_issuetype,
            "total_issue_keys": total_issue_keys
        }

        with open(consolidated_path, 'w', encoding='utf-8') as f:
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)
    else:
        # Use existing file
        consolidated_filename = existing_filename

    return {
        "success": True,
        "filename": consolidated_filename,
        "predictions_by_issuetype": predictions_by_issuetype,
        "total_issue_keys": total_issue_keys,
        "content_changed": content_changed
    }, 200


def apply_sent_items_if_needed(jira_issues, project_db, sent_dir=f"{ITERATION_READY_TO_SEND}"):
    project_name = Path(project_db).name
    sent_filename = project_name.replace(".json", "_sent.json")
    sent_filepath = f"{sent_dir}/{sent_filename}"
    applied_items = []
    try:
        with open(sent_filepath, "r", encoding="utf-8") as file:
            sent_items = json.load(file)
        for sent_item in sent_items:
            filtered_jira_issues = [item for item in jira_issues if item["key"] == sent_item["issuekey"]]
            if not len(filtered_jira_issues) == 1:
                continue
            jira_issue = filtered_jira_issues[0]
            if sent_item["field_name"] in jira_issue and not jira_issue[sent_item["field_name"]]:
                filtered_jira_issues[0][sent_item["field_name"]] = sent_item["value"]
                applied_items.append(sent_item)
            if sent_item["field"] in jira_issue and not jira_issue[sent_item["field"]]:
                filtered_jira_issues[0][sent_item["field"]] = sent_item["value"]
                applied_items.append(sent_item)

    except FileNotFoundError:
        print(f"Error: The file '{sent_filepath}' does not exist.")
    except json.JSONDecodeError:
        print(f"Error: '{sent_filepath}' is not a valid JSON file.")

    return applied_items

def apply_iterations(jira_issues, project_name, iteration_dir="iterations"):
    rejected_prediction_dict = {}
    if Path(iteration_dir):
        json_files = sorted(
            Path(iteration_dir).glob('*.json'),
            key=lambda f: f.stat().st_mtime
        )
        json_files = [os.path.abspath(f) for f in json_files]
        json_files = list(filter(
            lambda x: f"{project_name}_iteration" in x,
            json_files
        ))
        for index, json_file in enumerate(json_files):
            # print(f"[DEBUG] apply accepted predictions from iter#{index}")
            with open(json_file, 'r', encoding='utf-8') as file:
                confirmed_predictions = json.load(file)
                for confirmed_prediction in confirmed_predictions["target_fields"]:
                    target_field = confirmed_prediction["field_name"]

                    if target_field not in rejected_prediction_dict:
                        rejected_prediction_dict[target_field] = {}
                    for rejected_prediction in confirmed_prediction["rejected_predictions"]:
                        for issue_key in rejected_prediction["issue_keys"]:
                            # Remove summary
                            issue_key_ = issue_key.split("_")[0]
                            if issue_key_ not in rejected_prediction_dict[target_field]:
                                rejected_prediction_dict[target_field][issue_key_] = []

                            rejected_prediction_value = rejected_prediction["value"]
                            is_target_field_list = isinstance(jira_issues[0].get(target_field, None), list)
                            if is_target_field_list:
                                if not isinstance(rejected_prediction_value, list):
                                    rejected_prediction_value = rejected_prediction_value.split(',')

                            rejected_prediction_dict[target_field][issue_key_].append(rejected_prediction_value)

                    for prediction in confirmed_prediction["predictions"]:
                        predicted_value = prediction["value"]
                        issue_keys = prediction["issue_keys"]
                        issue_keys = list(map(lambda x: x.split('_')[0], issue_keys))

                        # Quick fix: adjust predicted_value according to target_field's type
                        is_target_field_list = isinstance(jira_issues[0][target_field], list)
                        is_predicted_value_list = isinstance(predicted_value, list)
                        is_split = is_target_field_list and not is_predicted_value_list
                        predicted_value = predicted_value.split(',') if is_split else predicted_value

                        # print(f"[DEBUG] {target_field}: apply value {predicted_value} to issue_keys {issue_keys}")
                        for issue_key in issue_keys:
                            jira_issue = list(filter(lambda x: x["key"] == issue_key, jira_issues))
                            if jira_issue:
                                jira_issue[0][target_field] = predicted_value
                                if "inf_iter" not in jira_issue[0]:
                                    jira_issue[0]["inf_iter"] = {target_field: index}
                                else:
                                    jira_issue[0]["inf_iter"][target_field] = index

    return rejected_prediction_dict


def tag_rejected_predictions(target_field, predictions, rejected_predictions):
    tag_count = 0
    rejected_predictions_per_issue_key = rejected_predictions.get(target_field, {})
    for prediction in predictions:
        issue_key = prediction["issue_key"]
        prediction_value = prediction["prediction"]
        if issue_key in rejected_predictions_per_issue_key:
            if isinstance(prediction_value, list):
                is_rejected = False
                for rejected_prediction_list in rejected_predictions_per_issue_key[issue_key]:
                    is_rejected = all(item in rejected_prediction_list for item in prediction_value)
                    if is_rejected:
                        break
                if is_rejected:
                    prediction["previously_rejected"] = True
                    tag_count += 1
            else:
                if prediction_value in rejected_predictions_per_issue_key[issue_key]:
                    prediction["previously_rejected"] = True
                    tag_count += 1
    return tag_count

def get_saved_review_state(project_stem, is_abort=None):
    saved_review_state = {}
    file_path = str(os.path.join(SAVED_ITERATION_FOLDER, project_stem))
    file_path = f"{file_path}_{IRO_ITERATION}.json"
    bak_file_path = f"{file_path}.bak"
    if Path(bak_file_path).is_file() and is_abort:
        Logger.debug(f"Renaming .bak file ...")
        Path(bak_file_path).rename(Path(file_path))

    if Path(file_path).is_file():
        with open(file_path, 'r', encoding='utf-8') as file:
            saved_review_state = json.load(file)
    return saved_review_state


def remove_files_with_string(directory_path, target_string):
    rem_count = 0
    dir_path = Path(directory_path)
    for file_path in dir_path.iterdir():
        if file_path.is_file() and target_string in file_path.name:
            try:
                file_path.unlink()
                rem_count += 1
            except Exception as e:
                print(f"Error deleting {file_path.name}: {e}")
    return rem_count


if __name__ == "__main__":
    project_path = r"C:\Users\wm080\Documents\Projects\JFIP-224_Branch\jfip_web_ui\databases\FBEZ_20260729_100643.json"
    project_json = Path(project_path).name
    ready_to_send_dir = r"C:\Users\wm080\Documents\Projects\JFIP-224_Branch\jfip_web_ui\iterations\ready_to_send"
    with open(project_path, "r", encoding="utf-8") as file:
        jira_issues = json.load(file)
    applied_items = apply_sent_items_if_needed(jira_issues, project_json)
    print(f"applied_items:", applied_items)


