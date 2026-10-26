"""The accepted-nudge path: a nudge offering every listed dataset (or area)
passes, and the pull checks are not applicable on that attempt.

Usage
$ uv run pytest tests/test_accepted_nudge.py -v
"""

from goldset.buckets import (
    PULL_PATH_CHECKS,
    implied_checks,
    reconcile,
    row_verdict,
)
from goldset.eval_types import ExpectedData
from goldset.evaluators.accepted_nudge import (
    evaluate_accepted_nudge,
    nudge_path,
)
from goldset.registry import EVALUATORS
from goldset.runner.base import BaseTestRunner


class _Probe(BaseTestRunner):
    async def run_test(self, query, expected_data):  # pragma: no cover
        raise NotImplementedError


def _nudge_state(*dataset_ids, pulled=False):
    """Agent state ending in a dataset_choice nudge, shaped like ch-comp-125's."""
    state = {
        "messages": [],
        "charts_data": [],
        "aoi_selection": {"aois": [{"src_id": "PER", "name": "Peru",
                                    "subtype": "country", "source": "gadm"}]},
        "nudge": {
            "type": "dataset_choice",
            "options": [f"dataset {i}" for i in dataset_ids],
            "data": [{"dataset_id": i, "dataset_name": f"dataset {i}"}
                     for i in dataset_ids],
        },
    }
    if pulled:
        state["statistics"] = [{"source_url": "https://x/analytics", "dataset_id": 8}]
    return state


def _aoi_nudge_state(*src_ids):
    """Agent state ending in an aoi_choice nudge, shaped like ch-quant-188's."""
    src_ids = src_ids or ("BRA.14_1", "SUR.6_1")
    return {
        "messages": [],
        "charts_data": [],
        "nudge": {
            "type": "aoi_choice",
            "options": list(src_ids),
            "data": [{"source": "gadm", "src_id": i, "name": i} for i in src_ids],
        },
    }


def test_every_listed_dataset_offered_passes_and_extras_are_allowed():
    result = evaluate_accepted_nudge(_nudge_state(8, 4), "8")
    assert result["accepted_nudge_match_score"] == 1.0
    assert result["actual_nudge_offered"] == "dataset_choice: 4; 8"


def test_a_listed_dataset_missing_from_the_nudge_fails():
    # ch-comp-154: expects 3;4, every nudge offered 4 and 1.
    assert evaluate_accepted_nudge(_nudge_state(4, 1), "3;4")[
        "accepted_nudge_match_score"] == 0.0


def test_abstains_without_the_expectation_or_off_the_nudge_path():
    assert evaluate_accepted_nudge(_nudge_state(8), "")[
        "accepted_nudge_match_score"] is None
    # A pull makes it the pull path, whatever else the state carries.
    assert evaluate_accepted_nudge(_nudge_state(8, pulled=True), "8")[
        "accepted_nudge_match_score"] is None
    # An area choice is not accepted by a dataset list alone.
    assert evaluate_accepted_nudge(_aoi_nudge_state(), "8")[
        "accepted_nudge_match_score"] is None
    assert nudge_path(_aoi_nudge_state(), "8", "") is None


def test_a_nudge_without_dataset_ids_abstains_loudly():
    state = {"nudge": {"type": "dataset_choice", "options": ["Tree cover loss"]}}
    result = evaluate_accepted_nudge(state, "4")
    assert result["accepted_nudge_match_score"] is None
    assert "abstained" in result["actual_nudge_offered"]


def test_pull_path_checks_are_exactly_the_presumes_pull_evaluators():
    from_registry = {
        field.removesuffix("_score")
        for spec in EVALUATORS
        if spec.presumes_pull
        for field in spec.score_fields
    }
    assert from_registry == PULL_PATH_CHECKS


def test_runner_skips_pull_checks_on_the_nudge_path():
    expected = ExpectedData(
        expected_aoi_ids="PER", expected_dataset_id="8",
        expected_data_pull="TRUE", expected_accept_nudge_offering="8",
    )
    evaluations = _Probe()._run_evaluations(_nudge_state(8, 4), expected, "q", None)
    assert evaluations["accepted_nudge_match_score"] == 1.0
    assert evaluations["aoi_id_match_score"] == 1.0
    for check in PULL_PATH_CHECKS:
        assert evaluations[f"{check}_score"] is None, check


def test_runner_scores_the_pull_path_as_before():
    expected = ExpectedData(
        expected_dataset_id="8", expected_data_pull="TRUE",
        expected_accept_nudge_offering="8",
    )
    # No nudge and no pull: a prose ask-back still fails the pull check.
    state = {"messages": [], "charts_data": []}
    evaluations = _Probe()._run_evaluations(state, expected, "q", None)
    assert evaluations["accepted_nudge_match_score"] is None
    assert evaluations["data_pull_exists_score"] == 0.0


