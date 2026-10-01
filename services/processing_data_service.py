import pandas as pd
import numpy as np
import json
from pandas.core.computation.ops import isnumeric
from pandas.core.dtypes.common import is_numeric_dtype
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from collections import defaultdict
import nlp.centroid_manager as centroid_manager
from config.constants import WORDS_TO_IGNORE_CONFIRMATION_QUESTIONS,FID_AVAILABLE_ISSUES, CFG_PROJECT,FID_QUESTION_COUNT, CQ_CONFIDENCE_DEFAULT, CFG_CONFIDENCE_FIELD, CSV_FIELD_NAMES,FQS_PREDICTED_VALUE,FQS_FIELD_NAME,FQS_SHARED_FEATURES,FQS_CLUSTER_ISSUES_COUNT,FQS_LIST_OF_ISSUES,FQS_LISTS_OF_CONFIDENCE,CQ_DEFAULT_WEIGHT_SCALE,CQ_DEFAULT_MAX_REP,CQ_DEFAULT_TOP_K,CQ_DEFAULT_MIN_SHARED_TOKENS,CQ_DEFAULT_MIN_ISSUE_COUNT_PER_CLUSTER
from collections import Counter
import utils_pkg as utils
import re
import os
unsafe_chars = '<>"\'/\\`=&{}()[];:,'

# Create a translation table: replace each unsafe char with '-'
translation_table = str.maketrans({c: '-' for c in unsafe_chars})

key = CSV_FIELD_NAMES[0]
summary = CSV_FIELD_NAMES[1]
field = CSV_FIELD_NAMES[2]
predicted = CSV_FIELD_NAMES[3]
confidence = CSV_FIELD_NAMES[4]
text_map = CSV_FIELD_NAMES[5]

# === CONFIGURATION ===
max_k_per_field = 5
min_tickets_to_cluster = 5

# === PREPROCESSING UTILITIES ===
def simple_tokenize(text):
    # text = text.lower()
    # text = re.sub(r"[^a-z0-9\s]", " ", text)
    # return text.split()

    # Example: Tokenize by spaces but keep hyphenated words together
    tokens = re.findall(r'\b\w+(?:-\w+)*\b', text.lower())
    return tokens

basic_stopwords = set(WORDS_TO_IGNORE_CONFIRMATION_QUESTIONS)

def preprocess(text):
    tokens = simple_tokenize(text)
    return ' '.join([t for t in tokens if t not in basic_stopwords])

def summarize_cluster(texts, top_n=5):
    all_words = ' '.join(texts).split()
    most_common = Counter(all_words).most_common(top_n)
    return [word for word, _ in most_common]
def sanitize_text(text: str) -> str:
    return str(text).translate(translation_table)
def filter_by_confidence(cluster_df):
    config = utils.model_config
    confidence_choice = 0.5
    if config != None:
        project = config.get(CFG_PROJECT, CFG_PROJECT)
        confidence_choice = config.get(CFG_CONFIDENCE_FIELD, project)
    filtered_list = []
    confidence_list = []
    bucket_df = cluster_df[(cluster_df['confidence'] >= float(confidence_choice))]
    # summaries_cleaned = [html.escape(str(s), quote=True) for s in bucket_df['summary']]
    summaries_cleaned = [sanitize_text(s) for s in bucket_df['summary']]

    combined = [f"{k}: {s}" for k, s in zip(bucket_df['key'], summaries_cleaned)]

    if len(bucket_df[key]) > 0:
        filtered_list.append(combined)
        confidence_list.append(bucket_df[confidence].tolist())
    return filtered_list, confidence_list

