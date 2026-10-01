import json
import os
import random

from nlp.centroid_manager import list_items_to_boolean_fields, get_target_field_possible_values
from reporting.audit_generator import dump_json_to_file
from config.constants import TEST_JSON_FILE, RAND_TEST_JSON_FILE, TEST_RESULTS_JSON_FILE

def generate_test_results_json(inference_json_path, inference_test_results=TEST_RESULTS_JSON_FILE):
    test_results = []
    for test in  run_random_tests(inference_json_path):
        key = test["key"]
        field = test["field"]
        predicted = test["predicted_value"]
        expected = test["expected_value"]
        accuracy = test["prediction_accuracy"]
        status = str(predicted).lower().strip() == str(expected).lower().strip()
        status = status or str(predicted).lower().strip() in str(expected).lower().strip()
        status = status or str(expected).lower().strip() in str(predicted).lower().strip()
        status_str = "PASS" if status else "FAIL"
        status_str = "INCONCLUSIVE" if status_str == "FAIL" and float(accuracy) < 0.6 else status_str
        status_class = "bg-success" if status else "bg-danger"
        status_class = "bg-warning" if status_str == "INCONCLUSIVE" else status_class
        status_class = f"{status_class} bg-gradient"

        test_results.append({
            "key": key,
            "field": field,
            "expected": expected,
            "inferred": predicted,
            "accuracy": accuracy,
            "status": status_str,
            "status_class": status_class
        })

    # Test Summary String
    total_count = len(test_results)
    pass_count = len(list(filter(lambda x: x["status"] == "PASS", test_results)))
    fail_count = len(list(filter(lambda x: x["status"] == "FAIL", test_results)))
    inconclusive_count = len(list(filter(lambda x: x["status"] == "INCONCLUSIVE", test_results)))

    test_summary_str = f"Passed: {pass_count}"
    test_summary_str += f", Failed: {fail_count}"
    test_summary_str += f", Inconclusive: {inconclusive_count}"
    test_summary_str += f", Total: {total_count}"

    dump_json_to_file(
        {"data": test_results}, inference_test_results)
    return inference_test_results, test_summary_str

def generate_report_html(inference_json_path):
    test_results = run_random_tests(inference_json_path)
    html_str = """
      <table class="table">
        <thead>
          <tr class="fs-6"><th>Issue Key</th><th>Target Field</th><th>Expected Value</th><th>Inferred Value</th><th>Accuracy</th><th>Status</th></tr>
        </thead>
        <tbody>
    """
    for test in test_results:
        key = test["key"]
        field = test["field"]
        predicted = test["predicted_value"]
        expected = test["expected_value"]
        accuracy = test["prediction_accuracy"]
        status = str(predicted).lower().strip() == str(expected).lower().strip()
        status = status or str(predicted).lower().strip() in str(expected).lower().strip()
        status = status or str(expected).lower().strip() in str(predicted).lower().strip()
        status_str = "PASS" if status else "FAIL"
        # status_str = status_str if float(accuracy) >= 0.6 else "INCONCLUSIVE"
        status_str = "---" if status_str == "FAIL" and float(accuracy) < 0.6 else status_str
        status_class = "table-success" if status else "table-danger"
        status_class = "table-warning" if status_str == "---" else status_class
        html_str += f"<tr class='fs-6 {status_class}'><td>{key}</td><td>{field}</td><td>{expected}</td><td>{predicted}</td><td>{accuracy}</td><td>{status_str}</td></tr>"
    html_str += "</tbody></table>"
    return html_str

def run_tests(inference_json_path):
    tests_per_project = {}
    with open(TEST_JSON_FILE, 'r') as file:
        tests_per_project = json.load(file)

    test_results = []
    project = os.path.basename(inference_json_path).split('_')[0]
    test_keys = list(map(lambda x: x["key"], tests_per_project.get(project, [])))

    test_data = []
    with open(inference_json_path, 'r') as file:
        data = json.load(file)["data"]
        test_data = list(filter(lambda x: x["key"] in test_keys, data))

    for test in  tests_per_project.get(project, []):
        filtered_test_data = list(filter(lambda x: x["key"] == test["key"], test_data))
        if len(filtered_test_data) == 1:
            test["predicted_value"] = filtered_test_data[0]["prediction"]
            test["prediction_accuracy"] = filtered_test_data[0]["accuracy"]
            test_results.append(test)

    return test_results

