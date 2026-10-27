"""Figure checks (draft-5): formulas over the agent's own pulled table."""

from types import SimpleNamespace

import pytest

from goldset.evaluators import figures
from goldset.evaluators.figures import (
    Aggregate,
    Combined,
    FigureError,
    candidates,
    claim_sentence,
    compute,
    evaluate_answer_period,
    evaluate_figure_claim,
    evaluate_figures,
    parse_claim,
    parse_figures,
    parse_formula,
    stated_numbers,
    validate,
)

TCL = [
    {"aoi_id": "PER.12", "tree_cover_loss_year": year, "area_ha": area}
    for year, area in [(2018, 100.0), (2019, 200.0), (2020, 300.0), (2021, 400.0)]
] + [{"aoi_id": "PER.23", "tree_cover_loss_year": 2020, "area_ha": 50.0}]


def _state(answer, *tables):
    urls = [f"https://analytics/{i}" for i in range(len(tables))]
    return (
        {"messages": [SimpleNamespace(content=answer)],
         "statistics": [{"source_url": u, "data": {}} for u in urls]},
        dict(zip(urls, tables, strict=True)),
    )


@pytest.fixture
def pulled(monkeypatch):
    """Serve tables by URL instead of fetching them."""
    def use(tables_by_url):
        def fake(url):
            rows = tables_by_url.get(url)
            if rows is None:
                return None
            columns = tuple(sorted({k for r in rows for k in r}))
            return columns, tuple(tuple(r.get(c) for c in columns) for r in rows)
        monkeypatch.setattr(figures, "_fetch", fake)
    return use


# ------------------------------------------------------------------ grammar


def test_parses_aggregates_conditions_and_groups():
    formula = parse_formula(
        "mean(area_ha) by tree_cover_loss_year where tree_cover_loss_year in 2018..2020"
        " and aoi_id = 'PER.12'"
    )
    assert formula == Aggregate(
        "mean", ("area_ha",), "tree_cover_loss_year",
        (figures.Condition("tree_cover_loss_year", "range", (2018, 2020)),
         figures.Condition("aoi_id", "=", ("PER.12",))),
    )
    assert isinstance(parse_formula("ratio(sum(a) where x = 1, sum(a))"), Combined)


def test_figures_split_into_alternatives_and_refs():
    parsed = parse_figures("sum(area_ha) | mean(area_ha) ; ref: max(area_ha) by year")
    assert [len(f.alternatives) for f in parsed] == [2, 1]
    assert [f.ref for f in parsed] == [False, True]


@pytest.mark.parametrize("bad", [
    "total(area_ha)", "sum(area ha)", "sum(area_ha) when year = 1", "ratio(sum(a))",
    "sum(area_ha) where year ~ 3",
])
def test_bad_formulas_fail_loudly(bad):
    with pytest.raises(FigureError):
        parse_figures(bad)


def test_validate_reports_case_errors():
    assert validate({"figure": "sum(area_ha)"}) == []
    assert validate({"figure": "sum(area_ha)", "figure_claim": "#1 > 0 :: a || b"}) == []
    assert validate({"figure": "sum(area_ha)", "figure_claim": "#2 > 0 :: a || b"})
    assert validate({"figure_claim": "#1 > 0 :: a || b"})


# -------------------------------------------------------------- computation


def test_sum_mean_and_grouped_aggregates():
    assert compute(parse_formula("sum(area_ha) where tree_cover_loss_year in 2018..2019"),
                   TCL) == 300.0
    # Annual mean across both areas' rows for 2020 is summed per year first.
    assert compute(parse_formula(
        "mean(area_ha) by tree_cover_loss_year where tree_cover_loss_year in 2019..2020"),
        TCL) == (200.0 + 350.0) / 2
    assert compute(parse_formula("max(area_ha) by tree_cover_loss_year"), TCL) == 400.0
    assert compute(parse_formula("count(area_ha) where aoi_id = 'per.23'"), TCL) == 1.0


def test_combined_figures():
    assert compute(parse_formula(
        "change(sum(area_ha) where tree_cover_loss_year = 2018, "
        "sum(area_ha) where tree_cover_loss_year = 2021)"), TCL) == 300.0
    assert compute(parse_formula(
        "ratio(sum(area_ha) where aoi_id = 'PER.23', sum(area_ha))"), TCL) == 50 / 1050


def test_a_missing_column_is_not_computable_and_tables_are_not_mixed():
    other = [{"land_cover_class": "Cropland", "area_ha": 9.0}]
    # sum(area_ha) per table, plus the union; never a figure from the wrong
    # dataset alone when the formula names a column only TCL has.
    by_year = parse_formula("sum(area_ha) where tree_cover_loss_year = 2021")
    assert candidates(by_year, [TCL, other]) == [400.0]
    unfiltered = parse_formula("sum(area_ha)")
    assert candidates(unfiltered, [TCL, other]) == [1050.0, 9.0, 1059.0]


# ---------------------------------------------------------------- the reply


def test_reads_numbers_with_scales_and_skips_years():
    stated = {s.text: s for s in stated_numbers(
        "In 2024 Bolivia lost 1.8 million hectares (1,813,615 ha), 4.3% of its forest,"
        " about 42 Mt CO2e, or 18,136 km²."
    )}
    assert stated["1.8 million"].value == pytest.approx(1.8e6)
    assert stated["1,813,615 ha"].value == 1813615
    assert stated["4.3%"].percent
    assert "2024" not in stated
    assert stated["42 Mt"].value == pytest.approx(42e6)
    assert stated["18,136 km²"].value == pytest.approx(1813600)


