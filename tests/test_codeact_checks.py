"""CodeAct checks: the chart route, and the chart's values against the pull."""

import pytest
from pydantic import ValidationError

from goldset.buckets import implied_checks
from goldset.eval_types import ExpectedData
from goldset.evaluators import figures
from goldset.evaluators.codeact_checks import (
    evaluate_chart_data,
    evaluate_chart_route,
    parse_chart_series,
    parse_series,
    validate,
)
from goldset.evaluators.figures import Aggregate, Condition, FigureError

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


# ------------------------------------------------------------- chart_data_match

TCL = [
    {"aoi_id": "PER.12", "tree_cover_loss_year": year, "area_ha": area}
    for year, area in [(2018, 100.0), (2019, 200.0), (2020, 300.0), (2021, 400.0)]
] + [{"aoi_id": "PER.23", "tree_cover_loss_year": 2020, "area_ha": 50.0}]

# Two days in May and one in June, three confidence levels each.
ALERTS = [
    {"aoi_id": "PER.26.3", "alert_date": day, "alert_confidence": level, "area_ha": area}
    for day, areas in [("2026-05-03", (1.0, 10.0, 5.0)), ("2026-05-20", (2.0, 20.0, 7.0)),
                       ("2026-06-11", (4.0, 40.0, 9.0))]
    for level, area in zip(("low", "high", "highest"), areas, strict=True)
]
MAY, JUNE = 45.0, 53.0

# Seven provinces, largest first.
PROVINCES = {f"IDN.{n}": (name, area) for n, (name, area) in enumerate(
    [("Riau", 700.0), ("Jambi", 600.0), ("Aceh", 500.0), ("Bali", 400.0),
     ("Papua", 300.0), ("Maluku", 200.0), ("Gorontalo", 100.0)], start=1)}
AREAS = [{"aoi_id": i, "area_ha": area} for i, (_name, area) in PROVINCES.items()]


def chart(rows, x="year", y="area_ha", kind="bar", **spec):
    return {"title": f"{kind} chart", "type": kind, "xAxis": x, "yAxis": y,
            "data": rows, **spec}


def state(charts, *tables, names=None, aois=()):
    urls = [f"https://analytics/{i}" for i in range(len(tables))]
    return (
        {"charts_data": charts, "codeact_parts": CODE,
         "statistics": [{"source_url": u, "aoi_id_to_name": names or {}} for u in urls],
         "aoi_selection": {"aois": list(aois)}},
        dict(zip(urls, tables, strict=True)),
    )


@pytest.fixture
def score(monkeypatch):
    """chart_data_match on a state, with tables served by URL, not fetched."""
    def run(series, charts, *tables, **context):
        agent_state, by_url = state(charts, *tables, **context)

        def fake(url):
            rows = by_url.get(url)
            if rows is None:
                return None
            columns = tuple(sorted({k for r in rows for k in r}))
            return columns, tuple(tuple(r.get(c) for c in columns) for r in rows)

        monkeypatch.setattr(figures, "_fetch", fake)
        return evaluate_chart_data(agent_state, series)
    return run


def yearly(values):
    return [{"year": year, "area_ha": value} for year, value in values.items()]


PER12 = "sum(area_ha) by tree_cover_loss_year where aoi_id = 'PER.12'"


def test_a_yearly_series_passes_in_any_year_form(score):
    for year in (int, str, float):
        rows = yearly({year(y): v for y, v in
                       [(2018, 100.0), (2019, 200.0), (2020, 300.0), (2021, 400.0)]})
        result = score(PER12, [chart(rows)], TCL)
        assert result["chart_data_match_score"] == 1.0, year
    assert "matches 'bar chart' (key year, value area_ha, scale 1)" in (
        result["chart_data_match_reason"])


def test_a_value_off_by_five_percent_fails(score):
    rows = yearly({2018: 100.0, 2019: 200.0, 2020: 315.0, 2021: 400.0})
    result = score(PER12, [chart(rows)], TCL)
    assert result["chart_data_match_score"] == 0.0
    assert "1 values off, worst error 5.0%" in result["chart_data_match_reason"]
    assert "expected {2018: 100, 2019: 200, 2020: 300, 2021: 400}" in (
        result["actual_chart_series"])


