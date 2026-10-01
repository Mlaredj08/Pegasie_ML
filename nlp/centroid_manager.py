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
from ml.metrics import evaluate_prediction_records, list_jaccard_percent, select_confidence_threshold

# CONSTANTS
EXTRA_DEPENDENCY_FIELDS = [] #[ "components" ]

nltk.download('wordnet')
nltk.download('omw-1.4')
nltk.download('stopwords')
lemmatizer = WordNetLemmatizer()
_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model

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
    embeddings = _get_embedding_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
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
    """Merge one-vs-rest predictions by Jira issue key, never by list index."""
    if not predictions_per_value:
        return []

    merged = {}
    order = []
    for value, prediction_dicts in predictions_per_value.items():
        items = (
            prediction_dicts
            if isinstance(prediction_dicts, list)
            else [prediction_dicts]
        )
        for prediction_dict in items:
            issue_key = (
                prediction_dict.get("issue_key")
                or prediction_dict.get("key")
            )
            if issue_key is None:
                continue
            if issue_key not in merged:
                item = copy.deepcopy(prediction_dict)
                item["prediction"] = []
                item["confident_prediction"] = []
                item["confidence_list"] = []
                item["false_confidence_list"] = []
                merged[issue_key] = item
                order.append(issue_key)

            item = merged[issue_key]
            try:
                confidence = float(
                    prediction_dict.get("confidence", 0.0)
                )
                if not math.isfinite(confidence):
                    confidence = 0.0
            except (TypeError, ValueError):
                confidence = 0.0

            predicted = str(
                prediction_dict.get("prediction")
            ).lower()
            if predicted == "true":
                item["prediction"].append(value)
                item["confidence_list"].append(confidence)
                if confidence >= confidence_threshold:
                    item["confident_prediction"].append(value)
            elif predicted == "false":
                item["false_confidence_list"].append(confidence)

    result = [merged[key] for key in order]
    for prediction in result:
        if prediction["confidence_list"]:
            prediction["confidence"] = (
                sum(prediction["confidence_list"])
                / len(prediction["confidence_list"])
            )
        elif prediction["false_confidence_list"]:
            prediction["confidence"] = (
                sum(prediction["false_confidence_list"])
                / len(prediction["false_confidence_list"])
            )
        else:
            prediction["confidence"] = 0.0
    return result


def compute_list_accuracy_score(expected_list, actual_list):
    """Compatibility wrapper returning Jaccard similarity (0..100)."""
    return list_jaccard_percent(expected_list, actual_list)


def compute_predictions_accuracy(
    prediction_list,
    list_accuracy_score_threshold=25,
    min_accuracy=0.9,
):
    """Compute exact metrics and confidence/coverage curves."""
    perf_metrics = _compute_predictions_accuracy(
        prediction_list,
        list_accuracy_score_threshold=list_accuracy_score_threshold,
        min_accuracy=min_accuracy,
    )
    if not isinstance(prediction_list, list):
        return perf_metrics

    prediction_test_list = [
        item
        for item in prediction_list
        if item.get("expected") is not None
    ]
    no_test_predictions = [
        item
        for item in prediction_list
        if not item.get("is_split_test")
    ]
    accuracy_per_confidence = {}
    for confidence_percent in range(95, 49, -5):
        threshold = confidence_percent / 100
        confident_tests = [
            item
            for item in prediction_test_list
            if float(item.get("confidence", 0) or 0) >= threshold
        ]
        if not confident_tests:
            continue
        cur_metrics = evaluate_prediction_records(confident_tests)
        confident_prod = [
            item
            for item in no_test_predictions
            if float(item.get("confidence", 0) or 0) >= threshold
        ]
        coverage = (
            100 * len(confident_prod) / len(no_test_predictions)
            if no_test_predictions
            else 0.0
        )
        accuracy_per_confidence[str(confidence_percent)] = {
            "f1_score": cur_metrics.get("f1_score"),
            "accuracy": cur_metrics.get("accuracy"),
            "basic_accuracy": cur_metrics.get(
                "basic_accuracy"
            ),
            "confident_predictions_percentage": coverage,
            "test_data_size": len(prediction_test_list),
        }
    if accuracy_per_confidence:
        perf_metrics[
            "accuracy_per_confidence"
        ] = accuracy_per_confidence
    return perf_metrics


def _compute_predictions_accuracy(
    prediction_list,
    list_accuracy_score_threshold=25,
    min_accuracy=0.9,
):
    del list_accuracy_score_threshold
    perf_metrics = (
        evaluate_prediction_records(prediction_list)
        if isinstance(prediction_list, list)
        else {}
    )
    if not perf_metrics:
        return perf_metrics

    threshold_result = select_confidence_threshold(
        prediction_list,
        target_score=min_accuracy,
        metric_name="basic_accuracy",
    )
    threshold = threshold_result["threshold"]
    no_test_predictions = [
        item
        for item in prediction_list
        if not item.get("is_split_test")
    ]
    confident_prod = [
        item
        for item in no_test_predictions
        if float(item.get("confidence", 0) or 0) >= threshold
    ]
    production_coverage = (
        100 * len(confident_prod) / len(no_test_predictions)
        if no_test_predictions
        else 100 * threshold_result["coverage"]
    )
    perf_metrics.update({
        "optimal_confidence": threshold,
        "optimal_accuracy": threshold_result["score"],
        "optimal_f1_score": threshold_result["metrics"].get(
            "f1_score",
            perf_metrics.get("f1_score", 0.0),
        ),
        "optimal_confidence_predictions_precent": (
            production_coverage
        ),
        "meets_target_accuracy": threshold_result[
            "meets_target"
        ],
    })
    return perf_metrics


def compute_predictions_accuracy_(
    prediction_list,
    list_accuracy_score_threshold=25,
):
    del list_accuracy_score_threshold
    return (
        evaluate_prediction_records(prediction_list)
        if isinstance(prediction_list, list)
        else {}
    )

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
