"""Numeric-fidelity checks (DR-PR11): the answer's numbers vs the thread's own data.

Field evidence (2026-08-28 dry runs, blocker 1 in both registers): asked to
quote four exact values from an analysis in its own thread, under an explicit
do-not-infer instruction, the agent fabricated all four, inverted the trend,
and invented a year the data does not hold. The newsroom re-run produced
publication-shaped prose claiming a 2021 peak of 1,412 ha (actual peak: 2014
at 646 ha), loss "consistently above 800 ha/yr since 2017" (actual range
288-464), and a rising trend on a series whose final value sits below its
first. Nothing in the suite compared the prose's figures to the thread's own
``charts_data``, so the behaviour was found twice in one day by hand.

Division of labour as in ``llm_judges.py``: the model only extracts — which
claims the prose makes, copied verbatim — and every verdict is computed here
in code against the chart data. ``answer_traceability`` checks the first
bolded headline figure; this check reads ALL numeric claims out of narrative
prose, ties each to the year/series it cites, and scores peak, threshold and
trend-direction assertions, so a confident wrong number tied to the wrong
year fails even when the same figure exists somewhere else in the data.

Tri-state per the working agreements. No charts, no prose, or no extracted
claims -> ``None`` (nothing to check — absence of numeric prose is not a
failure). Any contradicted claim -> ``0.0``. Every verifiable claim
supported -> ``1.0``. Claims the deterministic matcher cannot verify safely
(ambiguous locale decimals, an unresolvable multi-series trend) are skipped
with a recorded reason, never guessed. Both checks are born info-only
(``buckets.py``) until extraction shows std <= 0.10 over 3 trials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from goldset.evaluators.answer_evaluator import (
    _serialize_charts_json,
    extract_final_answer_text,
)
from goldset.evaluators.chart_numeric import (
    _NON_MEASURE_KEYS,
    chart_candidate_values,
    format_number,
    parse_expected_number,
)
from goldset.evaluators.llm_judges import NUMERIC_TOLERANCE
from goldset.models import HAIKU

# A trend claim needs this many points before a slope means anything.
_MIN_TREND_POINTS = 3

# Predicted change under 5% of the series' typical magnitude reads as flat:
# a claimed rise on a series that moved 2% over twenty years is neither
# confirmed nor refuted by the slope sign alone, so "stable" absorbs it.
_TREND_DEADBAND = 0.05

_YEAR_RE = re.compile(r"(19|20)\d{2}")


class NumericClaim(BaseModel):
    """One claim the prose makes about the analysed data. Extraction only —
    the model copies, and never computes; see the module docstring."""

    quote: str
    kind: str  # "value" | "peak" | "bound" | "trend"
    series: str = ""
    year: str = ""
    period_start: str = ""
    period_end: str = ""
    number: str = ""  # verbatim figure incl. sign/unit; "" for trend claims
    direction: str = ""  # trend only: "rising" | "falling" | "stable"
    bound_type: str = ""  # bound only: "above" | "below"


class ExtractedClaims(BaseModel):
    # reasoning precedes the claims: haiku commits to the first field it
    # emits and argues with itself otherwise (PR-04 F6)
    reasoning: str
    claims: list[NumericClaim]


# Free of `{}` except the single placeholder, so ChatPromptTemplate does not
# invent input variables (see test_numeric_fidelity's prompt hygiene tests).
EXTRACTOR_PROMPT = """
You are extracting numeric claims from an AI assistant's answer about
environmental analysis data. You extract only. Do not verify, compute,
convert, round, or judge any figure — every comparison happens later, in
code, against the analysis data itself.

ANSWER:
{answer_prose}

Extract every claim the answer makes about the analysed data, one entry per
claim, using these kinds:

- kind "value": a specific figure, e.g. "the district lost 16.29 hectares
  in 2020". Copy the figure into number exactly as written, keeping its
  sign, separators and unit. Set year to the 4-digit year the figure is
  tied to, or an empty string if none. Set series to the series, area, or
  category name the prose ties the figure to, or an empty string.
- kind "peak": a maximum-style claim, e.g. "loss peaked in 2021 at 1,412
  hectares". Set year to the claimed peak year and number to the claimed
  peak value, each an empty string if not stated.
- kind "bound": a claim that values stay above or below a threshold over a
  period, e.g. "consistently above 800 ha per year since 2017". Set
  bound_type to "above" or "below", number to the threshold as written, and
  period_start / period_end to the 4-digit years bounding the claim, empty
  string where open.
- kind "trend": a direction claim, e.g. "loss has been rising since 2017"
  or "the decline has flattened". Set direction to "rising", "falling", or
  "stable", period_start / period_end as for bound, and leave number empty.

