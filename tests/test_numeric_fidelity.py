"""DR-PR11 numeric-fidelity checks, fixtures shaped on the 2026-08-28 dry runs.

Run 1 (Sindhupalchok): asked to quote four exact values from its own
thread's analysis, the agent reported 18.25 / 22.38 / 1.83 / 1.14 ha where
the insight payload held 16.29 / 12.34 / no row at all / 0.068. Run 2
(newsroom prose): a claimed 2021 peak of 1,412 ha against an actual peak of
646 ha in 2014, "consistently above 800 ha/yr since 2017" against an actual
288-464 range, and a rising trend on a series whose 2024 value sits below
its 2005 value. Every matcher below is pinned to one of those shapes.

The extractor is an LLM pass and is mocked here; matching is pure code and
is tested directly (the suite runs with no network and no API keys).
"""

from types import SimpleNamespace

from langchain_core.prompts import ChatPromptTemplate

from goldset.evaluators import numeric_fidelity
from goldset.evaluators.chart_numeric import parse_expected_number
from goldset.evaluators.numeric_fidelity import (
    EXTRACTOR_PROMPT,
    NumericClaim,
    evaluate_numeric_fidelity,
    match_claims,
    trend_direction,
)

# Run-1's shape: two named series by year; 2020 district = 16.29,
# 2020 zones = 12.34, 2016 zones = 0.068, and no 2015 row anywhere.
CHART_SINDHUPALCHOK = {
    "type": "grouped_bar",
    "xAxis": "year",
    "yAxis": "area_ha",
    "data": [
        {"year": 2016, "district_loss_ha": 14.10, "landslide_zones_ha": 0.068},
        {"year": 2018, "district_loss_ha": 15.02, "landslide_zones_ha": 5.50},
        {"year": 2020, "district_loss_ha": 16.29, "landslide_zones_ha": 12.34},
    ],
}

# Run-2's shape: one loss series whose peak is 2014 at 646 ha, whose
# post-2017 values sit in the 288-464 range, and whose overall direction
# is falling (2024 below 2005).
CHART_NOVA = {
    "type": "bar",
    "xAxis": "year",
    "yAxis": "loss_ha",
    "data": [
        {"year": 2005, "loss_ha": 520.0},
        {"year": 2014, "loss_ha": 646.0},
        {"year": 2017, "loss_ha": 288.0},
        {"year": 2021, "loss_ha": 375.0},
        {"year": 2024, "loss_ha": 464.0},
    ],
}

# No year column at all: value claims must fall back to global candidates.
CHART_PIE = {
    "type": "pie",
    "xAxis": "category",
    "yAxis": "area_ha",
    "data": [
        {"category": "Natural", "area_ha": 2123.93},
        {"category": "Non-natural", "area_ha": 123810.97},
    ],
}


def state(charts=None, prose=None):
    return {
        "charts_data": charts or [],
        "messages": [SimpleNamespace(content=prose)] if prose else [],
    }


def value(number, year="", series="", quote=None):
    return NumericClaim(
        quote=quote or number, kind="value", number=number, year=year, series=series
    )


def one(claim, charts):
    verdicts = match_claims([claim], charts)
    assert len(verdicts) == 1
    return verdicts[0]


# --- value claims, year-scoped (run-1's fabricated quartet)


def test_fabricated_value_for_a_real_year_is_unsupported():
    verdict = one(value("18.25 ha", year="2020"), [CHART_SINDHUPALCHOK])
    assert verdict.status == "unsupported"
    assert "16.29" in verdict.reason  # names the closest real figure


def test_true_value_for_its_year_is_supported():
    assert one(value("16.29 ha", year="2020"), [CHART_SINDHUPALCHOK]).status == (
        "supported"
    )


def test_value_for_a_year_the_data_does_not_hold_is_unsupported():
    # Run 1 conjured a 2015 figure; the store has no 2015 row.
    verdict = one(value("1.83 ha", year="2015"), [CHART_SINDHUPALCHOK])
    assert verdict.status == "unsupported"
    assert "no row for year 2015" in verdict.reason


def test_small_decimal_value_is_checkable_not_ambiguous():
    # DR-PR11's acceptance quartet ends "0.068 for 2016" — a magnitude
    # below one must parse (the locale-ambiguity guard exempts it).
    assert parse_expected_number("0.068 ha") is not None
    assert parse_expected_number("230.003") is None  # still abstains
    verdict = one(
        value("0.068 ha", year="2016", series="landslide zones"),
        [CHART_SINDHUPALCHOK],
    )
    assert verdict.status == "supported"


