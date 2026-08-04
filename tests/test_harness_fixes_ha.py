"""PR-Ha — the four corrective harness fixes (docs/specs/caseset-v2-improvement-plan.md §4).

Each of these turned a *correct* agent answer into a failing check, so every
case below is taken from the row that exposed it in a real staging run.

    H1  parse_expected_number dropped a leading minus sign          (1-055)
    H2  pull_source_match never split ";" alternatives              (1-003, 1-062)
    H3  evaluate_scope had no ";" alternatives support               (1-089)
    H8  web_fallback flagged the product's own tile domain          (1-095)

Usage
$ uv run python -m pytest tests/test_harness_fixes_ha.py -v
"""

import json
from types import SimpleNamespace

from goldset.evaluators.chart_numeric import (
    evaluate_numeric_support,
    parse_expected_number,
)
from goldset.evaluators.guards import evaluate_guards
from goldset.evaluators.scope_checks import evaluate_scope

TOLERANCE = 0.02


# --------------------------------------------------------------------------- H1

def test_h1_negative_expected_number_keeps_its_sign():
    """1-055 expects a net *sink*: -286,994 Mg CO2e. The sign is the capability."""
    parsed = parse_expected_number("-286,994 Mg CO2e")
    assert parsed is not None
    assert parsed.value == -286_994.0


def test_h1_negative_expected_matches_the_charts_own_net_flux():
    """The chart's net-flux series held -286,993.69 all along — a 0.0001% match
    that the unsigned parse rejected in favour of a far-off gross-emissions bar."""
    charts = json.dumps(
        [
            {
                "type": "bar",
                "data": [
                    {"metric": "gross_emissions", "value": 37_436.76},
                    {"metric": "gross_removals", "value": -324_430.45},
                    {"metric": "net_flux", "value": -286_993.69},
                ],
            },
        ],
    )
    result = evaluate_numeric_support("-286,994 Mg CO2e", charts, TOLERANCE)
    assert result["support"] == "supported", result["explanation"]
    assert result["closest_value"] == -286_993.69


def test_h1_hyphen_inside_a_word_is_not_a_minus_sign():
    """1-104's expectation mentions "Sentinel-2"; that 2 is positive."""
    parsed = parse_expected_number("Sentinel-2 scenes: 5 hectares")
    assert parsed is not None
    assert parsed.value > 0


def test_h1_year_range_still_abstains():
    """1-052 expects '2015-2020'. A year is not a measurement, signed or not."""
    assert parse_expected_number("2015-2020") is None


def test_h1_negative_ambiguous_decimal_still_abstains():
    """The sign must not smuggle a value past the ambiguous-separator guard."""
    assert parse_expected_number("-230.003") is None


# --------------------------------------------------------------------------- H2

def _pull_state(dataset_id: int) -> dict:
    return {
        "messages": [],
        "charts_data": [],
        "statistics": {"dataset_id": dataset_id, "data": [1], "source_url": "x"},
        "dataset": {"dataset_id": dataset_id},
    }


def test_h2_pull_source_accepts_either_alternative():
    """1-003 expects '0;11' — DIST-ALERT and integrated alerts are both correct
    routings, per cases/README.md. Either must satisfy the guard."""
    for dataset_id in (0, 11):
        result = evaluate_guards(
            _pull_state(dataset_id),
            expects_data_pull=True,
            expected_answer="",
            expected_dataset_id="0;11",
        )
        assert result["pull_source_match_score"] == 1.0, dataset_id


def test_h2_pull_source_still_fails_a_dataset_outside_the_set():
    result = evaluate_guards(
        _pull_state(4),
        expects_data_pull=True,
        expected_answer="",
        expected_dataset_id="0;11",
    )
    assert result["pull_source_match_score"] == 0.0


def test_h2_single_value_expectation_is_unchanged():
    """The common case must not shift while fixing the alternatives case."""
    assert evaluate_guards(
        _pull_state(11), expects_data_pull=True, expected_answer="",
        expected_dataset_id="11",
    )["pull_source_match_score"] == 1.0
    assert evaluate_guards(
        _pull_state(4), expects_data_pull=True, expected_answer="",
        expected_dataset_id="11",
    )["pull_source_match_score"] == 0.0


def test_h2_dataset_id_zero_is_a_real_registry_id():
    """id 0 is DIST-ALERT, not absence — the falsiness bug that manufactured
    1-088's phantom standing failure."""
    assert evaluate_guards(
        _pull_state(0), expects_data_pull=True, expected_answer="",
        expected_dataset_id="0",
    )["pull_source_match_score"] == 1.0


# --------------------------------------------------------------------------- H3

