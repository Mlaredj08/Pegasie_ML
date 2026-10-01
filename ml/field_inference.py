import re

import nltk
import numpy as np
import pandas as pd
from typing import List, Dict, Union, Any

from nltk import WordNetLemmatizer
from nltk.corpus import stopwords
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC
from sklearn.linear_model import SGDClassifier
from config.constants import (
    LOGISTIC_REGRESSION,
    RANDOM_FOREST,
    LINEAR_SVC,
    MULTINOMIAL_NB,
    SGD_CLASSIFIER,
    DEFAULT_MODEL,
    CFG_MODEL,
    CFG_SOURCE_FIELDS,
    DEFAULT_SOURCE_FIELDS, CFG_MODEL_PARAMS, CFG_PROJECT
)
from services.test_service import select_random_issues_from_train_issues_to_test_inference, reset_ramdom_test
from services.iteration_service import retrieve_keyword_feedback
from collections import defaultdict

# Feedback Loop ##########################################################################################
nltk.download('wordnet')
nltk.download('omw-1.4')
nltk.download('stopwords')
lemmatizer = WordNetLemmatizer()

def clean_and_lemmatize(text):
    stop_words = set(stopwords.words('english'))
    words = re.findall(r'\b\w+(?:-\w+)*\b', text.lower())
    # lemmas = [lemmatizer.lemmatize(word) for word in list(filter(lambda x: not x.isdigit(), words))]
    lemmas = [lemmatizer.lemmatize(word) for word in words if word not in stop_words]
    return " ".join(lemmas)

def boost_feedback_keywords(text, target_filed, field_value="", boost_factor=10):
    text_lower = text.lower()
    keyword_dict, keyword_list = retrieve_keyword_feedback(field_name=target_filed)
    for dico in keyword_list:
        if str(dico["field_name"]).lower() == str(target_filed).lower() and str(dico["predicted_value"]).lower() == str(field_value).lower():
            for kw in dico["removed_keywords"]:
                text_lower = text_lower.replace(kw, "")
            for kw in dico["added_keywords"]:
                if kw in text_lower:
                    text_lower += (" " + kw) * boost_factor
    return text_lower
###########################################################################################################

def build_issue_text(issue: dict, fields: List[str]) -> str:
    parts: List[str] = []

    for field in fields:
        value: Any = issue.get(field)

         # Helper – emit just the token (no field name)
        def _add(tok: Union[str, int, float, bool]):
            if tok is None or tok == "":
                return
            parts.append(str(tok).strip())

        # -------- handle value types --------
        if isinstance(value, str):
            _add(value)

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (str, int, float, bool)):
                    _add(item)
                elif isinstance(item, dict):
                    # Flatten dict to its values
                    for v in item.values():
                        _add(v)
                elif item is not None:
                    _add(item)

        elif isinstance(value, dict):
            for v in value.values():
                _add(v)

        elif isinstance(value, (int, float, bool)):
            _add(value)

    issue_text = " ".join(parts)

    lemmatized_text = clean_and_lemmatize(issue_text)
    return lemmatized_text

def build_training_data(train_issues: list, target: str, source_fields: list):
    """
    Build X_train (texts) and y_train (target values) from train_issues.
    Handles various data types for the target field.
    """
    X_train = []
    y_train = []

    for issue in train_issues:
        text = build_issue_text(issue, source_fields)
        # Boost feedback keywords if found in text
        text = boost_feedback_keywords(text, target_filed=target, field_value=issue[target])
        if not text:
            continue

        X_train.append(text)
        raw = issue.get(target)

        # If it's a list of exactly one element
        if isinstance(raw, list):
            first = raw[0]
            if isinstance(first, str):
                y_train.append(first.strip())
            elif isinstance(first, dict):
                candidate = first.get("name", first.get("value", ""))
                y_train.append(str(candidate).strip())
            else:  # number or boolean
                y_train.append(str(first))

        # If single dict
        elif isinstance(raw, dict):
            val = raw.get("name", raw.get("value", None))
            y_train.append(str(val).strip() if val is not None else "")

        # If plain string
        elif isinstance(raw, str):
            y_train.append(raw.strip())

        # If number
        elif isinstance(raw, (int, float)):
            y_train.append(str(raw))

        # If boolean
        elif isinstance(raw, bool):
            y_train.append("true" if raw else "false")

        else:
            # (should not happen) mark as missing
            y_train.append("")

    return X_train, y_train


