"""Case -> ExpectedData adaptation: prefixing, parsing, uid passthrough."""

from goldset.adapter import case_to_expected
from goldset.store import Case

CASE = Case(
    id="1-002",
    status="todo",
    group="direct",
    query="Sao Paulo disturbance in H2 2024?",
    expected={
        "aoi_ids": "BRA.25_1;BRA.14_1",
        "dataset_id": "11",
        "answer": "1,319,600 hectares",
        "clarification": "FALSE",
        "suggested_datasets": "0;11",
        "dashboard_widgets": "insight;map",
    },
    notes={"status_reason": "irrelevant to the harness"},
)


def test_prefixing_and_validator_parsing():
    expected = case_to_expected(CASE)
    assert expected.expected_dataset_id == "11"
    assert expected.expected_answer == "1,319,600 hectares"
    # ExpectedData's own validators apply, identically to gnw-evals:
    assert expected.expected_aoi_ids == ["BRA.25_1", "BRA.14_1"]
    assert expected.expected_clarification is False
    assert expected.expected_suggested_datasets == ["0", "11"]
    assert expected.expected_dashboard_widgets == ["insight", "map"]


def test_metadata_and_uid_ride_along():
    expected = case_to_expected(CASE)
    assert expected.test_id == "1-002"
    assert expected.test_group == "direct"
    assert expected.status == "todo"
    assert expected.uid == CASE.uid  # extra="allow" passthrough


def test_absent_fields_take_harness_defaults():
    bare = Case(id="x", status="ready", group="g", query="q")
    expected = case_to_expected(bare)
    assert expected.expected_answer == ""
    assert expected.expected_clarification is None
    assert expected.expects_data_pull() is False


def test_expects_data_pull_gating():
    assert case_to_expected(CASE).expects_data_pull() is True
    clarify = Case(
        id="y", status="ready", group="g", query="q",
        expected={"answer": "42 ha", "clarification": "TRUE"},
    )
    assert case_to_expected(clarify).expects_data_pull() is False
