import pytest

from ml.metrics import (
    evaluate_prediction_records,
    list_jaccard_percent,
    select_confidence_threshold,
)


def test_single_label_uses_exact_match_not_substring():
    records = [
        {"expected": "High", "prediction": "Highest", "confidence": 0.95},
        {"expected": "Low", "prediction": "Low", "confidence": 0.80},
    ]
    metrics = evaluate_prediction_records(records)
    assert metrics["accuracy"] == pytest.approx(0.5)


def test_multilabel_jaccard_is_symmetric_and_penalises_extra_labels():
    assert list_jaccard_percent(["Backend", "Database"], ["Backend"]) == 50
    assert list_jaccard_percent(["Backend"], ["Backend", "Database"]) == 50
    assert list_jaccard_percent([], []) == 100


def test_threshold_selection_maximises_coverage_subject_to_quality():
    records = [
        {"expected": "A", "prediction": "A", "confidence": 0.95},
        {"expected": "A", "prediction": "A", "confidence": 0.80},
        {"expected": "A", "prediction": "B", "confidence": 0.60},
    ]
    result = select_confidence_threshold(records, target_score=0.90)
    assert result["meets_target"] is True
    assert result["threshold"] <= 0.80
    assert result["coverage"] == pytest.approx(2 / 3)


def test_multilabel_metrics_are_bounded():
    records = [
        {"expected": ["A", "B"], "prediction": ["A"], "confidence": 0.9},
        {"expected": ["C"], "prediction": ["C"], "confidence": 0.8},
    ]
    metrics = evaluate_prediction_records(records)
    for key in ("precision", "recall", "accuracy", "f1_score", "basic_accuracy"):
        assert 0.0 <= metrics[key] <= 1.0
