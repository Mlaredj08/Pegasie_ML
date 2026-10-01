# reporting/audit_generator.py
"""Audit report data generation: field completion analysis and JSON output."""
import csv
import json
from collections import Counter
import os
from pathlib import Path

from analysis.data_pre_analysis import get_target_fields_matrix_per_project
from config import IMPOSSIBLE_LINKS, FIELD_COMPLETION_FOLDER
from config.constants import AUDIT_OUT_FILE_SUFFIX, ARO_INCOMPLETE, ITERATION_FOLDER, UPDATED_DATABASE_FOLDER, \
    UPDATED_DATABASE_FILE, STATUSES_TO_EXCLUDE
from config.logger import Logger
import services.iteration_service as iteration_manager

# Constants
MAX_LEN = 150

def get_missing_data_by_field(json_path: str, field_name: str):
    try:
        with open(json_path, 'r', encoding='utf-8') as file:
            json_data = json.load(file)
    except FileNotFoundError:
        print(f"Error: The file '{json_path}' was not found.")
        return None
    completed = 0
    total = 0
    for item in json_data.get("data", []):
        if item.get("field") == field_name:
            completed = item.get("completed", 0)
            total = item.get("total", 0)
            break
    return {
        ARO_INCOMPLETE: total - completed if total else None
    }


def json_file_to_dict(file_path):
    json_obj = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            json_obj = json.load(file)
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{file_path}'. Check if the file contains valid JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return json_obj


def get_jira_field_audit_report_data(file_path, is_exclude_closed_issues=False):
    field_completion_list = []
    json_obj = json_file_to_dict(file_path = file_path)
    total = None
    total_fields = None
    sum_completion_percentage = 0

    # Get inferable fields
    project_name = Path(file_path).stem
    target_fields_matrix_per_project = get_target_fields_matrix_per_project([project_name])
    inferable_fields = target_fields_matrix_per_project.get(project_name, {}).get("inferable_fields", [])

    # Exclude Closed issues if specified.
    if is_exclude_closed_issues:
        Logger.info(f"Excluding closed & resolved issues ...")
        json_obj = [issue for issue in json_obj if issue["status"] not in STATUSES_TO_EXCLUDE]

    if json_obj:
        total = len(json_obj)
        field_names = inferable_fields if inferable_fields else json_obj[0].keys()
        total_fields = len(field_names)
        items_with_status = [item for item in json_obj if "status" in item]
        statuses = list(map(lambda x: x["status"], items_with_status))
        status_names = list(dict.fromkeys(statuses))
        status_counts = {}
        for status_name in status_names:
            status_counts[status_name] = len([item for item in statuses if item == status_name])
        print("status_counts:", status_counts)
        for field_name in field_names:
            filtered_json_obj = (list(filter(
                lambda x: "issuetype" in x and x["issuetype"] not in IMPOSSIBLE_LINKS.get(field_name, []),
                json_obj
            )))

            issue_count = len(list(filter(lambda x: field_name in x, filtered_json_obj)))
            incomplete_count = len(list(filter(lambda x: field_name in x and (x[field_name] is None or str(x[field_name]) == "[]"), filtered_json_obj)))
            complete_count = issue_count - incomplete_count
            complete_percentage = 100 * complete_count / issue_count
            sum_completion_percentage += complete_percentage
            common_values = [row[field_name] for row in filtered_json_obj]
            common_values = list(filter(lambda x: x, common_values))
            common_values = Counter(list(map(lambda x: str(x), common_values)))
            common_values = sorted(common_values.items(), key=lambda item: item[1], reverse=True)
            common_values = list(map(lambda x: f"[{x[1]}] {x[0][:MAX_LEN]}... " if len(x[0]) > MAX_LEN else f"[{x[1]}] {x[0]}", common_values))
            # Show incomplete fields only.
            if True or incomplete_count != 0:
                field_completion_list.append({
                    "field": field_name,
                    "completed": complete_count,
                    "total": issue_count,
                    "incomplete": issue_count - complete_count,
                    "%": f"{complete_percentage:.2f}",
                    "values": common_values[:5]
                })
    avg_completion = f"{sum_completion_percentage / total_fields:.2f}" if total_fields else None
    return {
        "headers": ["Field", "Completed", "Total Issues", "To Infer", "Completion %"],
        "data": field_completion_list,
        "total_issues": total,
        "total_fields": total_fields,
        "avg_completion": avg_completion
    }

def dump_json_to_file(json_object, out_file_path):
    with open(out_file_path, 'w') as f:
        json.dump(json_object, f, indent=4)

def dump_json_to_csv_file(json_object, out_file_path):
    data = json_object
    headers = data[0].keys() if data else []
    with open(out_file_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

def generate_audit_json_file(
        in_file_path,
        out_folder,
        project,
        is_exclude_closed=False,
        is_previous_iterations=None,
        iteration_to_include=None,
):
    json_obj_before = get_jira_field_audit_report_data(in_file_path, is_exclude_closed)
    json_obj_before_fields = list(map(lambda x: x["field"], json_obj_before["data"]))

    # Apply previous iterations' changes on db file
    updated_db_file = f"{UPDATED_DATABASE_FOLDER}\\{project}_{UPDATED_DATABASE_FILE}"
    if os.listdir(ITERATION_FOLDER):
        if is_previous_iterations:
            iteration_manager.apply_iterations_to_db(in_file_path, ITERATION_FOLDER, updated_db_file)
        elif iteration_to_include:
            iteration_manager.apply_iterations_to_db(in_file_path, ITERATION_FOLDER, updated_db_file, iteration_to_include)

    if os.listdir(ITERATION_FOLDER) and (is_previous_iterations or iteration_to_include):
        json_obj_after = get_jira_field_audit_report_data(updated_db_file, is_exclude_closed)
    else:
        json_obj_after = json_obj_before

    json_obj_after_data = list(filter(lambda x: x["field"] in json_obj_before_fields, json_obj_after["data"]))

    for after_item in json_obj_after_data:
        Logger.debug(f'after_item["field"]: {after_item["field"]}')
        before_item = list(filter(lambda x: x["field"] == after_item["field"], json_obj_before["data"]))[0]
        after_item["completed_before"] = before_item["completed"]
        after_item["incomplete_before"] = before_item["incomplete"]
        after_item["%_before"] = before_item["%"]
        delta = float(after_item["%"]) - float(before_item["%"])
        after_item["%_delta"] = f"{delta:.2f}",

    Path(FIELD_COMPLETION_FOLDER).mkdir(parents=True, exist_ok=True)
    out_file = f"{FIELD_COMPLETION_FOLDER}/{out_folder}.json"
    csv_out_file = f"{FIELD_COMPLETION_FOLDER}/{out_folder}.csv"
    dump_json_to_file({"data": json_obj_after_data}, out_file)
    dump_json_to_csv_file(json_obj_after_data, csv_out_file)
    # save_field_completion_as_csv(out_file)


if __name__ == "__main__":
    generate_audit_json_file(
        "databases/AIP_20250709_171749.json",
        "AIP_20250709_171749",
        "AIP"
    )
