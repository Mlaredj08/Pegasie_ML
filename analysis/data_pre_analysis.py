import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from config import UNPREDICTABLE_FIELDS, DATABASES_SETTINGS_FOLDER, INFERABILITY_ANALYSIS, PERFORMANCE_FOLDER
from config.logger import Logger


def compute_field_inheritance_probability(db_path, field="components"):
    df0 = pd.read_json(db_path)
    df1  = df0[df0[field].notna()]
    df1  = df1[df1[field].apply(len) > 0]
    df = df1[df1['parent'].notna()]
    inherited_count = 0
    for index, row in df.iterrows():
        parent_field = df0.loc[df0['key'] ==  row['parent'], field].iloc[0]
        if str(row[field]) == str(parent_field):
            inherited_count += 1

    return round(inherited_count / df.shape[0], 2), df.shape[0]


def compute_probability_of_siblings_to_share_field(db_path, field="components"):
    df0 = pd.read_json(db_path)
    df1  = df0[df0[field].notna()]
    df1  = df1[df1[field].apply(len) > 0]
    df = df1[df1['parent'].notna()]
    pd.set_option('display.max_colwidth', None)
    parent_values = df['parent'].unique()
    field_values = df[field].explode().unique()
    probability_per_parent = {}
    for parent in parent_values:
        cur_df = df[df['parent'] == parent]
        sibling_count = cur_df.shape[0]
        cur_field_values = cur_df[field].explode().unique()
        count_per_field_value = {}
        for field_value in cur_field_values:
            field_value_count = len(list(filter(lambda x: field_value in x, cur_df[field])))
            count_per_field_value[field_value] = field_value_count

        probability = round(max(list(count_per_field_value.values())) / sibling_count, 2)
        probability_per_parent[parent] = {"probability": probability, "sibling_count": sibling_count}

    probability_list = list(map(lambda x: x["probability"], probability_per_parent.values()))
    probability_avg = sum(probability_list) / len(probability_list)
    total_samples = sum(list(map(lambda x: x["sibling_count"], probability_per_parent.values())))

    print(f"[DEBUG] Probability of siblings to share '{field}' based on {total_samples} issues: {probability_avg}")
    return probability_avg, total_samples

def get_children_by_parent(db_path, field="components"):
    df0 = pd.read_json(db_path)
    df1 = df0[df0['parent'].notna()]
    pd.set_option('display.max_colwidth', None)
    parent_values = df1['parent'].unique()
    print("[DEBUG] parents:", parent_values)
    children_by_parent = []
    for parent in parent_values:
        parent_field = df0[df0['key'] == parent][field].iloc[0]
        df2 = df1[df1['parent'] == parent]
        children_keys =  df2['key'].tolist()
        children_fields = df2[field].tolist()
        if isinstance(parent_field, list):
            is_all_assigned = len(parent_field) != 0 and len(list(filter(lambda x: len(x) == 0, children_fields))) == 0
            unique_children_fields = set(tuple(sublist) for sublist in children_fields)
            is_sibling_match = len(unique_children_fields) == 1
            is_inherited = is_sibling_match and list(unique_children_fields)[0] == parent_field
        else:
            is_all_assigned = parent_field  and len(list(filter(lambda x: not x, children_fields))) == 0
            is_sibling_match = len(set(children_fields)) == 1
            is_inherited = is_sibling_match and list(set(children_fields))[0] == parent_field
        children_by_parent.append({
            "parent_key": parent,
            f"parent_{field}": parent_field,
            "child_keys": children_keys,
            f"child_{field}_list": children_fields,
            "is_all_assigned": is_all_assigned,
            "is_sibling_match": is_sibling_match,
            "is_inherited": is_inherited,
            "child_count": len(children_keys)

        })

    return children_by_parent

