"""Output-bucket checks, both deterministic.

``chart_well_formed`` needs no expectation: it fails a chart whose data is empty
or whose axis fields name keys absent from the data, since that renders badly
whatever the analysis computed. Two layouts exist: long format (``yAxis`` is a
data key) and wide format, where a non-empty ``seriesFields`` lists the data
columns the FE draws as series and ``yAxis`` is only a label, so the series
columns are checked instead of ``yAxis``. It overlaps ``chart_integrity`` on purpose: a
broken *spec* is an Output failure, a mis-joined *dataset* under a plausible
spec is an Analysis failure, and the two reasons read differently.

``chart_type_match`` compares the first chart's type with the case's
``chart_type`` expectation (``;``-separated alternatives).
"""

from __future__ import annotations

from typing import Any


def evaluate_chart_well_formed(agent_state: dict[str, Any]) -> dict[str, Any]:
    charts = agent_state.get("charts_data") or []
    result: dict[str, Any] = {
        "chart_well_formed_score": None,
        "chart_well_formed_reason": None,
        "actual_max_pie_slices": None,
    }
    if not charts:
        return result

    problems = []
    max_pie_slices = 0
    for index, chart in enumerate(charts):
        if not isinstance(chart, dict):
            problems.append(f"chart {index}: not an object")
            continue
        label = f"chart {index} ({chart.get('type', '?')})"
        data = chart.get("data")
        records = [row for row in data if isinstance(row, dict)] if isinstance(
            data, list
        ) else []
        if not records:
            problems.append(f"{label}: empty data")
            continue
        # The FE's table widget renders only the records and the title, so a
        # table's axis fields are never drawn (AJ, 2026-10-28, ch-quant-157).
        if chart.get("type") == "table":
            continue
        keys = {key for record in records for key in record}
        series = chart.get("seriesFields")
        wide = series is not None and series != []
        # Wide format: the FE draws one series per seriesFields column and uses
        # yAxis only as a label (ChartWidget.tsx), so yAxis need not be a key.
        axes = ("xAxis",) if wide else ("xAxis", "yAxis")
        for axis in axes:
            field = chart.get(axis)
            if isinstance(field, str) and field and field not in keys:
                problems.append(
                    f"{label}: {axis} references field {field!r} absent from data"
                )
        if wide:
            if not isinstance(series, list) or not all(
                isinstance(name, str) and name for name in series
            ):
                problems.append(f"{label}: seriesFields is not a list of field names")
            else:
                problems.extend(
                    f"{label}: seriesFields references field {name!r} absent from data"
                    for name in series
                    if name not in keys
                )
        if chart.get("type") == "pie":
            max_pie_slices = max(max_pie_slices, len(records))

    result["chart_well_formed_score"] = 0.0 if problems else 1.0
    if problems:
        result["chart_well_formed_reason"] = "; ".join(problems)
    if max_pie_slices:
        # info-only for now: surfaced for triage, thresholded later if noisy
        result["actual_max_pie_slices"] = max_pie_slices
    return result


def evaluate_chart_type(
    agent_state: dict[str, Any], expected_chart_type: str
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "chart_type_match_score": None,
        "actual_chart_type": None,
    }
    if not expected_chart_type:
        return result

    charts = agent_state.get("charts_data") or []
    first = charts[0] if charts and isinstance(charts[0], dict) else None
    actual = str(first.get("type", "")) if first is not None else ""
    result["actual_chart_type"] = actual or None
    if not actual:
        # a chart-type expectation implies a chart; none is a failure
        result["chart_type_match_score"] = 0.0
        return result
    alternatives = {
        alt.strip().lower() for alt in expected_chart_type.split(";") if alt.strip()
    }
    result["chart_type_match_score"] = 1.0 if actual.lower() in alternatives else 0.0
    return result
