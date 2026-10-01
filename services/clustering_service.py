# A python function that takes as parameter a list of Jira issues
# Does a centroid-based clustering using the description and the summary
# And returns a list of dicts { issues: ["key1", "key5", "key15"...], centroid: "key3", similarity_score: 0.8}
import json
from typing import List, Dict, Any
import numpy as np

from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from config import STATUSES_TO_EXCLUDE
from config.logger import Logger
from nlp.centroid_manager import group_predictions_per_value

_EMBEDDING_MODELS = {}


def _get_embedding_model(model_name: str):
    if model_name not in _EMBEDDING_MODELS:
        _EMBEDDING_MODELS[model_name] = SentenceTransformer(model_name)
    return _EMBEDDING_MODELS[model_name]



def cluster_jira_issues(
        issues: List[Dict[str, Any]],
        min_clusters: int = 2,
        max_clusters: int = 10,
        duplicate_threshold: float = 0.95,
        embedding_model: str = "all-MiniLM-L6-v2",
) -> List[Dict[str, Any]]:
    """
    Cluster Jira issues based on semantic similarity.

    Returns:
    [
        {
            "issues": [...],
            "centroid": "ISSUE-KEY",
            "similarity_score": 0.83,
            "label": "login authentication error"
        }
    ]
    """

    if len(issues) == 0:
        return []

    keys = [i["key"] for i in issues]
    texts = [
        f"{i.get('summary', '')} {i.get('description', '')}"
        for i in issues
    ]

    # -----------------------------
    # 1. Semantic embeddings
    # -----------------------------

    model = _get_embedding_model(embedding_model)
    embeddings = model.encode(texts, normalize_embeddings=True)

    # -----------------------------
    # 2. Remove / merge duplicates
    # -----------------------------

    similarity_matrix = cosine_similarity(embeddings)

    unique_indices = []
    seen = set()

    for i in range(len(issues)):
        if i in seen:
            continue

        duplicates = np.where(similarity_matrix[i] > duplicate_threshold)[0]

        for d in duplicates:
            seen.add(d)

        unique_indices.append(i)

    embeddings = embeddings[unique_indices]
    texts = [texts[i] for i in unique_indices]
    keys = [keys[i] for i in unique_indices]

    # -----------------------------
    # 3. Find optimal cluster count
    # -----------------------------

    best_k = min_clusters
    best_score = -1

    max_k = min(max_clusters, len(embeddings) - 1)
    min_k = min(min_clusters, max_k)
    for k in range(min_k, max_k + 1):

        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        score = silhouette_score(embeddings, labels)

        if score > best_score:
            best_score = score
            best_k = k

    # -----------------------------
    # 4. Run clustering
    # -----------------------------
    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)
    centroids = kmeans.cluster_centers_

    # -----------------------------
    # 5. Cluster keyword labeling
    # -----------------------------

    tfidf = TfidfVectorizer(stop_words="english", max_features=5000)
    tfidf_matrix = tfidf.fit_transform(texts)
    vocab = np.array(tfidf.get_feature_names_out())

    results = []

    for cluster_id in range(best_k):

        indices = np.where(labels == cluster_id)[0]

        if len(indices) == 0:
            continue

        cluster_embeddings = embeddings[indices]

        centroid_vector = centroids[cluster_id].reshape(1, -1)

        similarities = cosine_similarity(cluster_embeddings, centroid_vector).flatten()

        best_local = np.argmax(similarities)
        best_global = indices[best_local]

        centroid_key = keys[best_global]

        cluster_issue_keys = [keys[i] for i in indices]

        avg_similarity = float(np.mean(similarities))

        # -----------------------------
        # Generate cluster label
        # -----------------------------

        cluster_tfidf = tfidf_matrix[indices].mean(axis=0)
        top_words_idx = np.argsort(cluster_tfidf).A1[::-1][:3]
        label = " ".join(vocab[top_words_idx])

        results.append({
            "similarity_score": round(avg_similarity, 4),
            "size": len(cluster_issue_keys),
            "centroid": centroid_key,
            "label": label,
            "issues": cluster_issue_keys
        })

    return results


def cluster_predictions(
        inference_json_path,
        db_json_path,
        clustering_progress_dict,
        selected_types_per_field=None,
        is_exclude_closed_items=True
):
    if selected_types_per_field is None:
        selected_issue_type_per_field = {}

    with open(db_json_path, 'r', encoding='utf-8') as file:
        jira_issues = json.load(file)
    with open(inference_json_path, 'r', encoding='utf-8') as file:
        predictions_json = json.load(file)
        predictions = predictions_json["data"]
        metadata = predictions_json["metadata"]

        # Exclude closed issues
        if is_exclude_closed_items:
            Logger.info(f"Excluding closed items ...")
            predictions = filter_out_closed_items(predictions, jira_issues)

        # Exclude unselected issue types
        Logger.info(f"Filtering predictions according to selected_types_per_field ...")
        for field, selected_types in selected_types_per_field.items():
            predictions = [p for p in predictions if not (p["field"] == field and p["issuetype"] not in selected_types)]
            pass

        # Exclude previously rejected predictions
        rejected_predictions = list(filter(lambda x: x.get("previously_rejected", None) is True, predictions))
        Logger.info(f"Excluding previously rejected predictions ...")
        predictions = list(filter(lambda x: x.get("previously_rejected", None) is not True, predictions))

        # TODO: 'accuracy' here is actually the 'confidence'
        confident_predictions = []
        unconfident_predictions = []
        for field in metadata.keys():
            min_confidence = metadata[field]["min_confidence"]
            Logger.debug(f"Excluding {field} predictions with confidence lower than {min_confidence}")
            confident_predictions.extend(list(filter(
                lambda x: x["field"] == field and x["accuracy"] >= min_confidence,
                predictions))
            )
            unconfident_predictions.extend(list(filter(
                lambda x: x["field"] == field and x["accuracy"] < min_confidence,
                predictions))
            )

        predictions_per_value, total_values, not_predictable = group_predictions_per_value(confident_predictions)

        clustering_progress_dict["total"] = total_values

    avg_confidence = 0
    if confident_predictions:
        avg_confidence = sum(list(map(lambda x: x["accuracy"], confident_predictions))) / len(confident_predictions)

    clustered_predictions = cluster_predictions_(predictions_per_value, jira_issues, clustering_progress_dict)
    return clustered_predictions, avg_confidence, not_predictable, rejected_predictions, unconfident_predictions