Rules:
- quote is the verbatim fragment of the answer carrying the claim.
- Copy numbers verbatim. Never convert units or reformat separators.
- Dates that only describe the analysis window ("between 2001 and 2024",
  "data for 2015-2024") are not claims; skip them.
- Counts of things in the conversation itself ("2 datasets", "top 5") are
  not claims about the data; skip them.
- A number that restates the user's question is still a claim if the answer
  asserts it as true of the data.
- reasoning: one or two sentences on what you found, before the claims.
- If the answer makes no numeric claims, return an empty claims list.
"""


def extract_numeric_claims(prose: str) -> list[NumericClaim]:
    """LLM extraction pass. Raises on judge outage — the caller converts
    that to a judge_error, never to a verdict (PR-04 F4)."""
    prompt = ChatPromptTemplate.from_messages([("user", EXTRACTOR_PROMPT)])
    chain = prompt | HAIKU.with_structured_output(ExtractedClaims)
    extraction = chain.invoke({"answer_prose": prose})
    return extraction.claims


# ---------------------------------------------------------------------------
# Deterministic matching. Everything below is pure code over charts_data.


@dataclass(frozen=True)
class ClaimVerdict:
    claim: NumericClaim
    status: str  # "supported" | "unsupported" | "skipped"
    reason: str


def _record_sets(node: Any) -> list[list[dict[str, Any]]]:
    """Every list-of-records anywhere in the chart structure."""
    found: list[list[dict[str, Any]]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
            return
        if not isinstance(value, list):
            return
        records = [item for item in value if isinstance(item, dict)]
        if records:
            found.append(records)
        for item in value:
            walk(item)

    walk(node)
    return found


def _as_year(value: Any) -> int | None:
    match = _YEAR_RE.search(str(value)) if value is not None else None
    return int(match.group(0)) if match else None


def _year_key(records: list[dict[str, Any]]) -> str | None:
    """The key that holds the record's year, if the set is a time series."""
    keys = {key for record in records for key in record}
    for key in sorted(keys):
        values = [record[key] for record in records if key in record]
        years = [_as_year(v) for v in values]
        if values and all(year is not None for year in years):
            if key.lower() in _NON_MEASURE_KEYS or key.lower() in ("year", "years"):
                return key
    return None


def _measure_keys(records: list[dict[str, Any]], year_key: str | None) -> list[str]:
    keys = sorted({key for record in records for key in record})
    return [
        key
        for key in keys
        if key != year_key
        and key.lower() not in _NON_MEASURE_KEYS
        and any(
            isinstance(record.get(key), int | float)
            and not isinstance(record.get(key), bool)
            for record in records
        )
    ]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _series_matches(hint: str, name: str) -> bool:
    h, n = _norm(hint), _norm(name)
    return bool(h) and bool(n) and (h in n or n in h)


