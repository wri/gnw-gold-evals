"""Analysis checks for CodeAct answers, both deterministic.

Production draws a curated chart when one fits the pull, and runs CodeAct
(the code executor) only when none fits (project-zeno #910, #924). Some
questions must go through CodeAct: derived figures, another time step or
chart form, rankings of areas, and datasets with no curated view. A curated
chart on such a question is a routing failure (AJ, 2026-11-17).

``chart_route_match`` compares the route of the attempt with the case's
``chart_route`` (``codeact`` or ``curated``). The route comes from the final
agent state: ``codeact`` when ``codeact_parts`` is not empty and there is a
chart, ``curated`` when there is a chart and ``codeact_parts`` is empty, and
``none`` when there is no chart. In the production run 20261120T172336Z_prod
this rule agreed with every chart: each curated chart had no code parts and
an insight that starts "Standard", and no CodeAct chart did. A route
expectation implies a chart, so ``none`` fails, as in ``chart_type_match``.

``chart_data_match`` recomputes the chart's values from the tables the agent
pulled, as ``figure_match`` does for the reply, so generated code that draws
wrong bars fails. The case names the series with a formula
(``chart_series``), never with values:

    AGG(EXPR) by KEY [where COND [and COND]...] [top N] [cumulative]

AGG, EXPR and COND are as in ``figure`` (``figures.py``). Here ``by`` means
one value per group: AGG runs within each group of KEY and gives
``{key: value}``. In ``figure`` the same word sums per group and then
aggregates across the groups. KEY is a column, ``month(COL)`` (the date
column as ``YYYY-MM``) or ``year(COL)``. ``top N`` keeps the N groups with
the largest values; ``cumulative`` gives the running sum in key order. The
two do not combine. ``;`` separates series that must all match (two charts
in one turn); ``|`` separates fair alternatives, any one of which passes.

The expected series is computed on each pulled table and on their union, as
``figures.candidates`` does. Every chart is then read every way it can be:
each column as the key, each numeric column (and the sum of ``seriesFields``,
for wide stacked bars) as the value, and the rows of each value of a
declared ``groupField``, ``stackField`` or ``colorField`` on their own (long
grouped bars). Rows with the same key are summed (long format). Keys are
compared after folding case, accents, dashes and spaces; years, months and
area names are read in their usual forms (``_resolver``). A chart matches
when every expected key is in it and every row whose key is a group of the
series is within ``figures.TOLERANCE`` (or the rounding the chart states) of
the expected value times one scale: a unit change (1, 1e-3, 1e3, 1e-6, 1e6)
or a share of the total over all groups (100 / total, 1 / total). A key the
chart leaves out reads as 0, so a group whose value is 0 may be missing, as
long as the chart draws some group of the series. Rows whose key is no group
("Other", "Total") are ignored.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from goldset.evaluators.chart_numeric import format_number
from goldset.evaluators.figures import (
    _AGGREGATE,
    TOLERANCE,
    Aggregate,
    FigureError,
    _aggregate,
    _matches,
    _NotComputable,
    _row_value,
    _split_top,
    _union,
    pulled_tables,
)
from goldset.evaluators.utils import normalize_gadm_id

ROUTES = ("codeact", "curated")


def require_route(value: str) -> str:
    """The case's ``chart_route``; anything but a known route is a case error."""
    route = (value or "").strip()
    if route not in ROUTES:
        raise ValueError(f"chart_route must be one of {ROUTES}, got {value!r}")
    return route


def chart_route(agent_state: dict[str, Any]) -> str:
    """``codeact``, ``curated`` or ``none`` (no chart)."""
    if not agent_state.get("charts_data"):
        return "none"
    return "codeact" if agent_state.get("codeact_parts") else "curated"


def evaluate_chart_route(
    agent_state: dict[str, Any], expected_chart_route: str
) -> dict[str, Any]:
    """chart_route_match: the attempt took the expected chart route.

    ``null`` when the case sets no ``chart_route``. ``0.0`` when the route
    differs, including no chart at all. ``1.0`` when it is the same.
    """
    result: dict[str, Any] = {
        "chart_route_match_score": None,
        "chart_route_match_reason": None,
        "actual_chart_route": None,
    }
    if not expected_chart_route:
        return result
    expected = require_route(expected_chart_route)
    actual = chart_route(agent_state)
    charts = len(agent_state.get("charts_data") or [])
    parts = len(agent_state.get("codeact_parts") or [])
    result["actual_chart_route"] = actual
    result["chart_route_match_score"] = 1.0 if actual == expected else 0.0
    result["chart_route_match_reason"] = (
        f"expected {expected}, got {actual} ({charts} charts, {parts} code parts)"
    )
    return result