def run_random_tests(inference_json_path):
    tests_per_project = {}
    with open(RAND_TEST_JSON_FILE, 'r') as file:
        random_tests = json.load(file)

    test_results = []
    # project = os.path.basename(inference_json_path).split('_')[0]
    test_keys = list(map(lambda x: x["key"], random_tests))

    test_data = []
    with open(inference_json_path, 'r') as file:
        data = json.load(file)["data"]
        test_data = list(filter(lambda x: x["key"] in test_keys, data))

    for test in  random_tests:
        filtered_test_data = list(filter(lambda x: x["key"] == test["key"] and x["field"] == test["field"], test_data))
        if len(filtered_test_data) != 0:
            test["predicted_value"] = filtered_test_data[0]["prediction"]
            test["prediction_accuracy"] = filtered_test_data[0]["accuracy"]
            test_results.append(test)

    return test_results

def reset_ramdom_test():
    if os.path.exists(RAND_TEST_JSON_FILE):
        os.remove(RAND_TEST_JSON_FILE)

def select_random_issues_from_train_issues_to_test_inference(
        train_issues,
        target_field,
        test_issues_percentage=0.2,
        test_rand_seed=0,
        issues_to_exclude=None
):
    random_issues = None
    is_bad_train_data = True
    cur_test_rand_seed = test_rand_seed
    retry_count, max_retry = 0, 10
    while is_bad_train_data and retry_count < max_retry:
        retry_count += 1
        random_issues =  select_random_issues_from_train_issues_to_test_inference_(
            train_issues,
            target_field,
            test_issues_percentage,
            cur_test_rand_seed,
            issues_to_exclude
        )
        # Check train data has at leats 2 classes to avoid errors
        train_data_bad_items = get_train_data_bad_items(train_issues, random_issues, target_field)
        print(f"[DEBUG] test_rand_seed: {cur_test_rand_seed}, train_data_bad_items: {train_data_bad_items}")
        is_bad_train_data = len(train_data_bad_items) != 0
        cur_test_rand_seed += 1 if is_bad_train_data else 0

    print("[DEBUG] used test_rand_seed:", cur_test_rand_seed)
    return random_issues

def get_train_data_bad_items(train_issues, test_issues, target_field):
    train_data_bad_items = {}
    if isinstance(train_issues[0][target_field], list):
        test_issue_keys = list(map(lambda x: x["key"], test_issues))
        train_issues_minus_tests = list(filter(lambda x: x["key"] not in test_issue_keys, train_issues))

        possible_values_tuple = get_target_field_possible_values(
            None,
            [target_field],
            db_issues=train_issues)

        possible_values = possible_values_tuple[0][f"{target_field}_values"]
        flattened_possible_values = [item for sublist in possible_values for item in sublist]
        bool_target_fields = list(set(flattened_possible_values))
        # print("[DEBUG] bool_target_fields:", bool_target_fields)

        bool_train_issues = list_items_to_boolean_fields(
            train_issues_minus_tests,
            bool_target_fields, target_field
        )

        # print("[DEBUG] len(bool_train_issues):", len(bool_train_issues))
        for bool_target_field in bool_target_fields:
            # labeled_bool_train_issues = list(filter(lambda x: x[bool_target_field] is not None, bool_train_issues))
            # print(f"[DEBUG] bool_target_field: {bool_target_field} len(labeled_bool_train_issues):", len(labeled_bool_train_issues))
            true_count = len(list(filter(lambda x: x[bool_target_field] == "true", bool_train_issues)))
            false_count = len(list(filter(lambda x: x[bool_target_field] == "false", bool_train_issues)))
            print(f"[DEBUG] {bool_target_field}, true_count: {true_count}, false_count: {false_count}")
            if true_count == 0 or false_count == 0:
                train_data_bad_items[bool_target_field] = {"true_count": true_count, "false_count": false_count}
                # print(f"[DEBUG] {bool_target_field}, true_count: {true_count}, false_count: {false_count}")

    return train_data_bad_items