def test_figure_match_passes_rounding_and_fails_a_wrong_figure(pulled):
    figure = "sum(area_ha) where tree_cover_loss_year in 2018..2021"
    state, tables = _state("Loss totalled about 1,050 hectares.", TCL)
    pulled(tables)
    result = evaluate_figures(state, figure)
    assert result["figure_match_score"] == 1.0  # both areas: 1,000 + 50
    state, tables = _state("Loss totalled 1,250 hectares.", TCL)
    pulled(tables)
    result = evaluate_figures(state, figure)
    assert result["figure_match_score"] == 0.0
    assert "not in the reply" in result["actual_figures"]


def test_figure_match_abstains_without_a_readable_pull(pulled):
    state, tables = _state("1,000 ha", TCL)
    pulled({})
    assert evaluate_figures(state, "sum(area_ha)")["figure_match_score"] is None
    pulled(tables)
    assert evaluate_figures(state, "sum(other_column)")["figure_match_score"] is None


def test_shares_match_as_a_fraction_or_a_percentage(pulled):
    share = "ratio(sum(area_ha) where aoi_id = 'PER.23', sum(area_ha))"  # 4.76%
    for answer, score in [("about 4.8% of the loss", 1.0), ("a share of 0.048", 1.0),
                          ("about 9% of the loss", 0.0)]:
        state, tables = _state(answer, TCL)
        pulled(tables)
        assert evaluate_figures(state, share)["figure_match_score"] == score, answer


def test_a_comparison_split_over_two_pulls_uses_their_union(pulled):
    first = [r for r in TCL if r["aoi_id"] == "PER.12"]
    second = [r for r in TCL if r["aoi_id"] == "PER.23"]
    state, tables = _state("PER.12 lost 1,000 ha and PER.23 lost 50 ha.", first, second)
    pulled(tables)
    figure = "sum(area_ha) where aoi_id = 'PER.12' ; sum(area_ha) where aoi_id = 'PER.23'"
    assert evaluate_figures(state, figure)["figure_match_score"] == 1.0


# ---------------------------------------------------------------- the claim


def test_the_data_picks_the_claim_sentence(pulled):
    state, tables = _state("", TCL)
    pulled(tables)
    figure = ("sum(area_ha) where tree_cover_loss_year = 2021 ; "
              "ref: max(area_ha) by tree_cover_loss_year where tree_cover_loss_year in 2018..2020")
    sentence, detail = claim_sentence(state, figure, "#1 > #2 :: 2021 was the record || not")
    assert sentence == "2021 was the record"
    assert "is True" in detail
    assert parse_claim("#1 < 0 :: sink || source", 1).op == "<"


def test_figure_claim_is_judged_on_the_true_sentence(pulled, monkeypatch):
    seen = {}

    def judge(sentence, answer):
        seen["sentence"] = sentence
        return {"score": 1, "reason": "it says so"}

    monkeypatch.setattr("goldset.evaluators.llm_judges.llm_judge_claim", judge)
    state, tables = _state("2021 was the worst year.", TCL)
    pulled(tables)
    result = evaluate_figure_claim(
        state, "sum(area_ha) where tree_cover_loss_year = 2021 ; ref: sum(area_ha)",
        "#1 > #2 :: one year is more than all || one year is not more than all",
    )
    assert seen["sentence"] == "one year is not more than all"
    assert result["figure_claim_match_score"] == 1.0


# ----------------------------------------------------------------- the period


def test_answer_period_reads_the_period_and_maps_the_verdict(monkeypatch):
    seen = {}

    def judge(query, period, answer):
        seen["period"] = period
        return {"verdict": "fail", "reason": "it averaged 2001 to 2025"}

    monkeypatch.setattr("goldset.evaluators.llm_judges.llm_judge_answer_period", judge)
    state = {"messages": [SimpleNamespace(content="The average was 1.2 Mha.")]}
    result = evaluate_answer_period(state, "Average 2018-2022?", "2018-01-01", "2022-12-31")
    assert seen["period"] == "from 2018 to 2022"
    assert result["answer_period_match_score"] == 0.0
    open_ended = evaluate_answer_period(state, "Since 2021?", "2021-01-01", "")
    assert seen["period"] == "from 2021 to the latest data available"
    assert open_ended["answer_period_match_score"] == 0.0
    assert evaluate_answer_period(state, "q", "", "")["answer_period_match_score"] is None


def test_answer_period_not_applicable_scores_null(monkeypatch):
    monkeypatch.setattr(
        "goldset.evaluators.llm_judges.llm_judge_answer_period",
        lambda q, p, a: {"verdict": "not_applicable", "reason": "it declined"},
    )
    state = {"messages": [SimpleNamespace(content="I cannot answer that.")]}
    result = evaluate_answer_period(state, "q", "{run-14d}" and "2026-10-13", "2026-10-27", 3)
    assert result["answer_period_match_score"] is None


def test_a_zero_figure_may_be_stated_in_words(pulled):
    # Kayapó (BRA1507) returns no loss: "no loss was recorded" states it.
    empty_year = [{"aoi_id": "BRA1507", "tree_cover_loss_year": 2021, "area_ha": 0.0}]
    state, tables = _state("No loss was recorded in the territory in 2021.", empty_year)
    pulled(tables)
    assert evaluate_figures(state, "sum(area_ha)")["figure_match_score"] == 1.0