def split_issues(issues: List[dict], target_field: str):
    train = [i for i in issues if i.get(target_field)]
    infer = [i for i in issues if not i.get(target_field)]
    return train, infer

def compute_confidence(model, X: List[str]):
    if hasattr(model, "predict_proba"):
        probas = model.predict_proba(X)
        return [max(p) for p in probas]
    elif hasattr(model, "decision_function"):
        scores = model.decision_function(X)
        if scores.ndim == 1:
            return [abs(s) for s in scores]
        else:
            return [max(s) for s in scores]
    else:
        return [None for _ in X]

def select_pipeline(model_name: str, model_params: dict = None) -> Pipeline: # type: ignore
    model_params = model_params or {}
    key = model_name.lower()

    if key == LOGISTIC_REGRESSION:
        clf = LogisticRegression(**model_params)
    elif key == RANDOM_FOREST:
        clf = RandomForestClassifier(**model_params)
    elif key == LINEAR_SVC:
        clf = LinearSVC(**model_params)
    elif key == MULTINOMIAL_NB:
        clf = MultinomialNB(**model_params)
    elif key == SGD_CLASSIFIER:
        clf = SGDClassifier(**model_params)
    else:
        clf = RandomForestClassifier(**model_params)

    return Pipeline([
        ("tfidf", TfidfVectorizer()),
        ("clf", clf)
    ])


