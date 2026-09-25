"""forbidden_tools_absent: opt-in tool-scope isolation (CHALLENGE map set)."""

from types import SimpleNamespace

from goldset.buckets import buckets_for, implied_checks, is_info_only
from goldset.eval_types import ExpectedData
from goldset.evaluators.tool_checks import (
    called_tool_names,
    evaluate_forbidden_tools,
)
from goldset.registry import EVALUATORS

FORBIDDEN = "pick_aoi;pull_data;generate_insights"


def _msg(*names):
    """LangChain-style message object carrying tool_calls."""
    return SimpleNamespace(tool_calls=[{"name": n, "args": {}} for n in names])


def test_no_expectation_abstains():
    result = evaluate_forbidden_tools({"messages": [_msg("pull_data")]}, "")
    assert result["forbidden_tools_absent_score"] is None


def test_clean_pick_only_passes():
    state = {"messages": [SimpleNamespace(tool_calls=None), _msg("pick_dataset")]}
    result = evaluate_forbidden_tools(state, FORBIDDEN)
    assert result["forbidden_tools_absent_score"] == 1.0
    assert result["actual_tool_names"] == "pick_dataset"
    assert result["actual_forbidden_tools_called"] is None


def test_forbidden_call_fails_and_names_offenders():
    state = {"messages": [_msg("pick_dataset"), _msg("pick_aoi", "pull_data")]}
    result = evaluate_forbidden_tools(state, FORBIDDEN)
    assert result["forbidden_tools_absent_score"] == 0.0
    assert result["actual_forbidden_tools_called"] == "pick_aoi; pull_data"


def test_dict_messages_and_case_insensitive_list():
    state = {"messages": [{"tool_calls": [{"name": "Pick_AOI"}]}]}
    result = evaluate_forbidden_tools(state, " PICK_AOI ; pull_data ")
    assert result["forbidden_tools_absent_score"] == 0.0


def test_empty_message_list_scores_but_missing_messages_abstains():
    assert evaluate_forbidden_tools({"messages": []}, FORBIDDEN)[
        "forbidden_tools_absent_score"
    ] == 1.0
    missing = evaluate_forbidden_tools({}, FORBIDDEN)
    assert missing["forbidden_tools_absent_score"] is None
    assert "abstained" in missing["actual_forbidden_tools_called"]


def test_called_tool_names_keeps_order_and_duplicates():
    state = {"messages": [_msg("read_skill", "pick_dataset"), _msg("pick_dataset")]}
    assert called_tool_names(state) == ["read_skill", "pick_dataset", "pick_dataset"]


def test_wired_as_gating_scope_check_and_implied():
    assert buckets_for("forbidden_tools_absent") == ("scope",)
    assert not is_info_only("forbidden_tools_absent")
    assert "forbidden_tools_absent" in implied_checks({"forbidden_tools": FORBIDDEN})
    assert "forbidden_tools_absent" not in implied_checks({"dataset_id": "4"})


def test_flows_through_registry_from_expected_data():
    spec = next(s for s in EVALUATORS if s.name == "tool_scope")
    expected = ExpectedData(expected_forbidden_tools=FORBIDDEN)
    out = spec.run({"messages": [_msg("pull_data")]}, expected, "q", None)
    assert out["forbidden_tools_absent_score"] == 0.0
