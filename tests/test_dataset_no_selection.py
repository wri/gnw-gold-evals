"""dataset_id no_selection sentinel (CHALLENGE map set, unmappable cohort)."""

import sys
from pathlib import Path

from goldset.evaluators.dataset_evaluator import evaluate_dataset_selection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from coverage_doc import split_dataset_ids  # noqa: E402


def _score(state, expected_id, context_layer=""):
    return evaluate_dataset_selection(state, expected_id, "", context_layer)


def test_no_selection_passes_when_no_dataset():
    assert _score({}, "no_selection")["dataset_id_match_score"] == 1.0
    assert _score({"dataset": None}, "no_selection")["dataset_id_match_score"] == 1.0
    assert _score({"dataset": {"dataset_id": None}}, "NO_SELECTION")[
        "dataset_id_match_score"
    ] == 1.0


def test_no_selection_fails_when_a_dataset_was_substituted():
    state = {"dataset": {"dataset_id": 1, "dataset_name": "Global land cover"}}
    result = _score(state, "no_selection")
    assert result["dataset_id_match_score"] == 0.0
    assert result["actual_dataset_id"] == "1"


def test_sentinel_as_alternative():
    assert _score({}, "9;no_selection")["dataset_id_match_score"] == 1.0
    assert _score({"dataset": {"dataset_id": 9}}, "9;no_selection")[
        "dataset_id_match_score"
    ] == 1.0
    assert _score({"dataset": {"dataset_id": 4}}, "9;no_selection")[
        "dataset_id_match_score"
    ] == 0.0


def test_missing_dataset_without_sentinel_still_fails():
    result = _score({}, "4", context_layer="primary_forest")
    assert result["dataset_id_match_score"] == 0.0
    assert result["context_layer_match_score"] is None


def test_coverage_ignores_the_sentinel():
    assert split_dataset_ids("9;no_selection") == {"9"}
    assert split_dataset_ids("no_selection") == set()
