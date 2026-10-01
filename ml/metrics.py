"""ML evaluation helpers used by inference and model selection.

The original implementation calculated confusion-matrix counters manually and
used substring matching for labels. This module centralises exact, sklearn-
based metrics so model selection is reproducible and mathematically correct.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence, Set

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    jaccard_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import MultiLabelBinarizer


def _normalise_scalar(value: Any) -> str:
    """Normalise one categorical value without fuzzy/substring matching."""
    if value is None:
        return ""
    return str(value).strip()


def as_label_set(value: Any) -> Set[str]:
    """Convert a scalar or multi-label value into a normalised set."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return {_normalise_scalar(item) for item in value if _normalise_scalar(item)}
    normalised = _normalise_scalar(value)
    return {normalised} if normalised else set()


def list_jaccard_percent(expected: Any, predicted: Any) -> int:
    """Return Jaccard similarity as an integer percentage (0..100)."""
    expected_set = as_label_set(expected)
    predicted_set = as_label_set(predicted)
    union = expected_set | predicted_set
    if not union:
        return 100
    return int(round(100 * len(expected_set & predicted_set) / len(union)))


def _safe_confidence(record: Dict[str, Any]) -> float:
    try:
        value = float(record.get("confidence", 0.0))
        return value if np.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _is_multilabel(records: Sequence[Dict[str, Any]]) -> bool:
    return any(
        isinstance(record.get("expected"), (list, tuple, set, np.ndarray))
        or isinstance(record.get("prediction"), (list, tuple, set, np.ndarray))
        for record in records
    )


def evaluate_prediction_records(records: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """Evaluate prediction records using exact sklearn metrics.

    Only records with a non-None expected value are scored. Legacy keys
    (basic_accuracy, accuracy, f1_score) are retained so existing UI code can
    consume the improved metrics without a schema migration.
    """
    test_records = [r for r in records if r.get("expected") is not None]
    if not test_records:
        return {}

    confidences = [_safe_confidence(r) for r in test_records]
    avg_confidence = float(np.mean(confidences)) if confidences else 0.0

    if _is_multilabel(test_records):
        y_true_sets = [as_label_set(r.get("expected")) for r in test_records]
        y_pred_sets = [as_label_set(r.get("prediction")) for r in test_records]
        classes = sorted(set().union(*y_true_sets, *y_pred_sets))
        if not classes:
            return {
                "precision": 1.0,
                "recall": 1.0,
                "accuracy": 1.0,
                "f1_score": 1.0,
                "basic_accuracy": 1.0,
                "avg_confidence": avg_confidence,
                "jaccard_samples": 1.0,
                "subset_accuracy": 1.0,
            }

        mlb = MultiLabelBinarizer(classes=classes)
        mlb.fit([classes])
        y_true = mlb.transform(y_true_sets)
        y_pred = mlb.transform(y_pred_sets)

        sample_f1 = f1_score(y_true, y_pred, average="samples", zero_division=0)
        jaccard_samples = jaccard_score(y_true, y_pred, average="samples", zero_division=0)
        subset_accuracy = accuracy_score(y_true, y_pred)
        return {
            "precision": precision_score(y_true, y_pred, average="micro", zero_division=0),
            "recall": recall_score(y_true, y_pred, average="micro", zero_division=0),
            "accuracy": subset_accuracy,
            "f1_score": sample_f1,
            "basic_accuracy": jaccard_samples,
            "avg_confidence": avg_confidence,
            "jaccard_samples": jaccard_samples,
            "subset_accuracy": subset_accuracy,
            "f1_micro": f1_score(y_true, y_pred, average="micro", zero_division=0),
            "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
        }

    y_true = [_normalise_scalar(r.get("expected")) for r in test_records]
    y_pred = [_normalise_scalar(r.get("prediction")) for r in test_records]
    accuracy = accuracy_score(y_true, y_pred)
    try:
        balanced = balanced_accuracy_score(y_true, y_pred)
    except ValueError:
        balanced = accuracy

    return {
        "precision": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "accuracy": accuracy,
        "f1_score": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "basic_accuracy": accuracy,
        "balanced_accuracy": balanced,
        "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "avg_confidence": avg_confidence,
    }


def select_confidence_threshold(
    records: Sequence[Dict[str, Any]],
    target_score: float = 0.90,
    metric_name: str = "basic_accuracy",
) -> Dict[str, float]:
    """Choose the lowest threshold that meets the quality target.

    Choosing the lowest acceptable threshold maximises automation coverage. If
    no threshold meets the target, the threshold with the best quality is used,
    with coverage as the tie-breaker.
    """
    test_records = [r for r in records if r.get("expected") is not None]
    if not test_records:
        return {
            "threshold": 0.0,
            "score": 0.0,
            "coverage": 0.0,
            "meets_target": False,
        }

    candidates = sorted({
        0.0,
        *[round(x / 100, 2) for x in range(50, 100)],
        *[_safe_confidence(r) for r in test_records],
    })
    evaluations = []
    for threshold in candidates:
        accepted = [r for r in test_records if _safe_confidence(r) >= threshold]
        if not accepted:
            continue
        metrics = evaluate_prediction_records(accepted)
        score = float(metrics.get(metric_name, 0.0) or 0.0)
        coverage = len(accepted) / len(test_records)
        evaluations.append((threshold, score, coverage, metrics))

    meeting = [item for item in evaluations if item[1] >= target_score]
    if meeting:
        threshold, score, coverage, metrics = max(
            meeting, key=lambda x: (x[2], x[1], -x[0])
        )
        meets_target = True
    else:
        threshold, score, coverage, metrics = max(
            evaluations, key=lambda x: (x[1], x[2], -x[0])
        )
        meets_target = False

    return {
        "threshold": float(threshold),
        "score": float(score),
        "coverage": float(coverage),
        "meets_target": meets_target,
        "metrics": metrics,
    }