# === RESTRUCTURING FUNCTION ===
def restructure_for_questions(summary_json, issue_count_orphan, input_file, fields):
    total_questions = 0
    total_issues = 0
    total_orphans = 0
    question_summary = {}
    field_information = {}
    for field in fields:
        field_information[field] = {
            FID_QUESTION_COUNT: 0,
            FID_AVAILABLE_ISSUES: 0
        }

    for predicted_value, clusters in summary_json.items():
        question_summary[predicted_value] = []
        all_jira_issues = centroid_manager.json_file_to_dict(input_file)
        for cluster in clusters:
            shared_features = ', '.join(cluster[FQS_SHARED_FEATURES])
            total_count = cluster[FQS_CLUSTER_ISSUES_COUNT]
            field_name = cluster[FQS_FIELD_NAME]
            keywords = cluster[FQS_SHARED_FEATURES]
            act_total_count = sum(len(sublist) for sublist in list(cluster[FQS_LIST_OF_ISSUES]))
            cluster_keys = list(map(lambda x: x.split(':')[0],cluster[FQS_LIST_OF_ISSUES][0]))
            centroid = centroid_manager.get_cluster_centroid(cluster_keys, all_jira_issues)
            if centroid != "":
                question = (
                    f"Target Field: {field_name} Value: {predicted_value}"
                    f" —: {centroid} Being the issue that best represents this cluster, is it fair to say that its {field_name} are more likely to be {predicted_value} ?"
                )
            else:
                question = (
                    f"Target Field: {field_name} Value: {predicted_value}"
                    f" Keywords representing the group: {shared_features}"
                )
            if total_count > issue_count_orphan:
                question_summary[predicted_value].append({
                    "question": question,
                    "keywords": keywords,
                    "centroid": centroid,
                    FQS_FIELD_NAME: field_name,
                    FQS_CLUSTER_ISSUES_COUNT: act_total_count,
                    FQS_LIST_OF_ISSUES: cluster[FQS_LIST_OF_ISSUES],
                    "confidence": cluster[FQS_LISTS_OF_CONFIDENCE],
                    "similarity_cohesion": cluster.get("cohesion_cosine"),
                    "similarity_density": cluster.get("density_pairwise"),
                    "cluster_centroid": cluster.get("cluster_centroid")
                })
                total_questions = total_questions + 1
                total_issues = total_issues + act_total_count
                field_information[field_name][FID_QUESTION_COUNT] += 1
                field_information[field_name][FID_AVAILABLE_ISSUES] += act_total_count

            elif total_count <= issue_count_orphan:
                total_orphans = total_orphans + act_total_count
                act_total_count = sum(len(sublist) for sublist in list(cluster[FQS_LIST_OF_ISSUES]))
                question_summary[predicted_value].append({
                    "question": "ORPHANED",
                    "keywords": keywords,
                    "centroid": None,
                    FQS_FIELD_NAME: field_name,
                    FQS_CLUSTER_ISSUES_COUNT: act_total_count,
                    FQS_LIST_OF_ISSUES: cluster[FQS_LIST_OF_ISSUES],
                    "confidence": cluster[FQS_LISTS_OF_CONFIDENCE],
                    "similarity_cohesion": cluster.get("cohesion_cosine"),
                    "similarity_density": cluster.get("density_pairwise"),
                    "cluster_centroid": cluster.get("cluster_centroid")
                })

    return question_summary, total_questions, total_issues, field_information