def set_blocker_priority_to_blocked_priority(db_path):
    issues_to_set = {}

    pd.set_option('display.max_colwidth', None)
    df0 = pd.read_json(db_path)
    total_unassigned_priorities = df0[df0['priority'].isnull()].shape[0]

    # List blocked issues
    df1 = df0[df0['issuelinks'].apply(lambda x: any(d.get('type') == 'is blocked by' for d in x))]
    df1 = df1.assign(blocked_by=df1['issuelinks'].map(lambda x: [d['key'] for d in list(filter(lambda y: y["type"] == "is blocked by", x))]))

    for index, row in df1.iterrows():
        issue_priority = row['priority']
        blocked_key = row['key']
        blocked_desc = row['description']
        blocked_status = row['status']
        for blocker_key in row['blocked_by']:
            blocker_priority = df0.loc[df0['key'] == blocker_key, 'priority']
            if len(blocker_priority) == 0:
                continue
            blocker_priority = blocker_priority.iloc[0]
            if True or blocker_priority is None:

                if blocker_key not in issues_to_set:
                    issues_to_set[blocker_key] = {
                        "blocker_priority": blocker_priority,
                        "blocked": [(blocked_key, issue_priority, blocked_desc, blocked_status)],
                        "predicted_priority": None
                    }
                else:
                    if issue_priority not in issues_to_set[blocker_key]:
                        issues_to_set[blocker_key]["blocked"].append((blocked_key, issue_priority, blocked_desc, blocked_status))

    # Set to the highest priority if many
    for k, v in issues_to_set.items():
        priorities = list(map(lambda x: x[1], list(filter(lambda x: x[3] != "Closed", v["blocked"]))))
        priorities = list(filter(lambda x: x is not None, priorities))
        priorities.sort(reverse=True)
        issues_to_set[k]["predicted_priority"] = priorities[0] if priorities else None

    return issues_to_set