def test_a_missing_year_fails_and_rows_that_are_no_group_are_ignored(score):
    rows = yearly({2018: 100.0, 2019: 200.0, 2020: 300.0})
    result = score(PER12, [chart(rows)], TCL)
    assert result["chart_data_match_score"] == 0.0
    assert "missing 2021" in result["chart_data_match_reason"]
    rows = yearly({2018: 100.0, 2019: 200.0, 2020: 300.0, 2021: 400.0, "Total": 1000.0})
    assert score(PER12, [chart(rows)], TCL)["chart_data_match_score"] == 1.0


def test_a_wide_stacked_monthly_chart_matches_the_sum_of_its_series_fields(score):
    rows = [{"month": "2026-05", "low": 3.0, "high": 30.0, "highest": 12.0},
            {"month": "2026-06", "low": 4.0, "high": 40.0, "highest": 9.0}]
    wide = chart(rows, x="month", y="", kind="stacked-bar",
                 seriesFields=["low", "high", "highest"])
    result = score("sum(area_ha) by month(alert_date)", [wide], ALERTS)
    assert result["chart_data_match_score"] == 1.0
    assert "value sum of seriesFields" in result["chart_data_match_reason"]
    # One stack level is a value column of its own.
    high = "sum(area_ha) by month(alert_date) where alert_confidence = 'high'"
    assert score(high, [wide], ALERTS)["chart_data_match_score"] == 1.0


def test_a_long_stacked_chart_sums_the_rows_of_each_key(score):
    rows = [{"month": month, "confidence": level, "area_ha": area}
            for month, areas in [("May 2026", (3.0, 30.0, 12.0)), ("Jun 2026", (4.0, 40.0, 9.0))]
            for level, area in zip(("low", "high", "highest"), areas, strict=True)]
    long = chart(rows, x="month", kind="stacked-bar", stackField="confidence")
    assert score("sum(area_ha) by month(alert_date)", [long], ALERTS)[
        "chart_data_match_score"] == 1.0
    # A declared stack column is also read one value at a time.
    high = "sum(area_ha) by month(alert_date) where alert_confidence = 'high'"
    result = score(high, [long], ALERTS)
    assert result["chart_data_match_score"] == 1.0
    assert "where confidence = high" in result["chart_data_match_reason"]


@pytest.mark.parametrize("may", ["2026-05", "2026-05-01", "May 2026", "May-2026",
                                 "2026 May", "mayo 2026", "05/2026"])
def test_months_are_read_in_their_usual_forms(score, may):
    rows = [{"month": may, "area_ha": MAY}, {"month": "June 2026", "area_ha": JUNE}]
    assert score("sum(area_ha) by month(alert_date)", [chart(rows, x="month")], ALERTS)[
        "chart_data_match_score"] == 1.0


def test_a_daily_chart_is_not_a_monthly_series(score):
    days = {}
    for row in ALERTS:
        days[row["alert_date"]] = days.get(row["alert_date"], 0.0) + row["area_ha"]
    rows = [{"date": day, "area_ha": area} for day, area in days.items()]
    result = score("sum(area_ha) by month(alert_date)", [chart(rows, x="date")], ALERTS)
    assert result["chart_data_match_score"] == 0.0
    assert "several keys read as 2026-05" in result["chart_data_match_reason"]
    by_day = "sum(area_ha) by alert_date"
    assert score(by_day, [chart(rows, x="date")], ALERTS)["chart_data_match_score"] == 1.0


def _ranking(*ids):
    return [{"province": PROVINCES[i][0], "area_ha": PROVINCES[i][1]} for i in ids]


NAMES = {i: name for i, (name, _area) in PROVINCES.items()}