def group_predictions_from_inferred(
    json_path=None,
    input_file=None,
    issue_summaries=None,
    weight_scale=CQ_DEFAULT_WEIGHT_SCALE,
    max_rep=CQ_DEFAULT_MAX_REP,
    top_k=CQ_DEFAULT_TOP_K, #number of centroid keywords
    min_shared_tokens=CQ_DEFAULT_MIN_SHARED_TOKENS, # the minimum keywords to be matched against the top-k, for each issue, to stay in the clusters
    min_issue_count_per_cluster=CQ_DEFAULT_MIN_ISSUE_COUNT_PER_CLUSTER,
    apply_purity_filter: bool = False
):
    field_name = ""
    # ---- JSON parsing ----
    predictions = []
    fields = []
    config = utils.model_config
    configuration_confidence = CQ_CONFIDENCE_DEFAULT
    if config != None:
        project = config.get(CFG_PROJECT, CFG_PROJECT)
        configuration_confidence = config.get(CFG_CONFIDENCE_FIELD, project)
    top_tokens_per_issue = {}
    if json_path:
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        rows = raw.get("data", raw)
        rows = list(map(lambda x: x.values(), rows))
        built_predictions = []
        built_tokens = {}
        built_summaries = {}
        fields_seen = set()

        for row in rows:
            row = list(row)
            if not isinstance(row, (list, tuple)) or len(row) < 7:
                continue
            key = str(row[0])
            summary = row[1] or ""
            field_name = row[2]
            predicted_val = row[3]
            conf = row[4]
            try:
                conf = float(conf) if conf is not None else None
            except (TypeError, ValueError):
                conf = None
            tokens = row[6] or []

            built_summaries[key] = summary
            built_tokens[key] = [
                (str(t[0]), float(t[1])) for t in tokens
                if isinstance(t, (list, tuple)) and len(t) == 2
            ]
            if conf is not None and conf >= configuration_confidence:
                built_predictions.append((key, predicted_val, conf, field_name))
            if field_name:
                fields_seen.add(field_name)

        predictions = built_predictions
        top_tokens_per_issue = built_tokens
        issue_summaries = built_summaries
        if len(fields_seen) == 1:
            field_name = fields_seen.pop()

    groups = {}

    # bucket by predicted value
    label_buckets = {}
    for key, label, conf, field_name in predictions:
        if isinstance(label, list):
            label = ', '.join(label)
        label_buckets.setdefault((label, field_name), []).append((key, float(conf)))

    # totals
    # total_issues = len(predictions)
    total_clusters = 0

    def positive_token_set(k):
        return {tok for tok, c in (top_tokens_per_issue or {}).get(k, []) if c > 0}

    # per-label clustering
    for (label, field_name), items in label_buckets.items():
        if field_name not in fields:
            fields.append(field_name)
        # Build weighted docs (positive-only); separate orphans
        docs, kept_items, orphans = [], [], []
        for key, conf in items:
            pos = [(t, c) for t, c in (top_tokens_per_issue or {}).get(key, []) if c > 0]
            if not pos:
                orphans.append((key, conf))
                continue
            scaled = []
            for tok, c in pos:
                rep = max(1, min(int(round(c * weight_scale)), max_rep))
                scaled.extend([tok] * rep)
            docs.append(" ".join(scaled))
            kept_items.append((key, conf))

        clusters = {}
        vec = None
        km = None
        centroid_keywords_ordered = {}   # cl_id -> [kw1, kw2, ...]
        centroid_keywords_set = {}       # cl_id -> set(...)

        if len(kept_items) == 0:
            # only orphans → each becomes its own cluster
            for i, (k, c) in enumerate(orphans):
                clusters[i] = [(k, c)]
        elif len(kept_items) == 1:
            clusters[0] = kept_items[:]
            next_id = 1
            for (k, c) in orphans:
                clusters[next_id] = [(k, c)]
                next_id += 1
        else:
            # Vectorize weighted docs and run KMeans on KEPT items only
            vec = TfidfVectorizer()
            X = vec.fit_transform(docs)
            idx_map = {issue_key: i for i, (issue_key, _conf) in enumerate(kept_items)}

            # ---- NEW: choose k from min_issue_count_per_cluster ----
            k_target = max(1, len(kept_items) // max(1, int(min_issue_count_per_cluster)))
            k_target = min(k_target, len(kept_items))  # never exceed kept_items

            # If very small bucket, k_target can be 1; that's expected
            km = KMeans(n_clusters=k_target, random_state=0, n_init=10).fit(X)
            labels_arr = km.labels_

            # Collect initial clusters
            tmp_clusters = {}
            for (issue_key, conf), cl in zip(kept_items, labels_arr):
                tmp_clusters.setdefault(cl, []).append((issue_key, conf))

            # Centroid top-k keywords per KMeans cluster
            vocab = vec.get_feature_names_out()
            for cl in range(km.n_clusters): # type: ignore
                center = km.cluster_centers_[cl]
                top_idx = np.argsort(center)[::-1][:top_k]
                ordered = [vocab[i] for i in top_idx]
                centroid_keywords_ordered[cl] = ordered
                centroid_keywords_set[cl] = set(ordered)

            # Purity pass: keep members that overlap with centroid keywords
            # ---- Purity switch: keep or skip the purity filter ----
            if apply_purity_filter:
                # Purity pass: keep members that overlap with centroid keywords
                clusters = {}
                ejected = []
                for cl, members in tmp_clusters.items():
                    keep_list = []
                    for (issue_key, conf) in members:
                        overlap = positive_token_set(issue_key) & centroid_keywords_set[cl]
                        if len(overlap) >= min_shared_tokens:
                            keep_list.append((issue_key, conf))
                        else:
                            ejected.append((issue_key, conf))
                    if keep_list:
                        clusters[cl] = keep_list

                # Add each ejected and each orphan as singleton clusters
                next_id = (max(clusters.keys()) + 1) if clusters else 0
                for (k, c) in ejected:
                    clusters[next_id] = [(k, c)]
                    next_id += 1
                for (k, c) in orphans:
                    clusters[next_id] = [(k, c)]
                    next_id += 1
            else:
                # Skip purity: accept KMeans assignments as-is, but still add true orphans
                clusters = tmp_clusters
                next_id = (max(clusters.keys()) + 1) if clusters else 0
                for (k, c) in orphans:
                    clusters[next_id] = [(k, c)]
                    next_id += 1

        # 3) Build output clusters
        out_clusters = []
        for cl_id, members in clusters.items():
            cohesion_cosine = None
            density_pairwise = None
            cluster_centroid_key = None

            confs = [c for _, c in members]
            # Keywords
            # treat cl_id as an int index if we did KMeans and have that centroid
            has_kmeans_centroid = (vec is not None and km is not None)
            if has_kmeans_centroid:
                try:
                    cl_int = int(cl_id)
                except Exception:
                    cl_int = None
            else:
                cl_int = None

            if cl_int is not None and 0 <= cl_int < km.n_clusters:  # use centroid path
                member_idx = [idx_map[k] for k, _ in members if k in idx_map]
                if len(member_idx) >= 1:
                    X_sub = X[member_idx]  # rows are L2-normalized by TF-IDF
                    center = km.cluster_centers_[cl_int]
                    center_norm = center / (np.linalg.norm(center) + 1e-12)

                    # Mean cosine to centroid (cohesion)
                    prod = X_sub @ center_norm
                    if hasattr(prod, "toarray"):
                        prod = prod.toarray().ravel()
                    cohesion_vec = np.asarray(prod).ravel()
                    cohesion_cosine = float(np.mean(cohesion_vec))
                    if len(member_idx) >= 1:
                        best_local = int(np.argmax(cohesion_vec))
                        cluster_centroid_key = members[best_local][0]

                    # Mean pairwise cosine among members (density)
                    if X_sub.shape[0] >= 2:
                        S = (X_sub @ X_sub.T)
                        if hasattr(S, "toarray"):
                            S = S.toarray()
                        iu = np.triu_indices_from(S, k=1)
                        if iu[0].size > 0:
                            density_pairwise = float(np.mean(S[iu]))

                keywords = centroid_keywords_ordered.get(cl_int, [])[:top_k]
            else:
                member_idx = [idx_map[k] for k, _ in members if has_kmeans_centroid and k in idx_map]
                if has_kmeans_centroid and len(member_idx) >= 2:
                    X_sub = X[member_idx]
                    S = (X_sub @ X_sub.T).A
                    iu = np.triu_indices_from(S, k=1)
                    if iu[0].size > 0:
                        density_pairwise = float(np.mean(S[iu]))
                # fallback keywords by aggregate tokens
                agg = Counter()
                for k, _ in members:
                    for tok, c in (top_tokens_per_issue or {}).get(k, []):
                        if c > 0:
                            agg[tok] += c
                keywords = [t for t, _ in agg.most_common(top_k)]

                if cluster_centroid_key is None:
                    kw_set = set(keywords or [])
                    best_score = -1.0
                    best_key = None
                    for k, _ in members:
                        score = 0.0
                        for tok, w in (top_tokens_per_issue or {}).get(k, []):
                            if tok in kw_set and w > 0:
                                score += float(w)
                        if score > best_score:
                            best_score = score
                            best_key = k
                    cluster_centroid_key = best_key

            # Issue lines
            issue_lines = []
            for k, _c in members:
                s = (issue_summaries or {}).get(k, "") or ""
                issue_lines.append(f"{k}: {s}" if s else k)

            cluster_size = len(members)

            out_clusters.append({
                FQS_LISTS_OF_CONFIDENCE: [confs],
                FQS_FIELD_NAME: field_name,
                FQS_SHARED_FEATURES: keywords,
                FQS_CLUSTER_ISSUES_COUNT: cluster_size,
                FQS_LIST_OF_ISSUES: [issue_lines],
                FQS_PREDICTED_VALUE: label,
                "cohesion_cosine": cohesion_cosine,
                "density_pairwise": density_pairwise,
                "cluster_centroid": cluster_centroid_key
            })

        groups[label] = out_clusters
        total_clusters += len(out_clusters)
        # final filter min_issue_count_per_cluster. All small filters after threshold get filtered out
    result, question_count, total_issues, field_information = restructure_for_questions(groups, min_issue_count_per_cluster, input_file, fields)


    meta = result.setdefault("__meta", {})
    meta.update({
        "accepted_predictions": len(predictions),  # above threshold
        "emitted_predictions": total_issues,  # shown in questions (non-orphans)
        "confidence_threshold": configuration_confidence,
        "question_count": question_count  # handy to have here too
    })

    return result, total_issues, question_count, field_information  # type: ignore

