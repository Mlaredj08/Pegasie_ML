#!/usr/bin/env python3
"""
================================================================================
Jira Component Inference Script with Configurable Project, Model, and Fields
================================================================================

WHAT THIS SCRIPT DOES:
- Loads a JSON dataset of Jira issues
- Splits issues into:
    • Training set: issues with exactly one component
    • Inference set: issues without any components (to predict)
- Concatenates specified issue fields into a single text string for feature extraction
- Trains a chosen model using TF-IDF features on the training set
- Predicts the missing component field for the inference set
- Saves a CSV with issue key, concatenated text, and predicted component

OUTPUT FILE:
    <project>_<MODEL_NAME>_<timestamp>_inferred_components.csv

REQUIREMENTS:
    pip install scikit-learn pandas

USAGE EXAMPLE:
    python component_inference.py \
        --input_file CIA_20250516082353.json \
        --project CIA-REGRESSION-INFER \
        --model RandomForest \
        --fields summary description
================================================================================
"""

import json
import argparse
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.svm import LinearSVC
from sklearn.naive_bayes import MultinomialNB
from sklearn.ensemble import RandomForestClassifier
from datetime import datetime
import sys

from config.constants import LOGISTIC_REGRESSION, LINEAR_SVC, MULTINOMIAL_NB, RANDOM_FOREST, SGD_CLASSIFIER


def build_issue_text(issue: dict, fields: list) -> str:
    """
    Concatenate the values of the specified fields from a Jira issue into a single text string.
    If a field is missing or None, it is skipped.
    """
    parts = []
    for field in fields:
        value = issue.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return ". ".join(parts).strip()


def select_pipeline(model_name: str) -> Pipeline:
    """
    Return a scikit-learn Pipeline object configured with TF-IDF + chosen classifier.
    Available model_name options:
    - LogisticRegression
    - LinearSVC
    - MultinomialNB
    - RandomForest
    - SGDClassifier
    """
    if model_name == LOGISTIC_REGRESSION:
        return Pipeline([
            ("tfidf", TfidfVectorizer()),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))
        ])
    elif model_name == LINEAR_SVC:
        return Pipeline([
            ("tfidf", TfidfVectorizer()),
            ("clf", LinearSVC(class_weight="balanced", random_state=42))
        ])
    elif model_name == MULTINOMIAL_NB:
        return Pipeline([
            ("tfidf", TfidfVectorizer()),
            ("clf", MultinomialNB())
        ])
    elif model_name == RANDOM_FOREST:
        return Pipeline([
            ("tfidf", TfidfVectorizer()),
            ("clf", RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42))
        ])
    elif model_name == SGD_CLASSIFIER:
        return Pipeline([
            ("tfidf", TfidfVectorizer()),
            ("clf", SGDClassifier(loss="hinge", class_weight="balanced", random_state=42))
        ])
    else:
        raise ValueError(
            f"Unknown model: {model_name}. "
            f"Choose one of: LogisticRegression, LinearSVC, MultinomialNB, RandomForest, SGDClassifier."
        )


def main(args):
    # 1. Load Jira issues from JSON
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            issues = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in file: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Split issues into training (1 component) and inference (0 components)
    train_issues = []
    infer_issues = []
    for issue in issues:
        components = issue.get("components") or []
        if len(components) == 1:
            train_issues.append(issue)
        elif len(components) == 0:
            infer_issues.append(issue)
        # Issues with >1 component are ignored

    if not train_issues:
        print("ERROR: No issues with exactly one component found. Cannot train model.", file=sys.stderr)
        sys.exit(1)

    if not infer_issues:
        print("INFO: No issues without components found. Nothing to infer.", file=sys.stderr)
        sys.exit(0)

    # 3. Build training data using specified fields
    X_train = []
    y_train = []
    for issue in train_issues:
        text = build_issue_text(issue, args.fields)
        if text:  # Only include issues where concatenated text is non-empty
            X_train.append(text)
            y_train.append(issue["components"][0])

    if not X_train:
        print("ERROR: After concatenating fields, no valid training text found.", file=sys.stderr)
        sys.exit(1)

    # 4. Build inference data using specified fields
    X_infer = []
    infer_keys = []
    for issue in infer_issues:
        text = build_issue_text(issue, args.fields)
        if text:
            X_infer.append(text)
            infer_keys.append(issue["key"])

    if not X_infer:
        print("INFO: After concatenating fields, no valid inference text found.", file=sys.stderr)
        sys.exit(0)

    # 5. Select and instantiate pipeline based on chosen model
    print(f"Selected project: {args.project}")
    print(f"Selected model: {args.model}")
    pipeline = select_pipeline(args.model)

    # 6. Train the model
    print("Training the model...")
    pipeline.fit(X_train, y_train)

    # 7. Predict missing components
    print(f"Predicting components for {len(X_infer)} issues without components...")
    y_pred = pipeline.predict(X_infer)

    # 8. Save inference results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_df = pd.DataFrame({
        "key": infer_keys,
        "text": X_infer,
        "predicted_component": y_pred
    })

    results_file = f"{args.project}_{args.model}_{timestamp}_inferred_components.csv"
    results_df.to_csv(results_file, index=False, encoding="utf-8")
    print(f"Inference results saved to: {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Jira Component Inference Script with selectable project, model, and fields."
    )
    parser.add_argument(
        "--input_file", "-i",
        required=True,
        help="Path to the JSON file containing Jira issues."
    )
    parser.add_argument(
        "--project", "-p",
        required=True,
        help="Project name prefix for the output filename (e.g., CIA-REGRESSION-INFER)."
    )
    parser.add_argument(
        "--model", "-m",
        required=True,
        choices=["LogisticRegression", "LinearSVC", "MultinomialNB", "RandomForest", "SGDClassifier"],
        help="Name of the model to use for training."
    )
    parser.add_argument(
        "--fields", "-f",
        nargs="+",
        required=True,
        help="List of Jira issue fields to concatenate (e.g., summary description)."
    )

    args = parser.parse_args()
    main(args)