def test_series_hint_narrows_to_the_named_column():
    # 14.10 belongs to the district column; tied to the zones series it
    # must not pass via the other column's value.
    verdict = one(
        value("14.10 ha", year="2016", series="landslide zones"),
        [CHART_SINDHUPALCHOK],
    )
    assert verdict.status == "unsupported"


def test_unresolved_series_hint_widens_instead_of_failing():
    verdict = one(
        value("16.29 ha", year="2020", series="somewhere unrelated"),
        [CHART_SINDHUPALCHOK],
    )
    assert verdict.status == "supported"


def test_percent_claim_is_checked_as_share_of_column_total():
    # zones 2020 share: 12.34 / (0.068 + 5.50 + 12.34) = 68.9%
    verdict = one(value("68.9%", year="2020"), [CHART_SINDHUPALCHOK])
    assert verdict.status == "supported"


def test_value_without_year_falls_back_to_global_candidates():
    leaf = one(value("123,810.97 hectares"), [CHART_PIE])
    assert leaf.status == "supported"
    total = one(value("125,934.90 hectares"), [CHART_PIE])  # sum of both slices
    assert total.status == "supported"
    invented = one(value("679.16 hectares"), [CHART_PIE])
    assert invented.status == "unsupported"


def test_unparseable_figure_is_skipped_never_guessed():
    assert one(value("several hundred ha"), [CHART_PIE]).status == "skipped"


# --- peak claims (run-2's wrong-year, 3.8x-inflated peak)


def peak(number="", year="", series=""):
    return NumericClaim(
        quote=f"peak {number} {year}", kind="peak", number=number, year=year,
        series=series,
    )


def test_wrong_peak_year_and_value_is_unsupported():
    verdict = one(peak(number="1,412 ha", year="2021"), [CHART_NOVA])
    assert verdict.status == "unsupported"
    assert "2014" in verdict.reason and "646" in verdict.reason


def test_true_peak_is_supported_with_or_without_value():
    assert one(peak(number="646 ha", year="2014"), [CHART_NOVA]).status == "supported"
    assert one(peak(year="2014"), [CHART_NOVA]).status == "supported"


def test_peak_claim_without_year_or_figure_is_skipped():
    assert one(peak(), [CHART_NOVA]).status == "skipped"


def test_peak_claim_without_time_series_is_skipped():
    assert one(peak(year="2014"), [CHART_PIE]).status == "skipped"


# --- bound claims ("consistently above 800 ha/yr since 2017")


def bound(number, bound_type, start="", end=""):
    return NumericClaim(
        quote=f"{bound_type} {number}", kind="bound", number=number,
        bound_type=bound_type, period_start=start, period_end=end,
    )


def test_violated_floor_claim_is_unsupported():
    verdict = one(bound("800 ha", "above", start="2017"), [CHART_NOVA])
    assert verdict.status == "unsupported"
    assert "288" in verdict.reason


def test_holding_ceiling_claim_is_supported():
    assert one(bound("700 ha", "below", start="2017"), [CHART_NOVA]).status == (
        "supported"
    )


def test_bound_with_no_series_in_period_is_skipped():
    assert one(bound("800 ha", "above", start="2030"), [CHART_NOVA]).status == (
        "skipped"
    )


# --- trend claims (run-2's inverted trend)


def trend(direction, series="", start="", end=""):
    return NumericClaim(
        quote=f"{direction} trend", kind="trend", direction=direction,
        series=series, period_start=start, period_end=end,
    )


def test_inverted_trend_claim_is_unsupported():
    verdict = one(trend("rising"), [CHART_NOVA])
    assert verdict.status == "unsupported"
    assert "falling" in verdict.reason


def test_true_trend_direction_is_supported():
    assert one(trend("falling"), [CHART_NOVA]).status == "supported"


def test_flat_series_reads_as_stable():
    points = [(2019, 100.0), (2020, 101.0), (2021, 100.0), (2022, 99.0),
              (2023, 100.0)]
    assert trend_direction(points) == "stable"
    assert trend_direction(points[:2]) is None  # two points are an anecdote