def test_top_five_passes_and_the_wrong_fifth_area_fails(score):
    top = "sum(area_ha) by aoi_id top 5"
    right = chart(_ranking("IDN.1", "IDN.2", "IDN.3", "IDN.4", "IDN.5"), x="province")
    assert score(top, [right], AREAS, names=NAMES)["chart_data_match_score"] == 1.0
    # Showing more areas than asked is fine while each value is right.
    longer = chart(_ranking(*PROVINCES), x="province")
    assert score(top, [longer], AREAS, names=NAMES)["chart_data_match_score"] == 1.0
    wrong = chart(_ranking("IDN.1", "IDN.2", "IDN.3", "IDN.4", "IDN.6"), x="province")
    result = score(top, [wrong], AREAS, names=NAMES)
    assert result["chart_data_match_score"] == 0.0
    assert "missing idn.5" in result["chart_data_match_reason"]


def test_a_group_whose_value_is_zero_may_be_left_out(score):
    # ch-codeact-025: the chart leaves out a department with no fire loss.
    every = "sum(area_ha) by aoi_id"
    table = [*AREAS, {"aoi_id": "IDN.8", "area_ha": 0.0}]
    names = {**NAMES, "IDN.8": "Lampung"}
    drawn = chart(_ranking(*PROVINCES), x="province")
    assert score(every, [drawn], table, names=names)["chart_data_match_score"] == 1.0
    # A group with a value is still required.
    short = chart(_ranking(*list(PROVINCES)[1:]), x="province")
    result = score(every, [short], table, names=names)
    assert result["chart_data_match_score"] == 0.0
    assert "missing idn.1" in result["chart_data_match_reason"]
    assert "idn.8" not in result["chart_data_match_reason"].split("missing")[1]
    # A chart that draws no group of an all-zero series is not that series.
    zeros = [{"aoi_id": "IDN.8", "area_ha": 0.0}, {"aoi_id": "IDN.9", "area_ha": 0.0}]
    elsewhere = chart([{"province": "Somewhere", "area_ha": 5.0}], x="province")
    assert score(every, [elsewhere], zeros)["chart_data_match_score"] == 0.0


def test_areas_match_by_id_name_or_name_with_an_admin_word(score):
    rows = [{"area": "IDN.1_1", "area_ha": 700.0}, {"area": "Jambi Province", "area_ha": 600.0},
            {"area": "aceh", "area_ha": 500.0}, {"area": "Bali", "area_ha": 400.0},
            {"area": "Papua", "area_ha": 300.0}]
    result = score("sum(area_ha) by aoi_id top 5", [chart(rows, x="area")], AREAS,
                   names=NAMES)
    assert result["chart_data_match_score"] == 1.0
    # The selected areas' names count too: the whole name or its first part.
    aois = [{"src_id": "PER.26.3_1", "name": "Padre Abad, Ucayali, Peru"}]
    rows = [{"name": "Padre Abad", "area_ha": MAY + JUNE}]
    assert score("sum(area_ha) by aoi_id", [chart(rows, x="name")], ALERTS, aois=aois)[
        "chart_data_match_score"] == 1.0


def test_para_is_not_parana(score):
    table = [{"aoi_id": "BRA.14", "area_ha": 900.0}, {"aoi_id": "BRA.18", "area_ha": 100.0}]
    names = {"BRA.14": "Pará", "BRA.18": "Paraná"}
    series = "sum(area_ha) by aoi_id"
    right = [{"state": "Para", "area_ha": 900.0}, {"state": "Paraná State", "area_ha": 100.0}]
    assert score(series, [chart(right, x="state")], table, names=names)[
        "chart_data_match_score"] == 1.0
    swapped = [{"state": "Paraná", "area_ha": 900.0}, {"state": "Pará", "area_ha": 100.0}]
    assert score(series, [chart(swapped, x="state")], table, names=names)[
        "chart_data_match_score"] == 0.0
    # No substring match: with only Pará named, "Paraná" is no group.
    only = [{"state": "Paraná", "area_ha": 900.0}]
    result = score(series, [chart(only, x="state")], table[:1], names={"BRA.14": "Pará"})
    assert result["chart_data_match_score"] == 0.0
    assert "missing bra.14" in result["chart_data_match_reason"]


