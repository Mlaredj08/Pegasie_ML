"""Cross-validated model evaluation for Jira field inference."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    jaccard_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GroupKFold, KFold, StratifiedGroupKFold, StratifiedKFold

from ml.metrics import select_confidence_threshold
from ml.model_selection import JiraLabelInference


def _scalar_target(issue: Dict[str, Any], target_field: str) -> str:
    value = issue.get(target_field)
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _derive_groups(issues: Sequence[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Group parent/epic-related issues to reduce leakage across CV folds."""
    groups: List[str] = []
    repeated = False
    seen = set()
    for issue in issues:
        parent = issue.get("parent") or issue.get("epic_link")
        if isinstance(parent, dict):
            parent = parent.get("key") or parent.get("id")
        group = str(parent) if parent else f"__self__:{issue.get('key')}"
        if group in seen and not group.startswith("__self__:"):
            repeated = True
        seen.add(group)
        groups.append(group)
    return np.asarray(groups) if repeated else None


def _fold_count_for_single(y: np.ndarray, requested: int) -> int:
    _, counts = np.unique(y, return_counts=True)
    if not len(counts):
        return 0
    return max(0, min(requested, int(counts.min())))


def _predict_fold(clf: JiraLabelInference, validation: List[Dict[str, Any]], multi_label: bool):
    X_val = clf.extract_features(validation, fit=False)
    if multi_label:
        _, prob_matrix = clf.get_pred_proba(X_val)
        selected = prob_matrix >= 0.5
        predictions = [clf.mlb.classes_[row].tolist() for row in selected]
        confidences = np.mean(np.maximum(prob_matrix, 1.0 - prob_matrix), axis=1)
        return predictions, confidences

    y_pred = clf.model.predict(X_val)
    predictions = clf.label_encoder.inverse_transform(y_pred).tolist()
    if hasattr(clf.model, "predict_proba"):
        proba = clf.model.predict_proba(X_val)
        confidences = np.max(proba, axis=1)
    else:
        confidences = np.ones(len(predictions), dtype=float)
    return predictions, confidences


def evaluate_model_cv(
    jira_issues: Sequence[Dict[str, Any]],
    model_type: str,
    target_field: str,
    structured_fields: Optional[List[str]] = None,
    n_splits: int = 5,
    random_state: int = 42,
    target_score: float = 0.90,
) -> Dict[str, Any]:
    """Evaluate one model with out-of-fold predictions.

    Single-label targets use stratified folds. If repeated parent/epic groups
    exist, StratifiedGroupKFold keeps related Jira issues in the same fold.
    Multi-label targets use grouped/plain K-fold because sklearn cannot directly
    stratify arbitrary multi-label matrices.
    """
    structured_fields = [field for field in (structured_fields or []) if field]
    if target_field in structured_fields:
        raise ValueError(f"Target field '{target_field}' cannot be used as an input feature")

    labeled = [issue for issue in jira_issues if issue.get(target_field)]
    if len(labeled) < 4:
        return {"status": "insufficient_data", "sample_count": len(labeled)}

    multi_label = isinstance(labeled[0].get(target_field), list)
    groups = _derive_groups(labeled)

    if multi_label:
        folds = min(3, n_splits, len(labeled))
        if folds < 2:
            return {"status": "insufficient_data", "sample_count": len(labeled)}
        if groups is not None and len(set(groups)) >= folds:
            splitter = GroupKFold(n_splits=folds)
            split_iter = splitter.split(labeled, groups=groups)
        else:
            splitter = KFold(n_splits=folds, shuffle=True, random_state=random_state)
            split_iter = splitter.split(labeled)
    else:
        y = np.asarray([_scalar_target(issue, target_field) for issue in labeled])
        folds = _fold_count_for_single(y, n_splits)
        if folds < 2:
            return {"status": "insufficient_class_support", "sample_count": len(labeled)}
        if groups is not None and len(set(groups)) >= folds:
            splitter = StratifiedGroupKFold(
                n_splits=folds, shuffle=True, random_state=random_state
            )
            split_iter = splitter.split(labeled, y, groups)
        else:
            splitter = StratifiedKFold(
                n_splits=folds, shuffle=True, random_state=random_state
            )
            split_iter = splitter.split(labeled, y)

    records: List[Dict[str, Any]] = []
    for train_idx, val_idx in split_iter:
        train_issues = [labeled[i] for i in train_idx]
        validation = [labeled[i] for i in val_idx]

        clf = JiraLabelInference(
            model_type=model_type,
            multi_label=multi_label,
            structured_fields=structured_fields,
            model_path=None,
            test_rand_seed=random_state,
        )
        X_train = clf.extract_features(train_issues, fit=True)
        if multi_label:
            from sklearn.preprocessing import MultiLabelBinarizer
            clf.mlb = MultiLabelBinarizer()
            y_train = clf.mlb.fit_transform(
                [issue[target_field] for issue in train_issues]
            )
        else:
            from sklearn.preprocessing import LabelEncoder
            clf.label_encoder = LabelEncoder()
            y_train = clf.label_encoder.fit_transform(
                [_scalar_target(issue, target_field) for issue in train_issues]
            )
        clf.model = clf._init_model()
        clf.model.fit(X_train, y_train)

        predictions, confidences = _predict_fold(clf, validation, multi_label)
        for issue, prediction, confidence in zip(
            validation, predictions, confidences
        ):
            records.append({
                "issue_key": issue.get("key"),
                "expected": issue.get(target_field),
                "prediction": prediction,
                "confidence": float(confidence),
                "is_split_test": True,
            })

    if multi_label:
        classes = sorted(set().union(
            *[set(r["expected"]) for r in records],
            *[set(r["prediction"]) for r in records],
        ))
        from sklearn.preprocessing import MultiLabelBinarizer
        mlb = MultiLabelBinarizer(classes=classes)
        mlb.fit([classes])
        y_true = mlb.transform([r["expected"] for r in records])
        y_pred = mlb.transform([r["prediction"] for r in records])
        base_metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "balanced_accuracy": None,
            "precision_macro": precision_score(
                y_true, y_pred, average="macro", zero_division=0
            ),
            "recall_macro": recall_score(
                y_true, y_pred, average="macro", zero_division=0
            ),
            "f1_macro": f1_score(
                y_true, y_pred, average="macro", zero_division=0
            ),
            "f1_micro": f1_score(
                y_true, y_pred, average="micro", zero_division=0
            ),
            "jaccard_samples": jaccard_score(
                y_true, y_pred, average="samples", zero_division=0
            ),
        }
    else:
        y_true = [str(r["expected"]) for r in records]
        y_pred = [str(r["prediction"]) for r in records]
        base_metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
            "precision_macro": precision_score(
                y_true, y_pred, average="macro", zero_division=0
            ),
            "recall_macro": recall_score(
                y_true, y_pred, average="macro", zero_division=0
            ),
            "f1_macro": f1_score(
                y_true, y_pred, average="macro", zero_division=0
            ),
            "f1_weighted": f1_score(
                y_true, y_pred, average="weighted", zero_division=0
            ),
        }

    threshold = select_confidence_threshold(
        records,
        target_score=target_score,
        metric_name="basic_accuracy",
    )
    return {
        "status": "ok",
        "sample_count": len(labeled),
        "folds": folds,
        "grouped": groups is not None,
        "metrics": base_metrics,
        "optimal_confidence": threshold["threshold"],
        "optimal_score": threshold["score"],
        "coverage": threshold["coverage"],
        "meets_target": threshold["meets_target"],
    }
