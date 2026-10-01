import copy
import json
import math
import re

import nltk
import numpy as np
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from config.constants import KEYWORDS_TO_IGNORE

# CONSTANTS
EXTRA_DEPENDENCY_FIELDS = [] #[ "components" ]

nltk.download('wordnet')
nltk.download('omw-1.4')
nltk.download('stopwords')
lemmatizer = WordNetLemmatizer()
model = SentenceTransformer('all-MiniLM-L6-v2')

def remove_keywords_to_ignore(text):
    for keyword_regex in KEYWORDS_TO_IGNORE:
        text = re.sub(keyword_regex, '', text)
    return text

def clean_and_lemmatize(text):
    stop_words = set(stopwords.words('english'))
    text = remove_keywords_to_ignore(text)
    text = re.sub(r"[^a-zA-Z]", " ", text.lower())  # Remove punctuation and lowercase
    words = text.split()
    lemmas = [lemmatizer.lemmatize(word) for word in words if word not in stop_words]
    return " ".join(lemmas)

def extract_priority_keywords(keyword_json):
    keywords = {}
    for entry in keyword_json:
        for priority, words in entry.items():
            priority = priority.upper()
            if priority not in keywords:
                keywords[priority] = []
            keywords[priority].extend([w.lower() for w in words])
    return keywords

def combine_text(issue):
    combined_text = f"{issue.get('summary', '')} {issue.get('description', '')}"
    for filed in EXTRA_DEPENDENCY_FIELDS:
        combined_text += f"{issue.get(filed, '')}"
    return  combined_text

def get_cluster_centroid(cluster_keys, jira_issues):
    texts = []
    for issue_key in cluster_keys:
        issue_data = list(filter(lambda x: x["key"] == issue_key, jira_issues))[0]
        texts.append(clean_and_lemmatize(combine_text(issue_data)))
    embeddings = model.encode(texts)
    centroid = np.mean(embeddings, axis=0)
    similarities = cosine_similarity([centroid], embeddings)[0]
    most_representative_index = np.argmax(similarities)
    most_representative_issue = cluster_keys[most_representative_index]
    return most_representative_issue