def test_a_kha_chart_and_a_percent_share_pass(score):
    kha = yearly({2018: 0.1, 2019: 0.2, 2020: 0.3, 2021: 0.4})
    result = score(PER12, [chart(kha)], TCL)
    assert result["chart_data_match_score"] == 1.0
    assert "scale 1e-3" in result["chart_data_match_reason"]
    shares = [{"year": y, "share": s} for y, s in [(2018, 10.0), (2019, 20.0),
                                                   (2020, 30.0), (2021, 40.0)]]
    result = score(PER12, [chart(shares, y="share", kind="pie")], TCL)
    assert result["chart_data_match_score"] == 1.0
    assert "percent of total" in result["chart_data_match_reason"]


def test_the_rounding_a_chart_states_passes(score):
    # 0.36% shown as 0.4%: 11% off, but within the one decimal it states.
    table = [{"driver": "A", "area_ha": 99.64}, {"driver": "B", "area_ha": 0.36}]
    rows = [{"driver": "A", "pct": 99.6}, {"driver": "B", "pct": 0.4}]
    assert score("sum(area_ha) by driver", [chart(rows, x="driver", y="pct")], table)[
        "chart_data_match_score"] == 1.0
    rows = [{"driver": "A", "pct": 99.64}, {"driver": "B", "pct": 0.40}]
    assert score("sum(area_ha) by driver", [chart(rows, x="driver", y="pct")], table)[
        "chart_data_match_score"] == 0.0


def test_cumulative_is_the_running_sum_in_key_order(score):
    series = PER12 + " cumulative"
    running = yearly({2021: 1000.0, 2018: 100.0, 2019: 300.0, 2020: 600.0})
    assert score(series, [chart(running)], TCL)["chart_data_match_score"] == 1.0
    annual = yearly({2018: 100.0, 2019: 200.0, 2020: 300.0, 2021: 400.0})
    assert score(series, [chart(annual)], TCL)["chart_data_match_score"] == 0.0


def test_keys_fold_dashes_and_spaces(score):
    table = [{"period": "2000-2005", "area_ha": 10.0}, {"period": "2016-2020", "area_ha": 20.0}]
    # An en dash, and spaces round a hyphen, are folded away.
    rows = [{"period": "2000 - 2005", "area_ha": 10.0}, {"period": "2016\u20132020", "area_ha": 20.0}]
    assert score("sum(area_ha) by period", [chart(rows, x="period")], table)[
        "chart_data_match_score"] == 1.0


def test_series_must_all_match_and_alternatives_any(score):
    annual = chart(yearly({2018: 100.0, 2019: 200.0, 2020: 300.0, 2021: 400.0}))
    other = "sum(area_ha) by tree_cover_loss_year where aoi_id = 'PER.23'"
    assert score(f"{PER12} ; {other}", [annual], TCL)["chart_data_match_score"] == 0.0
    both = chart([{"year": 2020, "area_ha": 50.0}])
    assert score(f"{PER12} ; {other}", [annual, both], TCL)["chart_data_match_score"] == 1.0
    assert score(f"{other} | {PER12}", [annual], TCL)["chart_data_match_score"] == 1.0


def test_a_grouped_chart_is_read_one_group_at_a_time(score):
    rows = [{"year": y, "name": name, "area_ha": a}
            for y, name, a in [(2020, "PER.12", 300.0), (2020, "PER.23", 50.0),
                               (2021, "PER.12", 400.0)]]
    grouped = chart(rows, kind="grouped-bar", groupField="name")
    series = "sum(area_ha) by tree_cover_loss_year where aoi_id = 'PER.23'"
    assert score(series, [grouped], TCL)["chart_data_match_score"] == 1.0


def test_the_union_of_two_pulls_is_a_candidate(score):
    first, second = TCL[:2], TCL[2:4]
    rows = yearly({2018: 100.0, 2019: 200.0, 2020: 300.0, 2021: 400.0})
    assert score(PER12, [chart(rows)], first, second)["chart_data_match_score"] == 1.0