def test_h3_scope_accepts_alternatives():
    """1-089's own `text` licenses two behaviours: refuse outright, or caution
    and offer the annual dataset via a nudge. Both must pass.

    Note the alternative is `refuse;suggest`, not `refuse;clarify`: H4 classifies
    a `dataset_choice` nudge as `suggest`, and 1-089's observed nudge offers
    datasets ("Tree cover loss"). This is the coordination the plan flagged — H3
    and H4 together decide 1-089's expectation.
    """
    refused = {"statistics": None, "suggested_datasets": [], "nudge": {}}
    cautioned = {"statistics": None, "suggested_datasets": [],
                 "nudge": {"type": "dataset_choice"}}
    for state in (refused, cautioned):
        assert evaluate_scope(state, "refuse;suggest")["scope_match_score"] == 1.0


def test_h3_alternatives_accept_an_aoi_clarification():
    """The `clarify` class still exists for aoi_choice-shaped nudges."""
    state = {"statistics": None, "suggested_datasets": [],
             "nudge": {"type": "aoi_choice"}}
    assert evaluate_scope(state, "analyse;clarify")["scope_match_score"] == 1.0


def test_h3_scope_alternatives_still_reject_an_unlisted_class():
    analysed = {"statistics": {"data": [1]}, "suggested_datasets": [], "nudge": {}}
    assert evaluate_scope(analysed, "refuse;suggest")["scope_match_score"] == 0.0


def test_h3_single_scope_is_unchanged():
    analysed = {"statistics": {"data": [1]}, "suggested_datasets": [], "nudge": {}}
    assert evaluate_scope(analysed, "analyse")["scope_match_score"] == 1.0
    assert evaluate_scope(analysed, "refuse")["scope_match_score"] == 0.0


def test_h3_invalid_alternative_still_abstains():
    """A typo in one alternative must abstain loudly, not silently pass."""
    analysed = {"statistics": {"data": [1]}, "suggested_datasets": [], "nudge": {}}
    result = evaluate_scope(analysed, "analyse;bogus")
    assert result["scope_match_score"] is None
    assert "bogus" in (result["actual_scope"] or "")


# --------------------------------------------------------------------------- H8

def _answer_state(answer: str) -> dict:
    return {
        "messages": [SimpleNamespace(content=answer)],
        "charts_data": [{"type": "bar"}],
        "statistics": {"dataset_id": 4, "data": [1], "source_url": "x"},
        "dataset": {"dataset_id": 4},
    }


def test_h8_own_tile_domain_is_not_web_fallback():
    """1-095 answered correctly from a real pull and linked the product's own
    GFW dashboard; G2's premise ('came from web knowledge') was false."""
    state = _answer_state(
        "Finland lost 241,368.24 hectares in 2025 at a 10% canopy threshold. "
        "See also https://www.globalforestwatch.org/dashboards/country/FIN/ "
        "for the same figures." + " padding" * 10,
    )
    result = evaluate_guards(state, expects_data_pull=True, expected_answer="x",
                             expected_dataset_id="4")
    assert result["web_fallback_score"] == 1.0


def test_h8_wri_org_citation_still_fires():
    """1-030's signal must survive: a wri.org citation is the blog-skill tell."""
    state = _answer_state(
        "Ziguinchor has the most mangroves in Senegal, per "
        "https://www.wri.org/insights/mangrove-restoration." + " padding" * 10,
    )
    result = evaluate_guards(state, expects_data_pull=True, expected_answer="x",
                             expected_dataset_id="4")
    assert result["web_fallback_score"] == 0.0
    assert "wri.org" in (result["actual_web_links"] or "")


# --------------------------------------------------------------------- H1 (cont.)

def test_h1_a_year_followed_by_a_comma_still_abstains():
    """Found while documenting the evaluators (2026-08-04): the token "2020,"
    carries a trailing comma, so it missed the `^(19|20)\\d{2}$` year guard and
    became the expected *value* — an expectation of 2020 hectares.

    Abstention, rather than skipping ahead to 25.5 Mha, is the deliberate
    outcome: it matches what the same string without the comma has always done
    (`"In 2020 25.5 Mha"` -> None). A leading year means the claim is ambiguous,
    and this check abstains rather than guessing which number is the answer.
    No cases/v2 row has this shape; the guard is here so none can.
    """
    assert parse_expected_number("In 2020, 25.5 Mha of loss") is None
    assert parse_expected_number("In 2020 25.5 Mha of loss") is None
    # the bare year, with or without trailing punctuation, is not a measurement
    assert parse_expected_number("2020") is None
    assert parse_expected_number("2020,") is None
    assert parse_expected_number("2020.") is None


def test_h1_thousands_separators_still_parse():
    """The trailing-punctuation strip must not damage normal figures."""
    assert parse_expected_number("1,299,278 hectares").value == 1_299_278.0
    assert parse_expected_number("25.54 million hectares").value == 25_540_000.0
    assert parse_expected_number("679.17 ha").value == 679.17