def infer_fields(
        df: pd.DataFrame,
        field_models: dict,
        feedback_keywords=None,
        is_exclude_closed: bool = False,
        top_n_tokens: int = 8
):
    """
    Trains the configured model for each target field, predicts missing values,
    and returns (df, report) where report contains global/per-issue token explanations
    for supported classifiers:
      - Linear (coef_): logisticregression, linearsvc, sgd
      - Trees  (feature_importances_): randomforest (global + per-issue approx)
      - Naive Bayes (feature_log_prob_): multinomialnb
    """
    feedback_keywords = {} if feedback_keywords is None else feedback_keywords
    report = {}

    # ------------- helpers: pipeline parts & class index -------------
    def _get_parts(pipeline):
        """Find vectorizer & classifier irrespective of step names."""
        vec, clf = None, None
        for _, step in pipeline.named_steps.items():
            # identify vectorizer by capability
            if hasattr(step, "get_feature_names_out") or hasattr(step, "vocabulary_"):
                vec = step
            # identify classifier by prediction + one of the supported attribs
            if hasattr(step, "predict") and (
                hasattr(step, "coef_") or
                hasattr(step, "feature_importances_") or
                hasattr(step, "feature_log_prob_")
            ):
                clf = step

        # fallback to common names
        vec = vec or pipeline.named_steps.get("vectorizer")
        clf = clf or pipeline.named_steps.get("classifier") or pipeline.named_steps.get("clf")
        return vec, clf

    def _label_to_index(clf, label):
        if hasattr(clf, "classes_"):
            classes = list(clf.classes_)
            return classes.index(label) if label in classes else 0
        return 0

    # ------------- helpers: global explainers -------------
    def _global_top_tokens_linear(vectorizer, clf, top_k=20):
        feat = vectorizer.get_feature_names_out()
        coefs = getattr(clf, "coef_", None)
        if coefs is None:
            return None
        out = {}
        for c_idx, row in enumerate(coefs):
            row = np.asarray(row, dtype=float).ravel()
            pairs = sorted(zip(row, feat), key=lambda x: x[0], reverse=True)
            label = clf.classes_[c_idx] if hasattr(clf, "classes_") else str(c_idx)
            out[str(label)] = {
                "top_positive": pairs[:top_k],
                "top_negative": sorted(pairs, key=lambda x: x[0])[:top_k]
            }
        return out

    def _global_top_tokens_tree(vectorizer, clf, top_k=20):
        feat = vectorizer.get_feature_names_out()
        importances = getattr(clf, "feature_importances_", None)
        if importances is None:
            return None
        importances = np.asarray(importances, dtype=float).ravel()
        pairs = sorted(zip(importances, feat), key=lambda x: x[0], reverse=True)
        return {"feature_importances": pairs[:top_k]}

    def _global_top_tokens_nb(vectorizer, clf, top_k=20):
        feat = vectorizer.get_feature_names_out()
        log_prob = getattr(clf, "feature_log_prob_", None)
        if log_prob is None:
            return None
        log_prob = np.asarray(log_prob, dtype=float)
        mean_log_prob = log_prob.mean(axis=0)
        out = {}
        for c_idx in range(log_prob.shape[0]):
            weights = log_prob[c_idx] - mean_log_prob
            pairs = sorted(zip(weights, feat), key=lambda x: x[0], reverse=True)
            label = clf.classes_[c_idx] if hasattr(clf, "classes_") else str(c_idx)
            out[str(label)] = {
                "top_positive": pairs[:top_k],
                "top_negative": sorted(pairs, key=lambda x: x[0])[:top_k]
            }
        return out

    # ------------- helpers: per-issue explainers -------------
    def _explain_issue_linear(vectorizer, clf, text, predicted_label, top_k=8):
        # Vectorize once
        X = vectorizer.transform([text])
        coefs = getattr(clf, "coef_", None)
        classes = getattr(clf, "classes_", None)

        if coefs is None:
            return None

        n_rows, n_features = coefs.shape
        feat = vectorizer.get_feature_names_out()

        # Build sparse iteration over the single row
        row = X.tocoo()
        contributions = defaultdict(float)

        if classes is not None and len(classes) == 2 and n_rows == 1:
            # Binary case in scikit-learn linear models: coef_ has shape (1, n_features)
            # The single weight vector corresponds to classes_[1].
            # Use a sign flip when explaining the classes_[0] side.
            weights = np.asarray(coefs[0], dtype=float).ravel()
            sign = 1.0 if predicted_label == classes[1] else -1.0
            for _, j, v in zip(row.row, row.col, row.data):
                contributions[feat[j]] += float(v) * float(weights[j]) * sign
        else:
            # Multiclass (or unusual) case: one row per class
            try:
                # Robust class index resolution without relying on an external helper
                class_idx = int(np.where(classes == predicted_label)[0][0]) if classes is not None else 0
            except Exception:
                # Fallback if label isn't in classes_ for some reason
                class_idx = 0

            weights = np.asarray(coefs[class_idx], dtype=float).ravel()
            for _, j, v in zip(row.row, row.col, row.data):
                contributions[feat[j]] += float(v) * float(weights[j])

        if not contributions:
            return None

        # Normalize top_k and return top-|contribution| tokens (with signed values)
        if not top_k or top_k <= 0:
            top_k = 8

        toks = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:top_k]
        return [(tok, float(val)) for tok, val in toks]

    def _explain_issue_nb(vectorizer, clf, text, predicted_label, top_k=8):
        X = vectorizer.transform([text])
        class_idx = _label_to_index(clf, predicted_label)
        log_prob = getattr(clf, "feature_log_prob_", None)
        if log_prob is None:
            return None
        log_prob = np.asarray(log_prob, dtype=float)
        mean_log_prob = log_prob.mean(axis=0)
        weights = log_prob[class_idx] - mean_log_prob

        row = X.tocoo()
        feat = vectorizer.get_feature_names_out()
        contributions = {}
        for _, j, v in zip(row.row, row.col, row.data):
            token = feat[j]
            contrib = float(v) * float(weights[j])
            contributions[token] = contributions.get(token, 0.0) + contrib

        if not contributions:
            return None
        return sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:top_k]

    def _explain_issue_tree_approx(vectorizer, clf, text, top_k=8):
        """
        Heuristic per-issue attribution for tree models:
        contribution(token) ≈ X_token(issue) * feature_importance(token).
        (Not a true SHAP/path contribution, but lightweight and useful.)
        """
        if not hasattr(clf, "feature_importances_"):
            return None
        X = vectorizer.transform([text])
        feat = vectorizer.get_feature_names_out()
        importances = np.asarray(clf.feature_importances_, dtype=float).ravel()

        row = X.tocoo()
        contributions = {}
        for _, j, v in zip(row.row, row.col, row.data):
            token = feat[j]
            contrib = float(v) * float(importances[j])
            contributions[token] = contributions.get(token, 0.0) + contrib

        if not contributions:
            return None
        return sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:top_k]

    # Rest random tests.
    reset_ramdom_test()

    # ===================== main loop per field =====================
    for field_name, config in field_models.items():
        print(f"\n>>> Inferring field: {field_name} <<<")

        target_field  = field_name
        model_name    = config.get(CFG_MODEL, LOGISTIC_REGRESSION)
        source_fields = config.get(CFG_SOURCE_FIELDS, ["summary", "description"])
        model_params  = config.get(CFG_MODEL_PARAMS, {})
        project       = config.get(CFG_PROJECT)

        print("\n--- Field Inference Configuration ---")
        print(f"Target Field    : {target_field}")
        print(f"Model Name      : {model_name}")
        print(f"Source Fields   : {source_fields}")
        print(f"Model Parameters: {model_params}")
        print("--------------------------------------\n")

        issues = df.fillna("").to_dict(orient="records")

        # Precompute concatenated text for each issue
        text_map = {issue["key"]: build_issue_text(issue, source_fields) for issue in issues}
        text_column = "text"
        df[text_column] = df["key"].map(lambda k: text_map.get(k, ""))

        # Split into train/infer sets
        train_issues, infer_issues = split_issues(issues, target_field)
        if not train_issues or not infer_issues:
            print(f"[{field_name}] Skipped due to missing train or inference data.")
            continue

        # Add Random Tests
        random_issues = select_random_issues_from_train_issues_to_test_inference(train_issues, target_field)
        infer_issues.extend(random_issues)

        # Optionally filter out Closed issues for inference
        if is_exclude_closed:
            infer_issues = [x for x in infer_issues if x.get("status") != "Closed"]

        # Build data
        X_train, y_train = build_training_data(train_issues, target_field, source_fields)

        X_infer, infer_keys = [], []
        for issue in infer_issues:
            k = issue["key"]
            t = text_map.get(k, "")
            if t:
                X_infer.append(t)
                infer_keys.append(k)

        # Train
        pipeline = select_pipeline(model_name, model_params)
        pipeline.fit(X_train, y_train)

        # Predict
        y_pred = pipeline.predict(X_infer)
        confidences = compute_confidence(pipeline, X_infer)

        # Update df
        predicted_column  = f"predicted_{target_field}"
        confidence_column = f"{predicted_column}_confidence"
        mapping = dict(zip(infer_keys, zip(y_pred, confidences)))
        df[predicted_column]  = df["key"].map(lambda k: mapping[k][0] if k in mapping else None)
        df[confidence_column] = df["key"].map(lambda k: mapping[k][1] if k in mapping else None)

        # Explanations
        vectorizer, clf = _get_parts(pipeline)
        global_explanations = None
        per_issue_explanations = {}
        contrib_values = []

        if vectorizer is not None and clf is not None and hasattr(vectorizer, "get_feature_names_out"):
            # GLOBAL
            if hasattr(clf, "coef_"):  # linear family: logistic, linear svc, sgd
                global_explanations = _global_top_tokens_linear(vectorizer, clf, top_k=20)
            elif hasattr(clf, "feature_importances_"):  # trees: random forest
                global_explanations = _global_top_tokens_tree(vectorizer, clf, top_k=20)
            elif hasattr(clf, "feature_log_prob_"):  # NB
                global_explanations = _global_top_tokens_nb(vectorizer, clf, top_k=20)

            # PER-ISSUE
            if hasattr(clf, "coef_"):
                for k, text, label in zip(infer_keys, X_infer, y_pred):
                    toks = _explain_issue_linear(vectorizer, clf, text, label, top_k=top_n_tokens)
                    if toks:
                        per_issue_explanations[k] = {"predicted_label": label, "top_tokens": toks}
                        contrib_values.extend([c for _, c in toks])

            elif hasattr(clf, "feature_log_prob_"):
                for k, text, label in zip(infer_keys, X_infer, y_pred):
                    toks = _explain_issue_nb(vectorizer, clf, text, label, top_k=top_n_tokens)
                    if toks:
                        per_issue_explanations[k] = {"predicted_label": label, "top_tokens": toks}
                        contrib_values.extend([c for _, c in toks])

            elif hasattr(clf, "feature_importances_"):
                # Approximate per-issue tokens for trees
                for k, text, label in zip(infer_keys, X_infer, y_pred):
                    toks = _explain_issue_tree_approx(vectorizer, clf, text, top_k=top_n_tokens)
                    if toks:
                        per_issue_explanations[k] = {"predicted_label": label, "top_tokens": toks}
                        contrib_values.extend([c for _, c in toks])

        contrib_min = float(min(contrib_values)) if contrib_values else None
        contrib_max = float(max(contrib_values)) if contrib_values else None

        report[field_name] = {
            "model": model_name,
            "params": model_params,
            "inferred": int(len(y_pred)),
            "source_fields": source_fields,
            "text_map": text_map,
            "explanations": {
                "global": global_explanations,
                "per_issue": per_issue_explanations,
                "contribution_range": {"min": contrib_min, "max": contrib_max}
            }
        }

    return df, report