def test_no_chart_fails_and_no_series_abstains(score):
    result = score(PER12, [], TCL)
    assert result["chart_data_match_score"] == 0.0
    assert result["chart_data_match_reason"] == "no chart"
    assert score("", [chart(yearly({2018: 1.0}))], TCL)["chart_data_match_score"] is None


def test_a_series_the_pull_cannot_give_abstains(score):
    rows = yearly({2018: 100.0})
    result = score("sum(other_ha) by tree_cover_loss_year", [chart(rows)], TCL)
    assert result["chart_data_match_score"] is None
    assert "not computable from the pull (the table has no other_ha)" in (
        result["chart_data_match_reason"])
    result = score(PER12, [chart(rows)])
    assert result["chart_data_match_score"] is None
    assert result["chart_data_match_reason"] == "no pulled table could be read; abstained"
    not_dates = "sum(area_ha) by month(aoi_id)"
    assert score(not_dates, [chart(rows)], TCL)["chart_data_match_score"] is None


def test_the_grammar_reads_keys_flags_and_conditions():
    series = parse_series(
        "sum(area_ha) by month(alert_date) where alert_confidence in ('high', 'highest')"
        " and alert_date in 2026-04-01..2026-09-30"
    )
    assert (series.key, series.key_part, series.top, series.cumulative) == (
        "alert_date", "month", None, False)
    assert series.aggregate == Aggregate("sum", ("area_ha",), None, (
        Condition("alert_confidence", "in", ("high", "highest")),
        Condition("alert_date", "range", ("2026-04-01", "2026-09-30")),
    ))
    ranked = parse_series("max(area_ha) by aoi_id where year = 2024 top 10")
    assert (ranked.key, ranked.top, ranked.aggregate.func) == ("aoi_id", 10, "max")
    assert parse_series("sum(a) by year cumulative").cumulative
    assert [len(s) for s in parse_chart_series("sum(a) by x | sum(b) by x ; sum(a) by y")] == [2, 1]


@pytest.mark.parametrize("bad", [
    "sum(area_ha)",
    "sum(area_ha) by year by aoi_id",
    "total(area_ha) by year",
    "ratio(sum(a) by x, sum(b) by x)",
    "sum(area_ha) by year top 0",
    "sum(area_ha) by year top 3 cumulative",
    "sum(area_ha) by year when year = 2020",
    "sum(area_ha) by year top five",
])
def test_a_bad_series_fails_loudly(bad):
    with pytest.raises(FigureError):
        parse_chart_series(bad)
    assert validate({"chart_series": bad})[0].startswith("chart_series: ")


def test_areas_tied_at_the_top_n_line_are_fair_alternatives(score):
    table = [{"aoi_id": i, "area_ha": a} for i, a in
             [("IDN.1", 9.0), ("IDN.2", 5.0), ("IDN.3", 5.0), ("IDN.4", 1.0)]]
    names = {"IDN.1": "Riau", "IDN.2": "Jambi", "IDN.3": "Aceh", "IDN.4": "Bali"}
    for second in ("Jambi", "Aceh"):
        rows = [{"area": "Riau", "area_ha": 9.0}, {"area": second, "area_ha": 5.0}]
        assert score("sum(area_ha) by aoi_id top 2", [chart(rows, x="area")], table,
                     names=names)["chart_data_match_score"] == 1.0, second
    rows = [{"area": "Riau", "area_ha": 9.0}, {"area": "Bali", "area_ha": 1.0}]
    result = score("sum(area_ha) by aoi_id top 2", [chart(rows, x="area")], table,
                   names=names)
    assert result["chart_data_match_score"] == 0.0
    assert "missing 1 of ['idn.2', 'idn.3']" in result["chart_data_match_reason"]


def test_a_chart_too_coarse_for_the_series_does_not_pass_on_rounding(score):
    # 100 to 400 ha is 0.0001 to 0.0004 Mha: whole-number zeros say nothing.
    zeros = yearly({2018: 0, 2019: 0, 2020: 0, 2021: 0})
    assert score(PER12, [chart(zeros)], TCL)["chart_data_match_score"] == 0.0