def filter_out_closed_items(predictions, jira_issues):
    closed_issue_keys = [issue["key"] for issue in jira_issues if issue["status"] in STATUSES_TO_EXCLUDE]
    predictions = [prediction for prediction in predictions if prediction["key"] not in closed_issue_keys]
    return predictions


def cluster_predictions_(predictions, jira_issues, clustering_progress_dict):
    cluster_list_per_predicted_value = {}
    cluster_count = 0
    cluster_count_per_target_field = {}
    clustered_count = 0
    orphan_count = 0
    orphan_count_per_target_field = {}
    one_item_cluster_count = 0

    for target_field, predictions_per_value in predictions.items():
        orphan_count_per_target_field[target_field] = 0
        cluster_count_per_target_field[target_field] = 0
        for predicted_value, issue_keys_to_cluster in predictions_per_value.items():
            clustering_progress_dict["in_progress"] = f"{target_field}: '{predicted_value}'"
            if predicted_value not in cluster_list_per_predicted_value:
                cluster_list_per_predicted_value[predicted_value] = []

            if len(issue_keys_to_cluster) == 1:
                orphan_count += 1
                orphan_count_per_target_field[target_field] += 1
                one_item_cluster_count += 1
                issue_keys_to_cluster_desc = list(filter(lambda x: x["key"] in issue_keys_to_cluster, jira_issues))
                issue_keys_to_cluster_desc = list(
                    map(lambda x: f'{x["key"]}_{x["summary"]}', issue_keys_to_cluster_desc))
                cluster_list_per_predicted_value[predicted_value].append({
                    "field_name": target_field,
                    "question": "ORPHANED",
                    "keywords": "",
                    "centroid": None,
                    "cluster_issues_count": 1,
                    "list_of_issues": [issue_keys_to_cluster_desc[0]],
                    "confidence": [[]],
                    "similarity_cohesion": 1,
                    "similarity_density": 1,
                    "cluster_centroid": issue_keys_to_cluster[0]
                })
                clustering_progress_dict["completed"].append(f"{target_field}: '{predicted_value}'")
                continue

            clustered_count += len(issue_keys_to_cluster)
            filtered_jira_issues = list(filter(lambda x: x["key"] in issue_keys_to_cluster, jira_issues))
            issues_to_cluster = list(map(lambda x: {
                "key": x["key"],
                "summary": x["summary"],
                "description": x["description"]
            }, filtered_jira_issues))

            min_clusters = int(len(issue_keys_to_cluster) / 10)
            min_clusters = 2 if min_clusters <= 1 else min_clusters
            max_clusters = int(len(issue_keys_to_cluster) / 10)
            max_clusters = 2 if max_clusters <= 1 else max_clusters

            try:
                clusters = cluster_jira_issues(
                    issues_to_cluster,
                    min_clusters=min_clusters,
                    max_clusters=max_clusters
                )
            except Exception as e:
                clusters = []
                print("[DEBUG] Clustering exception:", e)

            total_clustered_issues = 0
            for cluster in clusters:
                total_clustered_issues += len(cluster['issues'])

            cluster_count += len(clusters)
            cluster_count_per_target_field[target_field] += 1

            clustering_progress_dict["completed"].append(f"{target_field}: '{predicted_value}'")

            for cluster in clusters:
                # TODO: simplify data / remove unnecessary fields
                clustered_jira_issues = list(filter(lambda x: x["key"] in cluster["issues"], jira_issues))
                clustered_jira_issues_desc = list(map(lambda x: f'{x["key"]}_{x["summary"]}', clustered_jira_issues))
                question = f"Using '{cluster['centroid']}' as the representative of the cluster, recommendation is to add "
                question += f"'{predicted_value}' as '{target_field}'."
                # issue_desc_list = list(map(lambda x: f"{x}: {x}_description", cluster["issues"]))
                question = "ORPHANED" if len(cluster["issues"]) == 1 else question
                clustered_count -= 1 if len(cluster["issues"]) == 1 else 0
                cluster_count -= 1 if len(cluster["issues"]) == 1 else 0
                orphan_count += 1 if len(cluster["issues"]) == 1 else 0
                orphan_count_per_target_field[target_field] += 1 if len(cluster["issues"]) == 1 else 0
                cluster_list_per_predicted_value[predicted_value].append({
                    "field_name": target_field,
                    "question": question,
                    "keywords": cluster["label"],
                    "centroid": None,
                    "cluster_issues_count": len(cluster["issues"]),
                    "list_of_issues": [clustered_jira_issues_desc],
                    "confidence": [[]],
                    "similarity_score": cluster["similarity_score"],
                    "cluster_centroid": cluster["centroid"]
                })

    return cluster_list_per_predicted_value, clustered_count, cluster_count, {}


if __name__ == "__main__":
    db_file = "AURTEST2_20260303_220007.json"
    prediction_file = f"predictions/review/{db_file}"
    cluster_predictions(prediction_file, f"databases/{db_file}")