def validate(expected: dict[str, str]) -> list[str]:
    """Problems with a case's chart fields, for tools/check.py."""
    problems = []
    if expected.get("chart_route"):
        try:
            require_route(expected["chart_route"])
        except ValueError as error:
            problems.append(str(error))
    try:
        parse_chart_series(expected.get("chart_series") or "")
    except FigureError as error:
        problems.append(f"chart_series: {error}")
    return problems


# ------------------------------------------------------- the series grammar


@dataclass(frozen=True)
class Series:
    text: str
    aggregate: Aggregate  # its ``by`` is always None: the groups come from key
    key: str
    key_part: str | None = None  # "month" or "year" of a date column
    top: int | None = None
    cumulative: bool = False


_TAIL = re.compile(r"^(.*?)(?:\s+top\s+(\d+))?(\s+cumulative)?\s*$", re.S)
_SERIES_BY = re.compile(r"\bby\s+(?:(month|year)\(\s*(\w+)\s*\)|(\w+))")


def parse_series(text: str) -> Series:
    """One series; raises FigureError on any mistake."""
    tail = _TAIL.match(text.strip())
    body = tail[1].strip() if tail else ""
    m = _AGGREGATE.match(body)
    if not m:
        raise FigureError(f"expected AGG(column) by KEY: {text!r}")
    head, rest = body[: m.start(3)], m[3]
    keys = list(_SERIES_BY.finditer(rest))
    if len(keys) != 1:
        raise FigureError(f"a series needs exactly one 'by KEY': {text!r}")
    key = keys[0]
    rest = " ".join((rest[: key.start()] + " " + rest[key.end():]).split())
    aggregate = _aggregate(f"{head} {rest}".strip())
    top = int(tail[2]) if tail[2] else None
    cumulative = bool(tail[3])
    if top is not None and top < 1:
        raise FigureError(f"top N needs N of at least 1: {text!r}")
    if top is not None and cumulative:
        raise FigureError(f"top and cumulative do not combine: {text!r}")
    return Series(
        text=text.strip(),
        aggregate=aggregate,
        key=key[2] or key[3],
        key_part=key[1],
        top=top,
        cumulative=cumulative,
    )


def parse_chart_series(text: str) -> list[tuple[Series, ...]]:
    """A case's ``chart_series``: all-of ``;``, each with ``|`` alternatives."""
    parsed = []
    for part in _split_top(text or "", ";"):
        if not part:
            continue
        alternatives = tuple(parse_series(a) for a in _split_top(part, "|") if a)
        if not alternatives:
            raise FigureError(f"empty series in {text!r}")
        parsed.append(alternatives)
    return parsed


# ------------------------------------------------------------------ the keys

# En dash, em dash and minus sign read as a hyphen: "2016\u20132020" is "2016-2020".
_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"})
_NUMERIC = re.compile(r"-?\d+(?:\.\d+)?")


def _number_text(value: float) -> str:
    return str(int(value)) if value.is_integer() else repr(value)


