"""Guard semantics (PR-04 G1/G2/G4 + F2), fixtures shaped on real run-6 rows."""

from types import SimpleNamespace

from goldset.evaluators.guards import evaluate_guards

LONG_ANSWER = (
    "Based on WRI's mangrove statistics, Fatick has substantially more "
    "mangrove area than Ziguinchor, with extensive estuarine systems. "
    "See https://www.wri.org/insights/mangroves for background."
)


def state(answer=None, stats=None, dataset_id=None, charts=None):
    return {
        "messages": [SimpleNamespace(content=answer)] if answer else [],
        "statistics": stats if stats is not None else [],
        "dataset": {"dataset_id": dataset_id} if dataset_id else {},
        "charts_data": charts or [],
    }


PULL = [{"source_url": "https://api.example/pull/1", "id": "p1", "data": [{"a": 1}]}]


def test_g1_answered_without_data_catches_1_030_shape():
    result = evaluate_guards(
        state(answer=LONG_ANSWER),
        expects_data_pull=True, expected_answer="Fatick", expected_dataset_id="3",
    )
    assert result["answered_without_data_score"] == 0.0


def test_g1_clean_when_data_pulled():
    result = evaluate_guards(
        state(answer=LONG_ANSWER, stats=PULL, dataset_id="3"),
        expects_data_pull=True, expected_answer="Fatick", expected_dataset_id="3",
    )
    assert result["answered_without_data_score"] == 1.0


def test_g1_refusal_is_not_a_violation():
    result = evaluate_guards(
        state(answer="I can't answer that."),
        expects_data_pull=True, expected_answer="x", expected_dataset_id="",
    )
    assert result["answered_without_data_score"] == 1.0


def test_g1_not_applicable_without_pull_expectation():
    result = evaluate_guards(
        state(answer=LONG_ANSWER),
        expects_data_pull=False, expected_answer="", expected_dataset_id="",
    )
    assert result["answered_without_data_score"] is None


def test_f2_chart_produced():
    absent = evaluate_guards(
        state(answer="prose only", stats=PULL),
        expects_data_pull=True, expected_answer="42 ha", expected_dataset_id="",
    )
    assert absent["chart_produced_score"] == 0.0
    present = evaluate_guards(
        state(answer="prose", stats=PULL, charts=[{"type": "bar", "data": []}]),
        expects_data_pull=True, expected_answer="42 ha", expected_dataset_id="",
    )
    assert present["chart_produced_score"] == 1.0
    no_expectation = evaluate_guards(
        state(answer="prose"),
        expects_data_pull=False, expected_answer="", expected_dataset_id="",
    )
    assert no_expectation["chart_produced_score"] is None


def test_g2_web_fallback_flags_external_links_only():
    external = evaluate_guards(
        state(answer=LONG_ANSWER, stats=PULL, dataset_id="3"),
        expects_data_pull=True, expected_answer="x", expected_dataset_id="3",
    )
    assert external["web_fallback_score"] == 0.0
    assert "wri.org" in external["actual_web_links"]

    own = evaluate_guards(
        state(answer="See https://app.globalnaturewatch.org/threads/x for the map. "
                     + "A" * 60, stats=PULL, dataset_id="3"),
        expects_data_pull=True, expected_answer="x", expected_dataset_id="3",
    )
    assert own["web_fallback_score"] == 1.0


def test_g4_pull_source_match_and_abstention():
    match = evaluate_guards(
        state(answer="a" * 100, stats=[{**PULL[0], "dataset_id": "11"}]),
        expects_data_pull=True, expected_answer="x", expected_dataset_id="11",
    )
    assert match["pull_source_match_score"] == 1.0

    mismatch = evaluate_guards(
        state(answer="a" * 100, stats=[{**PULL[0], "dataset_id": "4"}]),
        expects_data_pull=True, expected_answer="x", expected_dataset_id="11",
    )
    assert mismatch["pull_source_match_score"] == 0.0

    unreadable = evaluate_guards(
        state(answer="a" * 100, stats=PULL),
        expects_data_pull=True, expected_answer="x", expected_dataset_id="11",
    )
    assert unreadable["pull_source_match_score"] is None
    assert "abstained" in unreadable["actual_pull_source"]


def test_guards_flow_through_registry():
    from goldset.eval_types import ExpectedData
    from goldset.runner.base import BaseTestRunner

    class _Probe(BaseTestRunner):
        async def run_test(self, query, expected_data):  # pragma: no cover
            raise NotImplementedError

    evaluations = _Probe()._run_evaluations(
        state(answer=LONG_ANSWER),
        ExpectedData(expected_answer="Fatick has more"),
        "which state has more mangroves?",
        None,
    )
    assert evaluations["answered_without_data_score"] == 0.0
    assert evaluations["chart_produced_score"] == 0.0
    assert evaluations["web_fallback_score"] == 0.0