NUDGE_OK = {"aoi_id_match": 1.0, "accepted_nudge_match": 1.0, "data_pull_exists": None}
PULL_FAIL = {"aoi_id_match": 1.0, "accepted_nudge_match": None, "data_pull_exists": 0.0}


def test_rows_on_the_nudge_path_are_judged_by_attempt_majority():
    # ch-causal-024 on 23 Oct: attempt 1 neither pulled nor nudged, attempts
    # 2 and 3 offered both datasets. The per-check majority of
    # data_pull_exists is 0.0 (one attempt measured it), yet 2 of 3 passed.
    entry = {
        "checks": {"aoi_id_match": 1.0, "accepted_nudge_match": 1.0,
                   "data_pull_exists": 0.0},
        "trials": [{"checks": PULL_FAIL}, {"checks": NUDGE_OK}, {"checks": NUDGE_OK}],
    }
    assert row_verdict(entry) == "pass"
    tie = {"checks": entry["checks"],
           "trials": [{"checks": NUDGE_OK}, {"checks": PULL_FAIL}]}
    assert row_verdict(tie) == "fail"
    assert row_verdict({**entry, "error": "timeout"}) == "error"


def test_rows_off_the_nudge_path_keep_per_check_majority():
    entry = {
        "checks": {"aoi_id_match": 1.0, "data_pull_exists": 1.0},
        "trials": [{"checks": {"aoi_id_match": 1.0, "data_pull_exists": 0.0}},
                   {"checks": {"aoi_id_match": 1.0, "data_pull_exists": 1.0}},
                   {"checks": {"aoi_id_match": 0.0, "data_pull_exists": 1.0}}],
    }
    assert row_verdict(entry) == "pass"


def test_reconcile_owes_only_the_checks_of_the_path_taken():
    expected = {"aoi_ids": "PER", "dataset_id": "8", "data_pull": "TRUE",
                "accept_nudge_offering": "8"}
    implied = implied_checks(expected)
    assert {"accepted_nudge_match", "data_pull_exists", "dataset_id_match"} <= implied
    nudge_row = {"uid": "u1", "id": "c1", "checks": {"aoi_id_match": 1.0,
                 "accepted_nudge_match": 1.0}}
    pull_row = {"uid": "u2", "id": "c2", "checks": {
        "aoi_id_match": 1.0, "dataset_id_match": 1.0, "data_pull_exists": 1.0,
        "answered_without_data": 1.0, "accepted_nudge_match": None}}
    result = reconcile([nudge_row, pull_row], {"u1": expected, "u2": expected})
    assert result["missing"] == []


def test_an_area_choice_offering_the_listed_area_passes():
    # ch-quant-188: Pará, Brazil (BRA.14) must be offered; Suriname's Para may be too.
    result = evaluate_accepted_nudge(_aoi_nudge_state(), "", "BRA.14")
    assert result["accepted_nudge_match_score"] == 1.0
    assert result["actual_nudge_offered"] == "aoi_choice: bra.14; sur.6"
    assert evaluate_accepted_nudge(_aoi_nudge_state("SUR.6_1"), "", "BRA.14")[
        "accepted_nudge_match_score"] == 0.0


def test_runner_skips_the_area_check_at_an_area_choice():
    expected = ExpectedData(
        expected_aoi_ids="BRA.14", expected_dataset_id="6",
        expected_data_pull="TRUE", expected_accept_aoi_nudge_offering="BRA.14",
    )
    evaluations = _Probe()._run_evaluations(_aoi_nudge_state(), expected, "q", None)
    assert evaluations["accepted_nudge_match_score"] == 1.0
    assert evaluations["aoi_id_match_score"] is None
    assert evaluations["data_pull_exists_score"] is None


def test_a_dataset_choice_keeps_the_area_check():
    expected = ExpectedData(
        expected_aoi_ids="PER", expected_accept_nudge_offering="8",
        expected_accept_aoi_nudge_offering="PER",
    )
    evaluations = _Probe()._run_evaluations(_nudge_state(8), expected, "q", None)
    assert evaluations["accepted_nudge_match_score"] == 1.0
    assert evaluations["aoi_id_match_score"] == 1.0


def test_reconcile_excuses_the_area_check_on_an_area_choice():
    expected = {"aoi_ids": "BRA.14", "dataset_id": "6", "data_pull": "TRUE",
                "accept_aoi_nudge_offering": "BRA.14"}
    row = {"uid": "u", "id": "c", "checks": {"accepted_nudge_match": 1.0,
           "aoi_id_match": None}}
    assert reconcile([row], {"u": expected})["missing"] == []
