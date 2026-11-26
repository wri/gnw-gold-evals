"""CodeAct checks: the chart route, and the chart's values against the pull."""

import pytest
from pydantic import ValidationError

from goldset.buckets import implied_checks
from goldset.eval_types import ExpectedData
from goldset.evaluators.codeact_checks import evaluate_chart_route, validate

CHART = {"type": "bar", "xAxis": "year", "yAxis": "area_ha",
         "data": [{"year": 2020, "area_ha": 1.0}]}
CODE = [{"type": "code_block", "content": "cHJpbnQoMSk="}]


# ------------------------------------------------------------ chart_route_match


@pytest.mark.parametrize(("state", "route"), [
    ({"charts_data": [CHART], "codeact_parts": CODE}, "codeact"),
    ({"charts_data": [CHART], "codeact_parts": []}, "curated"),
    ({"charts_data": [CHART]}, "curated"),
    ({"charts_data": [], "codeact_parts": CODE}, "none"),
    ({}, "none"),
])
def test_the_route_comes_from_the_charts_and_the_code_parts(state, route):
    result = evaluate_chart_route(state, "codeact")
    assert result["actual_chart_route"] == route
    assert result["chart_route_match_score"] == (1.0 if route == "codeact" else 0.0)


def test_a_curated_expectation_passes_a_curated_chart_only():
    curated = {"charts_data": [CHART], "codeact_parts": []}
    assert evaluate_chart_route(curated, "curated")["chart_route_match_score"] == 1.0
    codeact = {"charts_data": [CHART], "codeact_parts": CODE}
    result = evaluate_chart_route(codeact, "curated")
    assert result["chart_route_match_score"] == 0.0
    assert result["chart_route_match_reason"] == (
        "expected curated, got codeact (1 charts, 1 code parts)"
    )


def test_no_route_expectation_abstains():
    result = evaluate_chart_route({"charts_data": [CHART]}, "")
    assert result["chart_route_match_score"] is None
    assert result["actual_chart_route"] is None


@pytest.mark.parametrize("bad", ["CodeAct", "code", "none"])
def test_an_unknown_route_fails_loudly(bad):
    with pytest.raises(ValueError, match="chart_route"):
        evaluate_chart_route({"charts_data": [CHART]}, bad)
    with pytest.raises(ValidationError):
        ExpectedData(expected_chart_route=bad)
    assert validate({"chart_route": bad})


def test_a_route_expectation_is_parsed_and_implied():
    assert ExpectedData(expected_chart_route="codeact").expected_chart_route == "codeact"
    assert ExpectedData().expected_chart_route == ""
    assert validate({"chart_route": "curated"}) == []
    assert implied_checks({"chart_route": "codeact"}) == {"chart_route_match"}