def _text_key(value: Any) -> str:
    """A key as text: case, accents, dashes and spaces folded; a whole number
    in any form (``2020``, ``"2020"``, ``2020.0``) as its digits."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number_text(float(value)) if math.isfinite(value) else str(value)
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s*-\s*", "-", text.translate(_DASHES))
    text = " ".join(text.split()).casefold()
    return _number_text(float(text)) if _NUMERIC.fullmatch(text) else text


_MONTH_WORDS = {
    1: "january jan enero ene januari",
    2: "february feb febrero februari",
    3: "march mar marzo maret",
    4: "april apr abril abr",
    5: "may mayo mei",
    6: "june jun junio juni",
    7: "july jul julio juli",
    8: "august aug agosto ago agustus agu agt",
    9: "september sep sept septiembre setiembre",
    10: "october oct octubre oktober okt",
    11: "november nov noviembre",
    12: "december dec diciembre dic desember des",
}
_MONTHS = {word: n for n, words in _MONTH_WORDS.items() for word in words.split()}
_ISO_MONTH = re.compile(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?(?:[t ].*)?")
_MONTH_YEAR = re.compile(r"(\d{1,2})[-/](\d{4})")
_NAME_YEAR = re.compile(r"([a-z]+)\.?[ ,/-]*(\d{4})")
_YEAR_NAME = re.compile(r"(\d{4})[ ,/-]*([a-z]+)\.?")
_YEAR = re.compile(r"(\d{4})(?:-\d{1,2}(?:-\d{1,2})?(?:[t ].*)?)?")


def _month_key(value: Any) -> str | None:
    """``YYYY-MM`` for a date or month in its usual forms, else None."""
    text = _text_key(value)
    year = month = None
    if m := _ISO_MONTH.fullmatch(text):
        year, month = m[1], int(m[2])
    elif m := _MONTH_YEAR.fullmatch(text):
        year, month = m[2], int(m[1])
    elif m := _NAME_YEAR.fullmatch(text):
        year, month = m[2], _MONTHS.get(m[1])
    elif m := _YEAR_NAME.fullmatch(text):
        year, month = m[1], _MONTHS.get(m[2])
    if year and month and 1 <= month <= 12:
        return f"{year}-{month:02d}"
    return None


def _year_key(value: Any) -> str | None:
    """``YYYY`` for a year or a date, else None."""
    m = _YEAR.fullmatch(_text_key(value))
    return m[1] if m else None


_ADMIN_WORD = re.compile(
    r"(.+?)\s+(region|province|district|department|state|municipality|county"
    r"|prefecture)"
)
_ID_SHAPE = re.compile(r"[a-z]{3}(?:\.\d+)*(?:_\d+)?|\d+")


def _without_admin_word(text: str) -> str:
    m = _ADMIN_WORD.fullmatch(text)
    return m[1] if m else text


def _id_key(value: Any) -> str:
    """An area id as ``aoi_id_match`` reads it: no GADM ``_1`` suffix."""
    return normalize_gadm_id(str(value).strip())


def _area_aliases(agent_state: dict[str, Any]) -> dict[str, set[str]]:
    """Area id -> the names the agent knows it by, all folded as keys.

    Names come from each statistics entry's ``aoi_id_to_name`` and from the
    selected areas (the whole name and its first segment). A name with a
    trailing admin word ("Riau Province") also counts without it.
    """
    names: dict[str, set[str]] = {}

    def add(aoi_id: Any, name: Any) -> None:
        if not aoi_id or not name:
            return
        text = _text_key(name)
        names.setdefault(_id_key(aoi_id), set()).update(
            {text, _without_admin_word(text)}
        )

    statistics = agent_state.get("statistics") or []
    if isinstance(statistics, dict):
        statistics = [statistics]
    for entry in statistics:
        mapping = entry.get("aoi_id_to_name") if isinstance(entry, dict) else None
        for aoi_id, name in (mapping or {}).items():
            add(aoi_id, name)
    selection = agent_state.get("aoi_selection") or {}
    aois = selection.get("aois") if isinstance(selection, dict) else None
    for aoi in aois or []:
        if isinstance(aoi, dict):
            name = str(aoi.get("name") or "")
            add(aoi.get("src_id"), name)
            add(aoi.get("src_id"), name.split(",")[0])
    return names


def _resolver(
    series: Series, aliases: dict[str, set[str]]
) -> Callable[[Any], str]:
    """How a key in a table or a chart becomes a group of ``series``."""
    if series.key_part == "month":
        return lambda value: _month_key(value) or _text_key(value)
    if series.key_part == "year":
        return lambda value: _year_key(value) or _text_key(value)
    if series.key != "aoi_id":
        return _text_key
    # An area by its id or any of its names, whole words only: "Pará" must
    # not match "Paraná". A name two areas share names neither.
    owners: dict[str, set[str]] = {}
    for aoi_id, area_names in aliases.items():
        for alias in {aoi_id, *area_names}:
            owners.setdefault(alias, set()).add(aoi_id)

    def resolve(value: Any) -> str:
        text = _text_key(value)
        tries = [text, _without_admin_word(text)]
        if _ID_SHAPE.fullmatch(text):
            tries.insert(0, _id_key(text))
        for alias in tries:
            if len(owners.get(alias, ())) == 1:
                return next(iter(owners[alias]))
        return _id_key(text) if _ID_SHAPE.fullmatch(text) else text

    return resolve


# -------------------------------------------------------- the expected series


@dataclass(frozen=True)
class Expected:
    values: dict[str, float]  # every group, in key order
    required: frozenset[str]  # the groups the chart must show
    tied: frozenset[str] = frozenset()  # top N ties: ``need`` of them must show
    need: int = 0
    total: float = 0.0  # over every group, before top N


def _key_order(key: str) -> tuple[int, float, str]:
    return (0, float(key), key) if _NUMERIC.fullmatch(key) else (1, 0.0, key)


def _aggregate_values(func: str, values: list[float]) -> float:
    if func == "count":
        return float(len(values))
    if func == "sum":
        return float(sum(values))
    if func == "mean":
        return sum(values) / len(values)
    return max(values) if func == "max" else min(values)


def expected_series(
    series: Series, rows: list[dict[str, Any]], aliases: dict[str, set[str]]
) -> Expected:
    """The series on ``rows``; raises _NotComputable."""
    agg = series.aggregate
    if not rows:
        raise _NotComputable("no rows pulled")
    needed = set(agg.columns) | {c.column for c in agg.conditions} | {series.key}
    present = set().union(*(row.keys() for row in rows))
    if not needed <= present:
        raise _NotComputable(f"the table has no {', '.join(sorted(needed - present))}")
    group = _resolver(series, aliases) if series.key_part is None else None
    groups: dict[str, list[float]] = {}
    for row in rows:
        if not all(_matches(row, c) for c in agg.conditions):
            continue
        raw = row.get(series.key)
        value = _row_value(row, agg.columns)
        if raw is None or value is None:
            continue
        if group is not None:
            key = group(raw)
        else:
            reader = _month_key if series.key_part == "month" else _year_key
            key = reader(raw)
            if key is None:
                raise _NotComputable(f"{series.key} value {raw!r} is not a date")
        groups.setdefault(key, []).append(value)
    if not groups:
        raise _NotComputable("no rows match")
    values = {
        k: _aggregate_values(agg.func, groups[k]) for k in sorted(groups, key=_key_order)
    }
    total = sum(values.values())
    if series.cumulative:
        running = 0.0
        for k in values:
            running += values[k]
            values[k] = running
    if series.top is None or series.top >= len(values):
        return Expected(values, frozenset(values), total=total)
    # The Nth largest value draws the line; groups tied with it are fair
    # alternatives for the last places.
    line = sorted(values.values(), reverse=True)[series.top - 1]
    required = frozenset(k for k, v in values.items() if v > line)
    tied = frozenset(k for k, v in values.items() if v == line)
    need = series.top - len(required)
    if len(tied) == need:  # no tie at the line: every one of them is required
        return Expected(values, required | tied, total=total)
    return Expected(values, required, tied, need, total)


def expected_candidates(
    series: Series, tables: list[list[dict[str, Any]]], aliases: dict[str, set[str]]
) -> tuple[list[Expected], str]:
    """The series on each table and on their union, and why none computed."""
    found: list[Expected] = []
    why = "no pulled table"
    for rows in [*tables, _union(tables)] if len(tables) > 1 else tables:
        try:
            computed = expected_series(series, rows, aliases)
        except _NotComputable as error:
            why = str(error)
            continue
        if computed not in found:
            found.append(computed)
    return found, why


# ------------------------------------------------------------ the chart side


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _decimals(value: Any) -> int:
    """Decimal places a chart value states (``2806.06`` states 2)."""
    if isinstance(value, int):
        return 0
    exponent = Decimal(repr(value)).normalize().as_tuple().exponent
    return min(max(0, -exponent), 12) if isinstance(exponent, int) else 12


@dataclass(frozen=True)
class _View:
    """One way to read a chart: its key column, and a value per row."""

    title: str
    key: str
    value: str  # a label for the evidence
    rows: tuple[tuple[Any, float], ...]  # (raw key, value)
    precision: float  # half the last decimal place the chart states


def _views(chart: dict[str, Any]) -> list[_View]:
    records = [r for r in chart.get("data") or [] if isinstance(r, dict)]
    columns = list(dict.fromkeys(k for r in records for k in r))
    numeric = [c for c in columns if any(_number(r.get(c)) is not None for r in records)]
    fields = chart.get("seriesFields")
    fields = (
        [f for f in fields if isinstance(f, str) and f in columns]
        if isinstance(fields, list) else []
    )
    title = str(chart.get("title") or chart.get("type") or "chart")
    subsets: list[tuple[str | None, str, list[dict[str, Any]]]] = [(None, "", records)]
    for name in ("groupField", "stackField", "colorField"):
        split = chart.get(name)
        if isinstance(split, str) and split in columns:
            for shown in dict.fromkeys(_text_key(r.get(split)) for r in records):
                subset = [r for r in records if _text_key(r.get(split)) == shown]
                subsets.append((split, f" where {split} = {shown}", subset))
    views: list[_View] = []
    for split, where, rows in subsets:
        for key in columns:
            if key == split:
                continue
            for value in numeric:
                if value in (key, split):
                    continue
                pairs = tuple(
                    (r[key], number) for r in rows
                    if r.get(key) is not None and (number := _number(r.get(value))) is not None
                )
                stated = max((_decimals(r.get(value)) for r in rows
                              if _number(r.get(value)) is not None), default=12)
                views.append(_View(title, key, value + where, pairs, 0.5 * 10.0 ** -stated))
            if len(fields) >= 2 and key not in fields and key != split:
                # Wide stacked bars: the FE draws each field; a missing one is 0.
                pairs = tuple(
                    (r[key], sum(_number(r.get(f)) or 0.0 for f in fields))
                    for r in rows if r.get(key) is not None
                )
                stated = max((_decimals(r.get(f)) for r in rows for f in fields
                              if _number(r.get(f)) is not None), default=12)
                views.append(_View(title, key, "sum of seriesFields" + where, pairs,
                                   0.5 * 10.0 ** -stated * len(fields)))
    return views


@dataclass
class _Attempt:
    view: _View
    scale: str
    missing: list[str] = field(default_factory=list)
    wrong: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    worst: float = 0.0

    @property
    def matched(self) -> bool:
        return not self.missing and not self.wrong and not self.merged

    def rank(self) -> tuple[int, int, float]:
        return (len(self.missing), len(self.wrong) + len(self.merged), self.worst)

    def describe(self) -> str:
        text = (f"'{self.view.title[:60]}' (key {self.view.key}, "
                f"value {self.view.value}, {self.scale})")
        if self.missing:
            text += f": missing {', '.join(self.missing[:5])}"
            if len(self.missing) > 5:
                text += f" (+{len(self.missing) - 5} more)"
        if self.merged:
            text += f"; several keys read as {', '.join(self.merged[:5])}"
        if self.wrong:
            text += f"; {len(self.wrong)} values off, worst error {self.worst:.1%}"
        return text


def _scales(expected: Expected) -> list[tuple[float, str]]:
    scales = [(1.0, "scale 1"), (1e-3, "scale 1e-3"), (1e3, "scale 1e3"),
              (1e-6, "scale 1e-6"), (1e6, "scale 1e6")]
    if expected.total:
        scales += [(100.0 / expected.total, "percent of total"),
                   (1.0 / expected.total, "share of total")]
    return scales


def _read(
    view: _View, resolve: Callable[[Any], str]
) -> tuple[dict[str, float], dict[str, set[str]]]:
    """The view's value per group, summed over repeated keys, and the keys
    that read as each group."""
    shown: dict[str, float] = {}
    raw_keys: dict[str, set[str]] = {}
    for raw, value in view.rows:
        group = resolve(raw)
        shown[group] = shown.get(group, 0.0) + value
        raw_keys.setdefault(group, set()).add(_text_key(raw))
    return shown, raw_keys


def _attempt(
    view: _View, read: tuple[dict[str, float], dict[str, set[str]]],
    expected: Expected, scale: float, label: str,
) -> _Attempt:
    shown, raw_keys = read
    # The rounding the chart states passes ("0.4%" for 0.36%), unless it is
    # too coarse for the series: a chart of zeros is not 300 ha in Mha.
    largest = max(abs(v) for v in expected.values.values()) * abs(scale)
    floor = view.precision if view.precision * 10 <= largest else 0.0
    attempt = _Attempt(view, label)

    def close(value: float, target: float) -> bool:
        return abs(value - target) <= max(TOLERANCE * abs(target), floor)

    # A group the chart leaves out reads as 0, so a group whose value is 0
    # need not be drawn: a department with no fire loss (ch-codeact-025,
    # BOL.7). The chart must still draw some group of the series.
    drawn = any(k in shown for k in expected.values)
    attempt.missing = [
        k for k in expected.values
        if k in expected.required and k not in shown
        and not (drawn and close(0.0, expected.values[k] * scale))
    ]
    tied_shown = sum(1 for k in expected.tied if k in shown)
    if tied_shown < expected.need:
        attempt.missing.append(f"{expected.need - tied_shown} of {sorted(expected.tied)}")
    for group, value in shown.items():
        if group not in expected.values:
            continue  # "Other", "Total": not a group of the series
        if len(raw_keys[group]) > 1:
            # Two keys read as one group (days as a month): not this series.
            attempt.merged.append(group)
            continue
        target = expected.values[group] * scale
        if close(value, target):
            continue
        attempt.wrong.append(group)
        error = abs(value - target) / abs(target) if target else math.inf
        attempt.worst = max(attempt.worst, error)
    return attempt


@dataclass
class SeriesResult:
    alternatives: tuple[Series, ...]
    expected: Expected | None = None
    matched: _Attempt | None = None
    closest: _Attempt | None = None
    why: str = ""


def check_series(
    alternatives: tuple[Series, ...],
    tables: list[list[dict[str, Any]]],
    charts: list[dict[str, Any]],
    aliases: dict[str, set[str]],
) -> SeriesResult:
    """The first chart reading that matches any alternative, else the closest."""
    result = SeriesResult(alternatives)
    views = [view for chart in charts for view in _views(chart)]
    for series in alternatives:
        found, why = expected_candidates(series, tables, aliases)
        result.why = result.why or why
        resolve = _resolver(series, aliases)
        for expected in found:
            result.expected = result.expected or expected
            for view in views:
                read = _read(view, resolve)
                for scale, label in _scales(expected):
                    attempt = _attempt(view, read, expected, scale, label)
                    if attempt.matched:
                        result.matched = attempt
                        return result
                    if result.closest is None or attempt.rank() < result.closest.rank():
                        result.closest = attempt
    return result


def _series_values(expected: Expected) -> str:
    shown = [f"{k}: {format_number(v)}" for k, v in list(expected.values.items())[:30]]
    more = len(expected.values) - 30
    return "{" + ", ".join(shown) + (f", +{more} more" if more > 0 else "") + "}"


def evaluate_chart_data(
    agent_state: dict[str, Any], expected_chart_series: str
) -> dict[str, Any]:
    """chart_data_match: a chart draws each asked series, computed from the pull.

    ``null`` when the case sets no ``chart_series``, or no asked series can
    be computed from what was pulled (nothing pulled, a table that cannot be
    read, a column it lacks). ``0.0`` when there is no chart (a series
    expectation implies one) or a computable series matches no chart.
    ``1.0`` when every computable series matches a chart.
    """
    result: dict[str, Any] = {
        "chart_data_match_score": None,
        "chart_data_match_reason": None,
        "actual_chart_series": None,
    }
    asked = parse_chart_series(expected_chart_series)
    if not asked:
        return result
    if not agent_state.get("charts_data"):
        result["chart_data_match_score"] = 0.0
        result["chart_data_match_reason"] = result["actual_chart_series"] = "no chart"
        return result
    tables = pulled_tables(agent_state)
    if not tables:
        result["chart_data_match_reason"] = "no pulled table could be read; abstained"
        return result
    charts = [c for c in agent_state["charts_data"] if isinstance(c, dict)]
    aliases = _area_aliases(agent_state)
    reasons, details, scored, missed = [], [], 0, 0
    for number, alternatives in enumerate(asked, start=1):
        checked = check_series(alternatives, tables, charts, aliases)
        name = f"#{number} {' | '.join(s.text for s in alternatives)}"
        if checked.expected is None:
            reasons.append(f"{name}: not computable from the pull ({checked.why})")
            details.append(reasons[-1])
            continue
        scored += 1
        values = _series_values(checked.expected)
        if checked.matched:
            line = f"{name}: matches {checked.matched.describe()}"
        else:
            missed += 1
            near = checked.closest.describe() if checked.closest else "no readable chart"
            line = f"{name}: no chart matches; closest {near}"
        reasons.append(line)
        details.append(f"{line}; expected {values}")
    result["chart_data_match_reason"] = "; ".join(reasons)
    result["actual_chart_series"] = "; ".join(details)
    if scored:
        result["chart_data_match_score"] = 0.0 if missed else 1.0
    return result