def generate_blocker_blocked_priority_data(db_path, project, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    output_file = f"{output_folder}/{project}_blocker_blocked_priority_data.json"
    data_dict = set_blocker_priority_to_blocked_priority(db_path)
    data_list = []
    for key, val in data_dict.items():
        blocked_keys = list(map(lambda x: x[0], val["blocked"]))
        blocked_priorities = list(map(lambda x: x[1], val["blocked"]))
        blocked_statuses = list(map(lambda x: x[3], val["blocked"]))
        priority = "null" if val["blocker_priority"] is None else val["blocker_priority"]
        predicted_priority = val["predicted_priority"]
        priority = f"0-{priority}" if priority != "null" and "-" not in priority else priority
        predicted_priority = f"0-{predicted_priority}" if predicted_priority and "-" not in predicted_priority else predicted_priority
        is_assumption_ok = priority != "null" and predicted_priority and priority >= predicted_priority
        is_assumption_ok = None if priority == "null" else is_assumption_ok
        row_dict = {
            "key": key,
            "priority": priority,
            "blocked_keys": blocked_keys,
            "blocked_priorities": blocked_priorities,
            "blocked_statuses": blocked_statuses,
            "is_all_blocked_closed": len(list(filter(lambda x: x != "Closed", blocked_statuses))) == 0,
            "blocked_count": len(blocked_keys),
            "predicted_priority": predicted_priority,
            "is_assumption_ok": is_assumption_ok
        }
        data_list.append(row_dict)

    with open(output_file, "w") as f:
        json.dump({"data": data_list}, f, indent=4)  # indent for pretty printing

    return output_file

# TODO: implement function
def generate_parent_children_priority_data(db_path, project, output_folder):
    output_file = f"{output_folder}/{project}_parent_children_priority_data.json"
    data_list = get_children_by_parent(db_path, field="priority")
    with open(output_file, "w") as f:
        json.dump({"data": data_list}, f, indent=4)  # indent for pretty printing
    return output_file

# TODO: implement function
def generate_parent_children_components_data(db_path, project, output_folder):
    output_file = f"{output_folder}/{project}_parent_children_components_data.json"
    data_list = get_children_by_parent(db_path, field="components")
    with open(output_file, "w") as f:
        json.dump({"data": data_list}, f, indent=4)  # indent for pretty printing
    return output_file

def apply_inheritance_rules(jira_issues, matching_rules_per_field=None):

    if matching_rules_per_field is None:
        matching_rules_per_field = {}

    issue_to_linked_issue_count = 0
    linked_issue_to_issue_count = 0
    updated_issues_per_filed = {"epic_link": [], "components": []}

    for issue in jira_issues:
        for field_name in matching_rules_per_field.keys():
            if not issue[field_name]:
                for link_type in matching_rules_per_field[field_name]:
                    for link_dict in issue["issuelinks"]:
                        link_key = link_dict["key"] if link_dict["type"] == link_type else None
                        if link_key:
                            link_field_values = list(filter(lambda x: x["key"] == link_key, jira_issues))
                            link_field_value = link_field_values[0][field_name] if link_field_values else None
                            if link_field_value:
                                issue[field_name] = link_field_value
                                issue_to_linked_issue_count += 1
                                # QF: using 1.1 to identify inheritance values
                                updated_issues_per_filed[field_name].append([issue["key"], link_field_value, 1.1, []])
                                break
                    if issue[field_name]:
                        break
            else:
                for link_type in matching_rules_per_field[field_name]:
                    for link_dict in issue["issuelinks"]:
                        link_key = link_dict["key"] if link_dict["type"] == link_type else None
                        if link_key:
                            link_field_values = list(filter(lambda x: x["key"] == link_key, jira_issues))
                            link_field_value = link_field_values[0][field_name] if link_field_values else None
                            if link_field_value and not link_field_values[0][field_name]:
                                linked_issue = link_field_values[0]
                                linked_issue[field_name] = issue[field_name]
                                linked_issue_to_issue_count += 1
                                updated_issues_per_filed[field_name].append([link_key, issue[field_name], 1.1, []])
                                break

    return updated_issues_per_filed

def check_if_linked_issues_share_field(jira_issues, field="components"):

    return_dict = {}

    labeled_issues = [i for i in jira_issues if field in i and i[field]]

    # Get issue link types:
    issue_link_fields = list(map(lambda x: x["issuelinks"], labeled_issues))
    issue_link_types = []
    for issue_link_field in issue_link_fields:
        for type_value in list(map(lambda x: x["type"], issue_link_field)):
            if type_value not in issue_link_types:
                issue_link_types.append(type_value)
    # Add 'parent' field if used
    if jira_issues and "parent" in jira_issues[0]:
        issue_link_types.append("parent")


    for issue in labeled_issues:
        issue_key = issue["key"]
        issue_field_value = issue[field]
        field_value_per_link_type = {}
        for issue_link in issue["issuelinks"]:
            link_type = issue_link["type"]
            link_key = issue_link["key"]
            link_issues = list(filter(lambda x: x["key"] == link_key, jira_issues))
            link_field_value = link_issues[0][field] if link_issues else None
            field_value_per_link_type[f"{link_type}:{link_key}"] = link_field_value

        # Add 'parent' field if used
        if jira_issues and "parent" in jira_issues[0]:
            parent_key = issue["parent"]
            if parent_key:
                parent_issue = list(filter(lambda x: x["key"] == parent_key, jira_issues))[0]
                field_value_per_link_type[f"parent:{parent_key}"] = parent_issue[field]

        if field_value_per_link_type:
            return_dict[issue_key] = {
                "field_value": issue_field_value,
                "field_value_per_link_type": field_value_per_link_type
            }

    stat_dict = {}
    for link_type in issue_link_types:
        stat_dict[link_type] = {"match": 0, "mismatch": 0}

    print("[DEBUG] return_dict:", return_dict)
    for k, v in return_dict.items():
        for kk, vv in v["field_value_per_link_type"].items():
            for link_type in issue_link_types:
                if vv and link_type in kk:
                    if vv == v["field_value"]:
                        stat_dict[link_type]["match"] += 1
                    else:
                        stat_dict[link_type]["mismatch"] += 1
    return stat_dict

def get_inheritance_rules_html(jira_issues, fields):
    inheritance_rules_html_str = ""
    for field in fields:
        inheritance_rules = check_if_linked_issues_share_field(jira_issues, field)
        readable_rules = match_dict_to_readable_msg(inheritance_rules, field)
        inheritance_rules_html_str += f"{readable_rules}<hr>"
    return inheritance_rules_html_str

def match_dict_to_readable_msg(match_dict, field_name):
    readable_rules = ""
    for k, v in match_dict.items():
        if v["match"] + v["mismatch"] != 0:
            match_prob = 100 * v["match"] / (v["match"] + v["mismatch"])
            match_prob_str = f'{v["match"]} / {v["match"] + v["mismatch"]}'
            readable_rule = f"The probability of an issue's '{field_name}' to match the '{field_name}' of the '{k}' issue is {match_prob:.2f}% [{match_prob_str}]"
            print(readable_rule)
            str1 = f"<b>'{field_name}'</b>"
            str2 = f"<b>'{k}'</b>"
            str3 = f"<b>{match_prob:.0f}%</b> [{match_prob_str}]"
            str3 = f"<mark>{str3}</mark>"  if match_prob == 100 else str3
            readable_rule = f"The probability of an issue's {str1} to match the {str1} of the {str2} issue is {str3}"
            readable_rules += f"{readable_rule}<br><br>"

    return readable_rules

def get_inheritance_rules(jira_issues, fields):

    inherit_dict = {}
    for field in fields:
        inherit_dict[field] = []
        stat_dict = check_if_linked_issues_share_field(jira_issues, field)
        for k, v in stat_dict.items():
            if v["mismatch"] == 0 and v["match"] > 0:
                inherit_dict[field].append(k)
    return inherit_dict

import difflib

def compare_files_and_get_diff(lines1, lines2):

    differ = difflib.Differ()
    diff = list(differ.compare(lines1, lines2))

    return diff

def get_predictable_fields(project_json, supported_fields=None, labeled_min_percentage=10):
    if supported_fields is None:
        supported_fields = ["epic_link", "components", "team"]

    with open(project_json, 'r', encoding='utf-8') as f:
        jira_issues = json.load(f)

    inferability_dir = str(Path(project_json).parent).replace("databases", "inferability_analysis")
    inferability_file = project_json.replace("databases", "inferability_analysis")
    if Path(inferability_file).is_file():
        with open(inferability_file, 'r', encoding='utf-8') as f:
            inferability_dict = json.load(f)
            if inferability_dict.get("labeled_min_percentage", None) == labeled_min_percentage:
                return inferability_dict.get("predictable_fields", [])

    predictable_fields = []
    labeled_data_per_field = {}
    for target_field in supported_fields:
        labeled_count = len(list(filter(lambda x: x.get(target_field, None), jira_issues)))
        unlabeled_count = len(jira_issues) - labeled_count
        labeled_percentage = 100 * labeled_count / len(jira_issues)
        labeled_data_per_field[target_field] = {
            "labeled_count": labeled_count,
            "unlabeled_count": unlabeled_count,
            "labeled_percentage": labeled_percentage
        }
        if labeled_min_percentage <= labeled_percentage < 100:
            predictable_fields.append(target_field)

    # Save to file
    Path(inferability_dir).mkdir(parents=True, exist_ok=True)
    with open(inferability_file, 'w', encoding='utf-8') as f:
        data = {
            "predictable_fields": predictable_fields,
            "labeled_data_per_field": labeled_data_per_field,
            "labeled_min_percentage": labeled_min_percentage
        }
        json.dump(data, f, ensure_ascii=False, indent=4)

    return predictable_fields

def get_target_fields_matrix(
        jira_issues,
        labeled_min_percentage=10,
        project_db_path=None
):

    if not jira_issues and project_db_path and Path(project_db_path).is_file():
        with open(project_db_path, 'r', encoding='utf-8') as file:
            jira_issues = json.load(file)

    field_names = list(jira_issues[0].keys()) if jira_issues else []
    issue_types = [item.get("issuetype", None) for item in jira_issues]
    issue_types = list(dict.fromkeys(issue_types))

    targetable_fields = [field for field in field_names if field not in UNPREDICTABLE_FIELDS]
    # Exclude unresolvable custom fields (eg. same friendly name for multiple custom id)
    targetable_fields = [field for field in targetable_fields if not field.startswith("customfield_")]
    # Exclude test-related fields
    targetable_fields = [field for field in targetable_fields if "test_" not in field]
    # Exclude time-estimate-related fields
    targetable_fields = [field for field in targetable_fields if not ("time" in field and field.endswith("estimate"))]
    inferable_fields, completed_fields = [], []
    inferable_fields_info = {}
    for field in targetable_fields:
        labeled_issues = [issue for issue in jira_issues if issue.get(field, None)]
        labeled_count = len(labeled_issues)
        labeled_percentage = 100 * labeled_count / len(jira_issues)
        if labeled_min_percentage <= labeled_percentage < 100:
            labeled_count_per_issue_type = {}
            for issue_type in issue_types:
                _labeled_issues = [issue for issue in labeled_issues if issue.get("issuetype", None) == issue_type]
                labeled_count_per_issue_type[issue_type] = len(_labeled_issues)

            inferable_fields.append(field)
            inferable_fields_info[field] = {
                "labeled_percentage": labeled_percentage,
                "labeled_count": labeled_count,
                "test_data_size": int(labeled_count / 5),
                "labeled_count_per_issue_type": labeled_count_per_issue_type,
                "total_issues": len(jira_issues)
            }
        elif  labeled_percentage == 100:
            completed_fields.append(field)

    return {
        "inferable_fields": inferable_fields,
        "issue_types": issue_types,
        "inferable_fields_info": inferable_fields_info
    }


def get_target_fields_matrix_per_project(project_names=None) -> dict[Any, Any]:
    if project_names is None:
        project_names = []
    target_fields_matrix_per_project = {}
    for file_path in Path(DATABASES_SETTINGS_FOLDER).glob('*.json'):
        project_name = Path(file_path).stem.replace("_settings", "")
        if project_names and project_name not in project_names:
            continue
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            project_key = f"{data.get('projectKey')}_{data.get('exportedAt')}"
            target_fields_matrix_per_project[project_key] = data.get("target_fields_matrix")
    return target_fields_matrix_per_project

def get_saved_target_fields_matrix_per_project():
    latest_target_fields_matrix_per_project = {}
    metadata_per_project = {}
    for file_path in Path(INFERABILITY_ANALYSIS).glob('*_grid.json'):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            project_key = Path(file_path).stem.split('_grid')[0]
            latest_target_fields_matrix_per_project[project_key] = data["data"]
            metadata_per_project[project_key] = data["metadata"]
    return latest_target_fields_matrix_per_project, metadata_per_project

def get_best_performance_per_project():
    best_performance_per_project = {}
    if Path(PERFORMANCE_FOLDER).exists():
        for file_path in Path(PERFORMANCE_FOLDER).glob('*.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                project_key = Path(file_path).stem
                best_performance_per_project[project_key] = data.get("best_model_per_field")
    return best_performance_per_project

if __name__ == "__main__":
    pass
    # best_performance_per_project = get_best_performance_per_project()
    # print("[DEBUG] matrix:", best_performance_per_project)

    # db_file = r"C:\Users\wm080\Documents\Projects\JFIP-219_Branch\jfip_web_ui\databases\DEMO_20260724_094223.json"
    # with open(db_file, 'r', encoding='utf-8') as f:
    #     jira_issue_list = json.load(f)
    # matrix = get_target_fields_matrix(jira_issue_list)
    # print("[DEBUG] matrix:", matrix)

    # settings_dir = r"C:\Users\wm080\Documents\Projects\JFIP-219_Branch\jfip_web_ui\databases\settings"
    # matrix_per_project = get_target_fields_matrix_per_project(settings_dir)
    # print("[DEBUG] matrix_per_project:", matrix_per_project)

    # inferability_analysis_dir = r"C:\Users\wm080\Documents\Projects\JFIP-219_Branch\jfip_web_ui\inferability_analysis"
    # matrix_per_project = get_latest_target_fields_matrix_per_project(inferability_analysis_dir)
    # print("[DEBUG] matrix_per_project:", matrix_per_project)