"""The accepted alternative paths: a nudge offering every listed dataset (or
area), or an answer from search_blogs citing an accepted post, passes, and the
pull checks are not applicable on that attempt.

Usage
$ uv run pytest tests/test_accepted_nudge.py -v
"""

from types import SimpleNamespace

from goldset.buckets import (
    PULL_PATH_CHECKS,
    implied_checks,
    reconcile,
    row_verdict,
)
from goldset.eval_types import ExpectedData
from goldset.evaluators.accepted_blog import blog_path, evaluate_accepted_blog
from goldset.evaluators.accepted_nudge import (
    evaluate_accepted_nudge,
    nudge_path,
)
from goldset.evaluators.guards import evaluate_guards
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


def test_any_one_alternative_offer_passes():
    # ch-comp-155 (draft-5 review): drivers with tree cover loss, or sLUC alone.
    def score(*offered):
        return evaluate_accepted_nudge(_nudge_state(*offered), "4;8 | 9")[
            "accepted_nudge_match_score"]

    assert score(9) == 1.0
    assert score(8, 4, 1) == 1.0
    assert score(8, 1) == 0.0  # half of the first offer is not enough


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


# --- accepted blog path ---------------------------------------------------

RIAU = "https://www.wri.org/insights/preventing-forest-fires-indonesia-focus-riau-province-peatland-and-illegal-burning"
OTHER = "https://www.wri.org/insights/some-other-post"
ACCEPTED = "preventing-forest-fires-indonesia-focus-riau-province-peatland-and-illegal-burning;peering-through-haze-what-data-can-tell-us-about-fires-indonesia"


def _blog_state(answer, pulled=False):
    """Agent state answering from search_blogs, shaped like ch-causal-022's."""
    state = {
        "messages": [
            SimpleNamespace(tool_calls=[{"name": "search_blogs", "args": {}}], content=""),
            SimpleNamespace(tool_calls=None, content=answer),
        ],
        "charts_data": [],
    }
    if pulled:
        state["statistics"] = [{"source_url": "https://x/analytics", "dataset_id": 10}]
    return state


def test_a_blog_answer_citing_an_accepted_post_passes():
    result = evaluate_accepted_blog(_blog_state(f"Peat fires ([source]({RIAU}#p3))."), ACCEPTED)
    assert result["accepted_blog_match_score"] == 1.0
    assert "preventing-forest-fires" in result["actual_blog_sources_cited"]


def test_a_blog_answer_citing_only_other_posts_or_nothing_fails():
    assert evaluate_accepted_blog(_blog_state(f"See {OTHER}"), ACCEPTED)[
        "accepted_blog_match_score"] == 0.0
    assert evaluate_accepted_blog(_blog_state("Fires burn peat."), ACCEPTED)[
        "accepted_blog_match_score"] == 0.0


def test_the_blog_path_needs_search_blogs_and_no_pull():
    assert not blog_path(_blog_state(RIAU, pulled=True), ACCEPTED)
    assert not blog_path({"messages": [SimpleNamespace(tool_calls=None, content=RIAU)]}, ACCEPTED)
    assert not blog_path(_blog_state(RIAU), "")


def test_runner_skips_pull_and_area_checks_on_the_blog_path():
    expected = ExpectedData(
        expected_aoi_ids="IDN.24", expected_dataset_id="10;8;11",
        expected_data_pull="TRUE", expected_accept_blog_sources=ACCEPTED,
    )
    evaluations = _Probe()._run_evaluations(_blog_state(f"[x]({RIAU})"), expected, "q", None)
    assert evaluations["accepted_blog_match_score"] == 1.0
    assert evaluations["aoi_id_match_score"] is None
    for check in PULL_PATH_CHECKS:
        assert evaluations[f"{check}_score"] is None, check


def test_web_fallback_ignores_accepted_posts():
    # Without a pull (after one, web_fallback abstains altogether).
    state = {"messages": [SimpleNamespace(content=f"Loss rose ([a]({RIAU})).")],
             "statistics": [], "charts_data": []}
    allowed = evaluate_guards(state, True, "", "10", accepted_blog_sources=ACCEPTED)
    assert allowed["web_fallback_score"] == 1.0
    state["messages"][0].content += f" See {OTHER}."
    assert evaluate_guards(state, True, "", "10", accepted_blog_sources=ACCEPTED)[
        "web_fallback_score"] == 0.0


def test_rows_on_the_blog_path_are_judged_by_attempt_majority():
    blog_ok = {"accepted_blog_match": 1.0, "data_pull_exists": None}
    pull_fail = {"accepted_blog_match": None, "data_pull_exists": 0.0}
    entry = {"checks": {"accepted_blog_match": 1.0, "data_pull_exists": 0.0},
             "trials": [{"checks": pull_fail}, {"checks": blog_ok}, {"checks": blog_ok}]}
    assert row_verdict(entry) == "pass"


def test_reconcile_owes_a_blog_row_only_its_path_checks():
    expected = {"aoi_ids": "IDN.24", "dataset_id": "10", "data_pull": "TRUE",
                "accept_blog_sources": ACCEPTED}
    assert "accepted_blog_match" in implied_checks(expected)
    row = {"uid": "u", "id": "c", "checks": {"accepted_blog_match": 1.0, "aoi_id_match": None}}
    assert reconcile([row], {"u": expected})["missing"] == []