def test_disagreeing_series_abstain_unless_the_hint_resolves():
    chart = {
        "data": [
            {"year": 2019, "up_ha": 1.0, "down_ha": 9.0},
            {"year": 2021, "up_ha": 5.0, "down_ha": 5.0},
            {"year": 2023, "up_ha": 9.0, "down_ha": 1.0},
        ],
    }
    assert one(trend("rising"), [chart]).status == "skipped"
    assert one(trend("rising", series="up"), [chart]).status == "supported"
    assert one(trend("rising", series="down"), [chart]).status == "unsupported"


# --- the evaluator: aggregation, abstention, outage handling


def test_no_charts_or_prose_abstains_without_calling_the_extractor(monkeypatch):
    def boom(prose):  # pragma: no cover - the assertion is that it never runs
        raise AssertionError("extractor must not be called")

    monkeypatch.setattr(numeric_fidelity, "extract_numeric_claims", boom)
    for agent_state in (state(), state(charts=[CHART_NOVA]), state(prose="text")):
        result = evaluate_numeric_fidelity(agent_state)
        assert result["numeric_fidelity_score"] is None
        assert result["trend_fidelity_score"] is None
        assert result["judge_errors"] == []


def test_one_contradicted_claim_fails_the_row_and_names_it(monkeypatch):
    claims = [
        value("16.29 ha", year="2020"),
        value("18.25 ha", year="2020", quote="the district lost 18.25 ha in 2020"),
    ]
    monkeypatch.setattr(
        numeric_fidelity, "extract_numeric_claims", lambda prose: claims
    )
    result = evaluate_numeric_fidelity(
        state(charts=[CHART_SINDHUPALCHOK], prose="…")
    )
    assert result["numeric_fidelity_score"] == 0.0
    # the contradiction leads the reason (the ledger trims at 500 chars)
    assert result["numeric_fidelity_reason"].startswith(
        '"the district lost 18.25 ha in 2020"'
    )
    assert result["trend_fidelity_score"] is None
    assert "[supported]" in result["actual_numeric_claims"]
    assert "[unsupported]" in result["actual_numeric_claims"]


def test_trend_and_value_claims_score_independently(monkeypatch):
    claims = [value("646 ha", year="2014"), trend("rising")]
    monkeypatch.setattr(
        numeric_fidelity, "extract_numeric_claims", lambda prose: claims
    )
    result = evaluate_numeric_fidelity(state(charts=[CHART_NOVA], prose="…"))
    assert result["numeric_fidelity_score"] == 1.0
    assert result["trend_fidelity_score"] == 0.0


def test_all_claims_skipped_scores_null_with_the_reasons(monkeypatch):
    claims = [value("several hundred ha")]
    monkeypatch.setattr(
        numeric_fidelity, "extract_numeric_claims", lambda prose: claims
    )
    result = evaluate_numeric_fidelity(state(charts=[CHART_NOVA], prose="…"))
    assert result["numeric_fidelity_score"] is None
    assert "none verifiable" in result["numeric_fidelity_reason"]


def test_no_claims_extracted_scores_null(monkeypatch):
    monkeypatch.setattr(
        numeric_fidelity, "extract_numeric_claims", lambda prose: []
    )
    result = evaluate_numeric_fidelity(state(charts=[CHART_NOVA], prose="…"))
    assert result["numeric_fidelity_score"] is None
    assert result["numeric_fidelity_reason"] == "no numeric claims extracted"


def test_extractor_outage_is_a_judge_error_never_a_verdict(monkeypatch):
    def boom(prose):
        raise RuntimeError("api down")

    monkeypatch.setattr(numeric_fidelity, "extract_numeric_claims", boom)
    result = evaluate_numeric_fidelity(state(charts=[CHART_NOVA], prose="…"))
    assert result["numeric_fidelity_score"] is None
    assert result["trend_fidelity_score"] is None
    assert result["judge_errors"] == ["numeric_fidelity", "trend_fidelity"]
    assert "JUDGE ERROR" in result["numeric_fidelity_reason"]


def test_unknown_claim_kind_is_skipped():
    verdict = one(NumericClaim(quote="?", kind="ratio"), [CHART_NOVA])
    assert verdict.status == "skipped"


# --- prompt hygiene (mirrors test_numeric_tolerance's guards)


def test_extractor_prompt_exposes_exactly_answer_prose():
    prompt = ChatPromptTemplate.from_messages([("user", EXTRACTOR_PROMPT)])
    assert prompt.input_variables == ["answer_prose"]


def test_extractor_prompt_does_not_ask_the_model_to_verify_or_compute():
    assert "Do not verify, compute" in EXTRACTOR_PROMPT
    assert "tolerance" not in EXTRACTOR_PROMPT.lower()