def json_file_to_dict(json_file):
    data_dict = {}
    try:
        with open(json_file, 'r', encoding="utf8") as file:
            data_dict = json.load(file)
    except FileNotFoundError:
        print(f"Error: The file '{json_file}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{json_file}'. Check file format.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return data_dict

def get_target_field_possible_values(db_file, target_fields, db_issues=None):
    target_field_possible_values = {}
    jira_issues = json_file_to_dict(db_file) if db_issues is None else db_issues

    for target_field in target_fields:
        target_field_list = list(map(lambda x: x[target_field], jira_issues))
        target_field_list = list(filter(lambda x: x and str(x) != "[]", target_field_list))
        if len(target_field_list) == 0:
            continue
        if isinstance(target_field_list[0], list):
            unique_tuples = set(tuple(sublist) for sublist in target_field_list)
            unique_target_field_list = [list(tup) for tup in unique_tuples]
        else:
            unique_target_field_list = list(set(target_field_list))
        target_field_possible_values[f"{target_field}_values"] = unique_target_field_list

    total_unlabeled_fields = 0
    unlabeled_count_per_field = {}
    for target_field in target_fields:
        unlabeled_fields = len(list(filter(
            lambda x: x[target_field] is None or str(x[target_field]) == "[]",
            jira_issues
        )))
        total_unlabeled_fields += unlabeled_fields
        unlabeled_count_per_field[target_field.capitalize()] = unlabeled_fields
    unlabeled_count_per_field["Total"] = total_unlabeled_fields
    return target_field_possible_values, unlabeled_count_per_field

def list_items_to_boolean_fields(jira_issues, list_possible_values, target_field):
    count_per_value = {}
    for jira_issue in jira_issues:
        for value in list_possible_values:
            if value not in count_per_value:
                count_per_value[value] = 0
            if jira_issue[target_field]:
                if value in jira_issue[target_field]:
                    jira_issue[value] = 'true'
                    count_per_value[value] += 1
                else:
                    jira_issue[value] = 'false'
            else:
                jira_issue[value] = None

    return jira_issues

def boolean_fields_to_list(predictions_per_value, confidence_threshold=0.75):
    if not predictions_per_value:
        return []
    prediction_list = copy.deepcopy(list(predictions_per_value.values())[0])
    for value, prediction_dicts in predictions_per_value.items():
        prediction_dicts_ = prediction_dicts if isinstance(prediction_dicts, list) else [prediction_dicts]
        for index, prediction_dict in enumerate(prediction_dicts_):
            # TODO: find nan error root cause
            # Quick fix: nan error
            if math.isnan(prediction_dict["confidence"]):
                prediction_dict["confidence"] = 0.001

            if not isinstance(prediction_list[index]["prediction"], list):
                prediction_list[index]["prediction"] = []
                prediction_list[index]["confident_prediction"] = []
                prediction_list[index]["confidence_list"] = []
                prediction_list[index]["false_confidence_list"] = []

            if prediction_dict["prediction"] == "true":
                prediction_list[index]["prediction"].append(value)
                prediction_list[index]["confidence_list"].append(prediction_dict["confidence"])
                if prediction_dict["confidence"] >= confidence_threshold:
                    prediction_list[index]["confident_prediction"].append(value)
            if prediction_dict["prediction"] == "false":
                prediction_list[index]["false_confidence_list"].append(prediction_dict["confidence"])

    for prediction in prediction_list:
        if "confidence_list" in prediction and prediction["confidence_list"]:
            prediction["confidence"] = sum(prediction["confidence_list"]) / len(prediction["confidence_list"])
        elif "false_confidence_list" in prediction and prediction["false_confidence_list"]:
            prediction["confidence"] = sum(prediction["false_confidence_list"]) / len(prediction["false_confidence_list"])
        else:
            prediction["confidence"] = -1
        if not prediction["prediction"]:
            prediction["prediction"] = []
    return prediction_list

def compute_list_accuracy_score(expected_list, actual_list):
    score = 0
    for item in actual_list:
        score_inc = 1 if item in expected_list else -1
        score += score_inc
    return int(100 * score / len(expected_list))

def compute_predictions_accuracy(prediction_list, list_accuracy_score_threshold=25):
    perf_metrics = _compute_predictions_accuracy(prediction_list, list_accuracy_score_threshold, 0.9)
    if "err_msg" not in prediction_list:
        prediction_test_list = [item for item in prediction_list if item.get("expected", None)]
        no_test_predictions = [item for item in prediction_list if not item["is_split_test"]]
        accuracy_per_confidence = {}
        if prediction_test_list:
            confidence_list = list(set(list(map(lambda x: x["confidence"], prediction_test_list))))
            confidence_list.sort()
            for confidence_percent in range(95, 49, -5):
                confidence = confidence_percent / 100
                confident_predictions = [item for item in prediction_test_list if item["confidence"] >= confidence]
                no_test_confident_predictions = [item for item in no_test_predictions if item["confidence"] >= confidence]
                if not confident_predictions:
                    continue
                cur_perf_metrics = compute_predictions_accuracy_(confident_predictions, list_accuracy_score_threshold)
                accuracy_per_confidence[str(confidence_percent)] = {
                    "f1_score": cur_perf_metrics.get("f1_score", None),
                    "accuracy": cur_perf_metrics.get("accuracy", None),
                    "basic_accuracy": cur_perf_metrics.get("basic_accuracy", None),
                    "confident_predictions_percentage": 100 * len(no_test_confident_predictions) / len(no_test_predictions),
                    "test_data_size": len(prediction_test_list)
                }
            print("[DEBUG] accuracy_per_confidence:", accuracy_per_confidence)
            perf_metrics.update({
                "accuracy_per_confidence": accuracy_per_confidence
            })
        else:
            pass
            # print("[DEBUG] prediction_list:", prediction_list)

    return perf_metrics

def _compute_predictions_accuracy(prediction_list, list_accuracy_score_threshold=25, min_accuracy=0.9):
    perf_metrics = compute_predictions_accuracy_(prediction_list, list_accuracy_score_threshold)
    optimal_confidence = perf_metrics.get("avg_confidence", 0)
    # Quick fix.
    optimal_confidence = 0.75 if math.isnan(optimal_confidence) else optimal_confidence
    optimal_f1_score = perf_metrics.get("f1_score", 0)
    optimal_confidence_predictions_precent = 0
    optimal_accuracy = perf_metrics.get("basic_accuracy", 0)

    is_increase_confidence = perf_metrics.get("basic_accuracy", 0) < min_accuracy
    if is_increase_confidence:
        if optimal_confidence and np.isfinite([perf_metrics["avg_confidence"], 0.99, 0.01]).all():
            for confidence_threshold in np.arange(perf_metrics["avg_confidence"], 0.99, 0.01):
                no_test_prediction_list = list(filter(lambda x: not x["is_split_test"], prediction_list))
                confident_prediction_list = list(filter(lambda x: x["confidence"] >= confidence_threshold, prediction_list))
                no_test_confident_prediction_list = list(filter(lambda x: not x["is_split_test"], confident_prediction_list))
                cur_perf_metrics = compute_predictions_accuracy_(confident_prediction_list, list_accuracy_score_threshold)
                #print("[DEBUG] cur_perf_metrics:", cur_perf_metrics)
                #print(f"[DEBUG] Checking confidence_threshold {confidence_threshold}: basic_accuracy {cur_perf_metrics["basic_accuracy"]}")
                if not cur_perf_metrics.get("basic_accuracy", None):
                    print("[DEBUG] breaking loop cur_perf_metrics.get('basic_accuracy', None):", cur_perf_metrics.get("basic_accuracy", None))
                    break
                if cur_perf_metrics["basic_accuracy"] > optimal_accuracy:
                    optimal_confidence = confidence_threshold.item()
                    optimal_accuracy = cur_perf_metrics["basic_accuracy"]
                    optimal_f1_score = cur_perf_metrics["f1_score"]
                    optimal_confidence_predictions_precent = 100 * len(no_test_confident_prediction_list) / len(no_test_prediction_list)
                if optimal_accuracy >= min_accuracy:
                    print(f"[DEBUG] breaking loop optimal_accuracy >= min_accuracy {min_accuracy}")
                    print("[DEBUG] optimal_accuracy:", optimal_accuracy)
                    break
    else:
        print("[DEBUG] decreasing the confidence ...")
        pass

    perf_metrics.update({
        "optimal_confidence": optimal_confidence,
        "optimal_accuracy": optimal_accuracy,
        "optimal_f1_score": optimal_f1_score,
        "optimal_confidence_predictions_precent": optimal_confidence_predictions_precent
    })
    return perf_metrics

def compute_predictions_accuracy_(prediction_list, list_accuracy_score_threshold):
    pass_count = 0
    is_list = isinstance(prediction_list, list)
    if not is_list:
        print("[DEBUG] prediction_list is not a list")
        # print("[DEBUG] prediction_list:", prediction_list)
        return {}
    if is_list and prediction_list and not isinstance(prediction_list[0], dict):
        print("[DEBUG] prediction_list[0] is not a dict")
        print("[DEBUG] prediction_list[0]:", prediction_list[0])
        return {}

    prediction_test_list = list(filter(lambda x: x.get("expected", None) is not None, prediction_list))

    for prediction in prediction_test_list:
        if prediction.get("accuracy_score", None):
            pass_count += 1 if prediction["accuracy_score"] >= list_accuracy_score_threshold else 0
        else:
            pass_count += 1 if prediction["prediction"] == prediction["expected"] else 0
    basic_accuracy = pass_count / len(prediction_test_list) if prediction_test_list else None

    # Confusion Matrix
    perf_metrics = {}
    expected_values = list(map(lambda x: x["expected"], prediction_test_list))
    if expected_values:
        if isinstance(expected_values[0], list):
            expected_values = list(set(sum(expected_values, [])))
        else:
            expected_values = list(set(expected_values))

        total_tp, total_tn, total_fp, total_fn = 0, 0, 0, 0
        for expected_value in expected_values:
            for prediction in prediction_test_list:
                if isinstance(expected_value, float):
                    check_is_match = lambda a, b: a == b
                else:
                    check_is_match = lambda a, b: a in b
                if check_is_match(expected_value, prediction["expected"]):
                    total_tp += 1 if check_is_match(expected_value, prediction["prediction"]) else 0
                    total_fn += 1 if not check_is_match(expected_value, prediction["prediction"]) else 0
                else:
                    total_fn += 1 if check_is_match(expected_value, prediction["prediction"]) else 0
                    total_tn += 1 if not check_is_match(expected_value, prediction["prediction"]) else 0

        confidence_list = list(map(lambda x: x["confidence"], prediction_list))
        avg_confidence = sum(confidence_list) / len(confidence_list)
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0
        perf_metrics = {
            "precision": precision,
            "recall": recall,
            "accuracy": (total_tp + total_tn) / (total_tp + total_fp + total_tn + total_fn),
            "f1_score": f1_score,
            "basic_accuracy": basic_accuracy,
            "avg_confidence": avg_confidence,
        }

    return perf_metrics


def group_predictions_per_value(all_predictions):
    target_fields = list(set(list(map(lambda x: x["field"], all_predictions))))
    predictions_per_value = {}
    not_predictable = []
    total_values = 0
    for target_field in target_fields:
        predictions_per_value[target_field] = {}
        predictions = list(filter(lambda x: x["field"] == target_field, all_predictions))
        # prediction_values = list(map(lambda x: x["prediction"], predictions))
        for prediction in predictions:
            prediction_value = prediction["prediction"]
            if prediction_value is None:
                not_predictable.append(prediction)
                continue
            if isinstance(prediction_value, list):
                prediction_value = [v for v in prediction_value if v]
                if not prediction_value:
                    not_predictable.append(prediction)
                    continue
                prediction_value.sort()
                prediction_value = ",".join(prediction_value)
            elif isinstance(prediction_value, str) and not prediction_value.strip():
                not_predictable.append(prediction)
                continue
            if prediction_value not in predictions_per_value[target_field]:
                predictions_per_value[target_field][prediction_value] = []
                total_values += 1
            predictions_per_value[target_field][prediction_value].append(prediction["key"])
            # predictions_per_value[target_field][prediction_value].append((prediction["key"], prediction["accuracy"]))

    return predictions_per_value, total_values, not_predictable


if __name__ == "__main__":
    prediction_file = "predictions/review/DEMO_20260303_212037.json"
    with open(prediction_file, 'r', encoding='utf-8') as file:
        predictions = json.load(file)
    group_predictions_per_value(predictions["data"])