def _restrict(
    records: list[dict[str, Any]],
    measure_keys: list[str],
    series_hint: str,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Narrow records/columns to the claimed series when it resolves cleanly.

    A hint may name a measure column ("high confidence alerts") or a label
    value inside the rows (a custom-area name in a `name` column). When
    neither resolves, match against everything and say so in the reason —
    an unresolved hint must widen the candidate set, never fail the claim.
    """
    if not series_hint:
        return records, measure_keys, True
    matched_keys = [key for key in measure_keys if _series_matches(series_hint, key)]
    if matched_keys:
        return records, matched_keys, True
    matched_records = [
        record
        for record in records
        if any(
            isinstance(value, str) and _series_matches(series_hint, value)
            for value in record.values()
        )
    ]
    if matched_records:
        return matched_records, measure_keys, True
    return records, measure_keys, False


def _values_for_year(
    charts: list[dict[str, Any]],
    year: int,
    series_hint: str,
    is_percent: bool,
) -> tuple[list[float], bool, bool]:
    """Candidate figures tied to one year.

    Returns (candidates, saw_time_series, series_resolved). Candidates are
    the matching records' measure values, their per-record cross-column sums,
    and — for percent claims — each value as a share of its column total.
    """
    candidates: list[float] = []
    saw_time_series = False
    series_resolved = True
    for chart in charts:
        for records in _record_sets(chart):
            year_key = _year_key(records)
            if year_key is None:
                continue
            saw_time_series = True
            scoped, keys, resolved = _restrict(
                records, _measure_keys(records, year_key), series_hint
            )
            series_resolved = series_resolved and resolved
            hits = [r for r in scoped if _as_year(r.get(year_key)) == year]
            for record in hits:
                row: list[float] = []
                for key in keys:
                    value = record.get(key)
                    if isinstance(value, int | float) and not isinstance(value, bool):
                        row.append(float(value))
                        if is_percent:
                            total = sum(
                                float(r[key])
                                for r in records
                                if isinstance(r.get(key), int | float)
                                and not isinstance(r.get(key), bool)
                            )
                            if total:
                                candidates.append(float(value) / total * 100)
                candidates.extend(row)
                if len(row) >= 2:
                    candidates.append(sum(row))
    return candidates, saw_time_series, series_resolved


def _within(value: float, target: float) -> bool:
    return target != 0 and abs(value - target) / abs(target) <= NUMERIC_TOLERANCE


def _match_value(claim: NumericClaim, charts: list[dict[str, Any]]) -> ClaimVerdict:
    parsed = parse_expected_number(claim.number)
    if parsed is None:
        return ClaimVerdict(
            claim, "skipped", f'figure "{claim.number}" not safely parseable'
        )
    unit = "%" if parsed.is_percent else ""
    year = _as_year(claim.year)
    if year is not None:
        candidates, saw_time_series, resolved = _values_for_year(
            charts, year, claim.series, parsed.is_percent
        )
        if saw_time_series:
            if not candidates:
                return ClaimVerdict(
                    claim,
                    "unsupported",
                    f"the data holds no row for year {year}"
                    + (f' (series "{claim.series}")' if claim.series else ""),
                )
            closest = min(candidates, key=lambda v: abs(v - parsed.value))
            if _within(closest, parsed.value):
                return ClaimVerdict(
                    claim,
                    "supported",
                    f"{format_number(parsed.value)}{unit} for {year} matches "
                    f"{format_number(closest)}{unit} in the data",
                )
            note = "" if resolved else f' (series "{claim.series}" unresolved, matched all series)'
            return ClaimVerdict(
                claim,
                "unsupported",
                f"claimed {format_number(parsed.value)}{unit} for {year}; the "
                f"closest figure that year is {format_number(closest)}{unit}{note}",
            )
    # No usable year anywhere: any figure a reader could take from the charts.
    candidates = chart_candidate_values(
        _serialize_charts_json(charts), is_percent=parsed.is_percent
    )
    if not candidates:
        return ClaimVerdict(
            claim, "unsupported", "the chart data holds no figure to compare against"
        )
    closest = min(candidates, key=lambda v: abs(v - parsed.value))
    if _within(closest, parsed.value):
        return ClaimVerdict(
            claim,
            "supported",
            f"{format_number(parsed.value)}{unit} matches "
            f"{format_number(closest)}{unit} in the data",
        )
    return ClaimVerdict(
        claim,
        "unsupported",
        f"claimed {format_number(parsed.value)}{unit}; the closest figure in "
        f"the data is {format_number(closest)}{unit}",
    )


def _time_series_columns(
    charts: list[dict[str, Any]], series_hint: str
) -> tuple[list[tuple[str, list[tuple[int, float]]]], bool]:
    """Every (column name, [(year, value), ...]) series in the charts."""
    columns: list[tuple[str, list[tuple[int, float]]]] = []
    series_resolved = True
    for chart in charts:
        for records in _record_sets(chart):
            year_key = _year_key(records)
            if year_key is None:
                continue
            scoped, keys, resolved = _restrict(
                records, _measure_keys(records, year_key), series_hint
            )
            series_resolved = series_resolved and resolved
            for key in keys:
                points = sorted(
                    (
                        (_as_year(record.get(year_key)), float(record[key]))
                        for record in scoped
                        if _as_year(record.get(year_key)) is not None
                        and isinstance(record.get(key), int | float)
                        and not isinstance(record.get(key), bool)
                    ),
                )
                if points:
                    columns.append((key, points))
    return columns, series_resolved


def _match_peak(claim: NumericClaim, charts: list[dict[str, Any]]) -> ClaimVerdict:
    claimed_year = _as_year(claim.year)
    parsed = parse_expected_number(claim.number) if claim.number else None
    if claimed_year is None and parsed is None:
        return ClaimVerdict(claim, "skipped", "peak claim carries no year or figure")
    columns, _resolved = _time_series_columns(charts, claim.series)
    if not columns:
        return ClaimVerdict(claim, "skipped", "no time series in the data to rank")
    observed: list[str] = []
    for name, points in columns:
        peak_year, peak_value = max(points, key=lambda p: p[1])
        year_ok = claimed_year is None or peak_year == claimed_year
        value_ok = parsed is None or _within(peak_value, parsed.value)
        if year_ok and value_ok:
            return ClaimVerdict(
                claim,
                "supported",
                f'"{name}" peaks in {peak_year} at {format_number(peak_value)}',
            )
        observed.append(f'"{name}" peaks in {peak_year} at {format_number(peak_value)}')
    return ClaimVerdict(
        claim,
        "unsupported",
        "claimed peak"
        + (f" in {claimed_year}" if claimed_year else "")
        + (f" of {format_number(parsed.value)}" if parsed else "")
        + "; actually " + "; ".join(observed[:3]),
    )


def _period(claim: NumericClaim) -> tuple[int | None, int | None]:
    return _as_year(claim.period_start), _as_year(claim.period_end)


def _in_period(year: int, start: int | None, end: int | None) -> bool:
    return (start is None or year >= start) and (end is None or year <= end)


def _match_bound(claim: NumericClaim, charts: list[dict[str, Any]]) -> ClaimVerdict:
    parsed = parse_expected_number(claim.number)
    if parsed is None or claim.bound_type not in ("above", "below"):
        return ClaimVerdict(claim, "skipped", "threshold not safely parseable")
    columns, _resolved = _time_series_columns(charts, claim.series)
    start, end = _period(claim)
    observed: list[str] = []
    for name, points in columns:
        values = [v for year, v in points if _in_period(year, start, end)]
        if not values:
            continue
        if claim.bound_type == "above":
            ok = min(values) >= parsed.value * (1 - NUMERIC_TOLERANCE)
            edge = min(values)
        else:
            ok = max(values) <= parsed.value * (1 + NUMERIC_TOLERANCE)
            edge = max(values)
        if ok:
            return ClaimVerdict(
                claim,
                "supported",
                f'"{name}" stays {claim.bound_type} '
                f"{format_number(parsed.value)} in the period",
            )
        observed.append(
            f'"{name}" reaches {format_number(edge)}'
        )
    if not observed:
        return ClaimVerdict(claim, "skipped", "no time series covers the period")
    return ClaimVerdict(
        claim,
        "unsupported",
        f"claimed {claim.bound_type} {format_number(parsed.value)}; "
        + "; ".join(observed[:3]),
    )


def _slope(points: list[tuple[int, float]]) -> tuple[float, float] | None:
    """Least-squares (slope, relative predicted change over the span)."""
    if len(points) < _MIN_TREND_POINTS:
        return None
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    scale = sum(abs(y) for _, y in points) / n
    if denominator == 0 or scale == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
    span = max(x for x, _ in points) - min(x for x, _ in points)
    return slope, abs(slope * span) / scale


def trend_direction(points: list[tuple[int, float]]) -> str | None:
    """Least-squares slope direction, with a flatness deadband.

    None when fewer than ``_MIN_TREND_POINTS`` points or the series has no
    magnitude to compare against — a slope over two points is an anecdote.
    """
    stats = _slope(points)
    if stats is None:
        return None
    slope, relative_change = stats
    if relative_change < _TREND_DEADBAND:
        return "stable"
    return "rising" if slope > 0 else "falling"


def _direction_verdict(claimed: str, points: list[tuple[int, float]]) -> tuple[str, str] | None:
    """One column's verdict on a direction claim, or None if no slope.

    Only a DECISIVE contradiction fails: rising claimed on decisively
    falling data, or "stable" claimed on decisively moving data. Inside the
    flatness deadband a rising/falling claim whose sign matches the drift is
    a defensible description ("rose slightly"), so it passes — caught live
    on the first staging probe, where extent that drifted +0.8% over 22
    years was described as "rose" with both endpoints quoted exactly, and
    the deadband alone called that unsupported. A sign-opposing claim inside
    the deadband abstains: flat-plus-noise is not evidence either way.
    """
    stats = _slope(points)
    if stats is None:
        return None
    slope, _ = stats
    computed = trend_direction(points)
    if claimed == computed:
        return "supported", f"the data's direction is {computed}"
    if computed == "stable":
        drift = "rising" if slope > 0 else "falling"
        if claimed == drift:
            return (
                "supported",
                f"mild {drift} drift, within the flatness deadband",
            )
        return (
            "skipped",
            "flat within the deadband; direction claim not decidable",
        )
    return "unsupported", f"the data's direction is {computed}"


def _match_trend(claim: NumericClaim, charts: list[dict[str, Any]]) -> ClaimVerdict:
    if claim.direction not in ("rising", "falling", "stable"):
        return ClaimVerdict(claim, "skipped", f'direction "{claim.direction}" unknown')
    columns, resolved = _time_series_columns(charts, claim.series)
    start, end = _period(claim)
    votes: dict[str, tuple[str, str]] = {}
    for name, points in columns:
        scoped = [(year, v) for year, v in points if _in_period(year, start, end)]
        verdict = _direction_verdict(claim.direction, scoped)
        if verdict is not None:
            votes[name] = verdict
    decisive = {name: v for name, v in votes.items() if v[0] != "skipped"}
    if not decisive:
        return ClaimVerdict(
            claim,
            "skipped",
            "; ".join(detail for _, detail in votes.values())
            or "no time series long enough to carry a trend",
        )
    # A trend claim is about one series. A resolved hint has already scoped
    # the columns; unresolved across series with disagreeing verdicts,
    # attributing the claim would be a guess, so abstain rather than fail
    # (precision over recall).
    verdicts = {v[0] for v in decisive.values()}
    detail = "; ".join(
        f'"{name}": {d}' for name, (_, d) in sorted(decisive.items())[:4]
    )
    if len(verdicts) > 1 and not (claim.series and resolved):
        return ClaimVerdict(
            claim,
            "skipped",
            f"series disagree ({detail}) and the claim's series could not be resolved",
        )
    if "supported" in verdicts:
        return ClaimVerdict(claim, "supported", detail)
    return ClaimVerdict(claim, "unsupported", f"claimed {claim.direction}; {detail}")


_MATCHERS = {
    "value": _match_value,
    "peak": _match_peak,
    "bound": _match_bound,
    "trend": _match_trend,
}


def match_claims(
    claims: list[NumericClaim], charts: list[dict[str, Any]]
) -> list[ClaimVerdict]:
    """Deterministic verdict per claim. Unknown kinds are skipped, never
    guessed — a new extractor kind must land with its matcher."""
    verdicts = []
    for claim in claims:
        matcher = _MATCHERS.get(claim.kind)
        if matcher is None:
            verdicts.append(
                ClaimVerdict(claim, "skipped", f'unknown claim kind "{claim.kind}"')
            )
        else:
            verdicts.append(matcher(claim, charts))
    return verdicts


# ---------------------------------------------------------------------------
# The evaluator.


def _score(verdicts: list[ClaimVerdict]) -> tuple[float | None, str | None]:
    verifiable = [v for v in verdicts if v.status != "skipped"]
    if not verifiable:
        if verdicts:
            return None, (
                f"{len(verdicts)} claim(s) extracted, none verifiable: "
                + "; ".join(v.reason for v in verdicts[:3])
            )
        return None, None
    failing = [v for v in verifiable if v.status == "unsupported"]
    # Failing claims first: the reason column is trimmed to 500 chars in the
    # ledger and the contradiction is the part worth keeping.
    ordered = failing + [v for v in verifiable if v.status == "supported"]
    reason = "; ".join(f'"{v.claim.quote}" — {v.reason}' for v in ordered[:5])
    return (0.0 if failing else 1.0), reason


def evaluate_numeric_fidelity(agent_state: dict[str, Any]) -> dict[str, Any]:
    """Both fidelity checks from one extraction pass.

    ``numeric_fidelity`` scores value/peak/bound claims; ``trend_fidelity``
    scores direction claims. One LLM call serves both, and an extractor
    outage surfaces as a judge error on both, never as a verdict.
    """
    result: dict[str, Any] = {
        "numeric_fidelity_score": None,
        "numeric_fidelity_reason": None,
        "trend_fidelity_score": None,
        "trend_fidelity_reason": None,
        "actual_numeric_claims": None,
        "judge_errors": [],
    }
    charts = agent_state.get("charts_data") or []
    prose = extract_final_answer_text(agent_state.get("messages", []))
    if not charts or not prose:
        return result

    try:
        claims = extract_numeric_claims(prose)
    except Exception as error:  # extractor outage: error, never a verdict (F4)
        result["numeric_fidelity_reason"] = f"JUDGE ERROR: {error}"
        result["trend_fidelity_reason"] = f"JUDGE ERROR: {error}"
        result["judge_errors"] = ["numeric_fidelity", "trend_fidelity"]
        return result

    if not claims:
        result["numeric_fidelity_reason"] = "no numeric claims extracted"
        return result

    verdicts = match_claims(claims, charts)
    numeric = [v for v in verdicts if v.claim.kind != "trend"]
    trend = [v for v in verdicts if v.claim.kind == "trend"]
    result["numeric_fidelity_score"], result["numeric_fidelity_reason"] = _score(
        numeric
    )
    result["trend_fidelity_score"], result["trend_fidelity_reason"] = _score(trend)
    result["actual_numeric_claims"] = "; ".join(
        f'[{v.status}] "{v.claim.quote}"' for v in verdicts
    )
    return result