def select_random_issues_from_train_issues_to_test_inference_(
        train_issues,
        target_field,
        test_issues_percentage=0.2,
        test_rand_seed=0,
        issues_to_exclude=None
):
    # Select issues
    test_issues_length = int(len(train_issues) * test_issues_percentage)
    random.seed(test_rand_seed)

    # Exclude issues if needed
    if issues_to_exclude:
        for couple in issues_to_exclude:
            key, val = couple
            train_issues = list(filter(lambda x: x[key] != val, train_issues))

    random_issues = random.sample(train_issues, test_issues_length)

    random_tests = []
    for random_issue in random_issues:
        random_tests.append({
            "field": target_field,
            "key": random_issue["key"],
            "type": random_issue["issuetype"],
            "summary": random_issue["summary"],
            "expected_value": random_issue[target_field]
        })

    # Update test JSON file
    all_random_tests = []
    # if os.path.exists(RAND_TEST_JSON_FILE):
    #     with open(RAND_TEST_JSON_FILE, 'r') as file:
    #         all_random_tests = json.load(file)

    all_random_tests.extend(random_tests)

    # Debug file
    dump_json_to_file(all_random_tests, RAND_TEST_JSON_FILE)

    return random_issues

if __name__ == "__main__":

    project_json = r"C:\Users\wm080\Documents\Projects\llm_usage_logic\jfip_web_ui\databases\AURORATEST_LLM.json"
    with open(project_json, 'r', encoding='utf-8') as file:
        jira_issues = json.load(file)

    target_field = "components"
    labeled_data = list(filter(lambda x: x[target_field], jira_issues))
    print("[DEBUG] len(labeled_data):", len(labeled_data))
    test_data = select_random_issues_from_train_issues_to_test_inference_(
        labeled_data,
        target_field,
        test_issues_percentage=0.2,
        test_rand_seed=925,
        issues_to_exclude=None
    )
    print("[DEBUG] len(test_data):", len(test_data))

    train_data_bad_items = get_train_data_bad_items(labeled_data, test_data, target_field)
    print("[DEBUG] train_data_bad_items:", train_data_bad_items)

    # possible_values_tuple = get_target_field_possible_values(project_json, [target_field])
    # possible_values = possible_values_tuple[0][f"{target_field}_values"]
    # flattened_possible_values = [item for sublist in possible_values for item in sublist]
    # bool_target_fields = list(set(flattened_possible_values))
    # print("[DEBUG] bool_target_fields:", bool_target_fields)
    #
    # jira_issues = list_items_to_boolean_fields(jira_issues, bool_target_fields, target_field)
    # # print("[DEBUG] jira_issues[0]:", jira_issues[0])
    #
    # bad_labeled_data = {}
    # for bool_target_field in bool_target_fields:
    #
    #     labeled_data = list(filter(lambda x: x[bool_target_field] is not None, jira_issues))
    #     print("[DEBUG] len(labeled_data):", len(labeled_data))
    #     test_data = select_random_issues_from_train_issues_to_test_inference(
    #         labeled_data,
    #         bool_target_field,
    #         test_issues_percentage=0.2,  # Test data size is 20% of labeled data
    #         test_rand_seed=912,
    #         issues_to_exclude=None  # [("issuetype", "Epic")]
    #     )
    #     print("[DEBUG] len(test_data):", len(test_data))
    #     test_data_keys = list(map(lambda x: x["key"], test_data))
    #     train_data = list(filter(lambda x: x["key"] not in test_data_keys, jira_issues))
    #     print("[DEBUG] len(train_data):", len(train_data))
    #
    #     true_count = len(list(filter(lambda x: x[bool_target_field] == "true", train_data)))
    #     false_count = len(list(filter(lambda x: x[bool_target_field] == "false", train_data)))
    #     none_count = len(list(filter(lambda x: x[bool_target_field] is None, train_data)))
    #     print("[DEBUG] none_count:", none_count)
    #
    #     if true_count == 0 or false_count == 0:
    #         print(f"[DEBUG] {bool_target_field}: true_count {true_count}; false_count {false_count}")
    #         bad_labeled_data[bool_target_field] = {"true_count": true_count, "false_count": false_count}
    #
    #
    #
    # print("[DEBUG] bad_labeled_data:", bad_labeled_data)

    # inference_file = "CIA_20250905_131407/CIA_inferred.json"
    # test_results = run_random_tests(inference_file)
    # for test_result in test_results:
    #     print(test_results)
