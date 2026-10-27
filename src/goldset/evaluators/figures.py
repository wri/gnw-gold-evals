"""Figure checks: the asked figure, recomputed from the data the agent pulled.

AJ's rule for BENCHMARK draft-5 (2026-10-27): whether the underlying data is
right is out of scope; what is scored is whether the agent did the right
maths on the table it pulled and stated the result in its reply. A case
names the figure with a formula (``figure``), never a stored value, so the
case survives data releases. Accuracy is "could this mislead the user?", so
the check is not strict about form: stated rounding, unit changes and fair
alternative calculations pass, and only the asked figures are checked.

``figure`` holds one or more figures separated by ``;``. A figure may list
fair alternatives separated by ``|``; a ``ref:`` prefix marks a figure used
only by ``figure_claim`` (it need not appear in the reply). A figure is
``AGG(EXPR) [by COLUMN] [where COND [and COND]...]`` with AGG one of sum,
mean, max, min, count; EXPR a column or columns joined with ``+``; ``by``
sums EXPR per value of COLUMN before AGG runs across those groups; and COND
one of ``COL = V``, ``COL != V``, ``COL in A..B`` (inclusive) or
``COL in (V1, V2)``. ``ratio(F, F)``, ``change(F, F)`` (second minus first)
and ``pct_change(F, F)`` combine two figures.

``figure_claim`` is ``CONDITION :: sentence if true || sentence if false``,
with CONDITION comparing figures by position (``#1 > #2``, ``#1 < 0``). The
data decides which sentence is true; an AI reviewer checks the reply says
it (``figure_claim_match``), and never does arithmetic.

The pulled tables are not in agent state (``statistics[*].data`` is empty),
so each statistics entry's ``source_url`` is fetched. A figure is computed on
each table and on the union of all of them, and the reply passes when it
states any computable candidate: one formula can then cover both a single
pull and a comparison split over two pulls, without summing two datasets
into one figure. A figure that cannot be computed (no table, a column the
table lacks) abstains rather than fails.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx

from goldset.evaluators.answer_evaluator import extract_final_answer_text
from goldset.evaluators.chart_numeric import format_number

TOLERANCE = 0.02
FETCH_TIMEOUT_S = 30.0

AGGREGATES = ("sum", "mean", "max", "min", "count")
COMBINERS = ("ratio", "change", "pct_change")


class FigureError(ValueError):
    """A figure or claim that does not parse: a case error, raised loudly."""


# ---------------------------------------------------------------- the grammar


@dataclass(frozen=True)
class Condition:
    column: str
    op: str  # "=", "!=", "range", "in"
    values: tuple[Any, ...]


@dataclass(frozen=True)
class Aggregate:
    func: str
    columns: tuple[str, ...]
    by: str | None = None
    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class Combined:
    func: str
    left: Aggregate
    right: Aggregate


Formula = Aggregate | Combined


@dataclass(frozen=True)
class Figure:
    text: str
    alternatives: tuple[Formula, ...]
    ref: bool = False


@dataclass(frozen=True)
class Claim:
    left: int | float  # figure position (1-based int) or a number
    op: str
    right: int | float
    left_is_figure: bool
    right_is_figure: bool
    if_true: str
    if_false: str


def _split_top(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside parentheses and quotes."""
    parts, depth, quote, current, i = [], 0, None, [], 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and text.startswith(sep, i):
            parts.append("".join(current))
            current, i = [], i + len(sep)
            continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return [p.strip() for p in parts]


def _value(token: str) -> Any:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    try:
        number = float(token)
    except ValueError:
        return token
    return int(number) if number.is_integer() and "." not in token else number


_RANGE = re.compile(r"^(\w+)\s+in\s+(.+?)\.\.(.+)$")
_LIST = re.compile(r"^(\w+)\s+in\s+\((.*)\)$")
_COMPARE = re.compile(r"^(\w+)\s*(!=|=)\s*(.+)$")


def _condition(text: str) -> Condition:
    if m := _LIST.match(text):
        return Condition(m[1], "in", tuple(_value(v) for v in _split_top(m[2], ",")))
    if m := _RANGE.match(text):
        return Condition(m[1], "range", (_value(m[2]), _value(m[3])))
    if m := _COMPARE.match(text):
        return Condition(m[1], m[2], (_value(m[3]),))
    raise FigureError(f"cannot read the condition {text!r}")


_AGGREGATE = re.compile(r"^(\w+)\((.+?)\)\s*(.*)$", re.S)
_BY = re.compile(r"\bby\s+(\w+)")


def _aggregate(text: str) -> Aggregate:
    m = _AGGREGATE.match(text.strip())
    if not m or m[1] not in AGGREGATES:
        raise FigureError(f"expected AGG(column) with AGG in {AGGREGATES}: {text!r}")
    func, expr, rest = m[1], m[2], m[3].strip()
    columns = tuple(c.strip() for c in expr.split("+") if c.strip())
    if not columns or not all(re.fullmatch(r"\w+", c) for c in columns):
        raise FigureError(f"expected column names in {func}(...): {text!r}")
    by = None
    if b := _BY.search(rest.split(" where ")[0] if " where " in rest else rest):
        by = b[1]
        rest = (rest[: b.start()] + rest[b.end():]).strip()
    conditions: tuple[Condition, ...] = ()
    if rest:
        if not rest.startswith("where "):
            raise FigureError(f"expected 'where ...' after the aggregate: {text!r}")
        clause = rest.removeprefix("where ").strip()
        if b := _BY.search(clause):
            if by:
                raise FigureError(f"two 'by' columns: {text!r}")
            by = b[1]
            clause = (clause[: b.start()] + clause[b.end():]).strip()
        conditions = tuple(_condition(c) for c in _split_top(clause, " and ") if c)
    return Aggregate(func, columns, by, conditions)


def parse_formula(text: str) -> Formula:
    text = text.strip()
    for combiner in COMBINERS:
        if text.startswith(combiner + "(") and text.endswith(")"):
            args = _split_top(text[len(combiner) + 1 : -1], ",")
            if len(args) != 2:
                raise FigureError(f"{combiner}() takes two figures: {text!r}")
            return Combined(combiner, _aggregate(args[0]), _aggregate(args[1]))
    return _aggregate(text)


def parse_figures(text: str) -> list[Figure]:
    """Parse a case's ``figure`` field; raises FigureError on any mistake."""
    figures = []
    for part in _split_top(text or "", ";"):
        if not part:
            continue
        ref = part.startswith("ref:")
        body = part.removeprefix("ref:").strip()
        alternatives = tuple(parse_formula(a) for a in _split_top(body, "|") if a)
        if not alternatives:
            raise FigureError(f"empty figure in {text!r}")
        figures.append(Figure(body, alternatives, ref))
    return figures


_CLAIM = re.compile(r"^\s*(#\d+|-?[\d.]+)\s*(>=|<=|>|<)\s*(#\d+|-?[\d.]+)\s*$")


def parse_claim(text: str, n_figures: int) -> Claim:
    """Parse ``CONDITION :: if true || if false``; raises FigureError."""
    if "::" not in text or "||" not in text:
        raise FigureError(f"expected 'CONDITION :: if true || if false': {text!r}")
    condition, sentences = text.split("::", 1)
    if_true, if_false = (s.strip() for s in sentences.split("||", 1))
    m = _CLAIM.match(condition)
    if not m or not if_true or not if_false:
        raise FigureError(f"cannot read the claim {text!r}")

    def side(token: str) -> tuple[int | float, bool]:
        if token.startswith("#"):
            position = int(token[1:])
            if not 1 <= position <= n_figures:
                raise FigureError(f"{token} names no figure (there are {n_figures})")
            return position, True
        return float(token), False

    left, left_fig = side(m[1])
    right, right_fig = side(m[3])
    return Claim(left, m[2], right, left_fig, right_fig, if_true, if_false)


def validate(expected: dict[str, str]) -> list[str]:
    """Problems with a case's figure fields, for tools/check.py."""
    problems = []
    try:
        figures = parse_figures(expected.get("figure") or "")
        if expected.get("figure_claim"):
            if not figures:
                problems.append("figure_claim without figure")
            else:
                parse_claim(expected["figure_claim"], len(figures))
    except FigureError as error:
        problems.append(f"figure: {error}")
    return problems


# ----------------------------------------------------------- the pulled data


@lru_cache(maxsize=4096)
def _fetch(url: str) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]] | None:
    """One pulled table as (columns, rows); None if it cannot be read."""
    try:
        response = httpx.get(
            url.replace("http://", "https://", 1), timeout=FETCH_TIMEOUT_S,
            follow_redirects=True,
        )
        response.raise_for_status()
        result = (response.json().get("data") or {}).get("result")
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(result, dict):
        return None
    columns = tuple(k for k, v in result.items() if isinstance(v, list))
    if not columns:
        return None
    length = max(len(result[c]) for c in columns)
    rows = tuple(
        tuple(result[c][i] if i < len(result[c]) else None for c in columns)
        for i in range(length)
    )
    return columns, rows


def pulled_tables(agent_state: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Every table the attempt pulled, each as a list of row dicts."""
    statistics = agent_state.get("statistics") or []
    if isinstance(statistics, dict):
        statistics = [statistics]
    tables, seen = [], set()
    for entry in statistics:
        url = str((entry or {}).get("source_url") or "") if isinstance(entry, dict) else ""
        if not url or url in seen:
            continue
        seen.add(url)
        fetched = _fetch(url)
        if fetched:
            columns, rows = fetched
            tables.append([dict(zip(columns, row, strict=True)) for row in rows])
    return tables


def _union(tables: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """All rows once: two pulls of overlapping windows repeat rows."""
    seen, rows = set(), []
    for table in tables:
        for row in table:
            key = tuple(sorted((k, repr(v)) for k, v in row.items()))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


# ------------------------------------------------------------- computation


class _NotComputable(Exception):
    pass


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            return stripped.lower()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _matches(row: dict[str, Any], condition: Condition) -> bool:
    if condition.column not in row:
        return False
    actual = _norm(row[condition.column])
    if condition.op == "range":
        low, high = (_norm(v) for v in condition.values)
        try:
            return low <= actual <= high
        except TypeError:
            # ISO dates against a datetime string: compare the date part.
            return str(low) <= str(actual)[: len(str(low))] <= str(high)
    if condition.op == "in":
        return actual in {_norm(v) for v in condition.values}
    target = _norm(condition.values[0])
    return (actual == target) if condition.op == "=" else (actual != target)


def _row_value(row: dict[str, Any], columns: tuple[str, ...]) -> float | None:
    total, any_value = 0.0, False
    for column in columns:
        value = row.get(column)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value)
            any_value = True
    return total if any_value else None


def _compute_aggregate(agg: Aggregate, rows: list[dict[str, Any]]) -> float:
    if not rows:
        raise _NotComputable("no rows pulled")
    needed = set(agg.columns) | {c.column for c in agg.conditions}
    if agg.by:
        needed.add(agg.by)
    present = set().union(*(row.keys() for row in rows))
    if not needed <= present:
        raise _NotComputable(f"the table has no {', '.join(sorted(needed - present))}")
    selected = [r for r in rows if all(_matches(r, c) for c in agg.conditions)]
    values: list[float]
    if agg.by:
        groups: dict[Any, float] = {}
        for row in selected:
            value = _row_value(row, agg.columns)
            if value is not None:
                groups[_norm(row.get(agg.by))] = groups.get(_norm(row.get(agg.by)), 0.0) + value
        values = list(groups.values())
    else:
        values = [v for r in selected if (v := _row_value(r, agg.columns)) is not None]
    if agg.func == "count":
        return float(len(values))
    if agg.func == "sum":
        return float(sum(values))
    if not values:
        raise _NotComputable("no rows match")
    if agg.func == "mean":
        return sum(values) / len(values)
    return max(values) if agg.func == "max" else min(values)


def compute(formula: Formula, rows: list[dict[str, Any]]) -> float:
    """The formula's value on ``rows``; raises _NotComputable."""
    if isinstance(formula, Aggregate):
        return _compute_aggregate(formula, rows)
    left = _compute_aggregate(formula.left, rows)
    right = _compute_aggregate(formula.right, rows)
    if formula.func == "change":
        return right - left
    if left == 0:
        raise _NotComputable("division by zero")
    if formula.func == "ratio":
        return left / right if right else math.inf
    return (right - left) / left * 100


def candidates(formula: Formula, tables: list[list[dict[str, Any]]]) -> list[float]:
    """The formula on each table and on their union (see the module doc)."""
    values = []
    for rows in [*tables, _union(tables)] if len(tables) > 1 else tables:
        try:
            value = compute(formula, rows)
        except _NotComputable:
            continue
        if math.isfinite(value) and value not in values:
            values.append(value)
    return values


# ------------------------------------------------------------- the reply


_SCALES = {
    "thousand": 1e3, "k": 1e3, "kha": 1e3, "kt": 1e3,
    "million": 1e6, "m": 1e6, "mn": 1e6, "mha": 1e6, "mt": 1e6, "mtco2e": 1e6,
    "billion": 1e9, "bn": 1e9, "b": 1e9, "gt": 1e9, "gtco2e": 1e9,
}
_NUMBER = re.compile(
    r"(?<![\w.])(-?\d{1,3}(?:,\d{3})+|-?\d+)(?:\.(\d+))?"
    r"\s*(%|percent|per cent)?\s*([A-Za-z²0-9]+)?"
)
_KM2 = ("km²", "km2")
# Words after a number that make it a measure, not a year.
_UNITS = ("ha", "hectare", "hectares", "acres", "t", "tonnes", "tons", "tco2e",
          "mgco2e", "mg", "co2e")


@dataclass(frozen=True)
class Stated:
    value: float
    precision: float  # half the last stated digit, in the same units
    percent: bool
    text: str


def stated_numbers(answer: str) -> list[Stated]:
    """Every number in the reply, scaled by the words after it."""
    found = []
    for m in _NUMBER.finditer(answer or ""):
        whole, decimals, percent = m[1], m[2] or "", m[3]
        word = (m[4] or "").lower()
        scale = _SCALES.get(word, 1.0)
        if word.startswith(_KM2):
            scale = 100.0  # km² to hectares
        measured = scale != 1.0 or word in _UNITS
        if not (decimals or "," in whole or percent or measured) and re.fullmatch(
            r"(19|20)\d\d", whole.lstrip("-")
        ):
            continue  # a year, not a figure
        value = float(whole.replace(",", "") + ("." + decimals if decimals else ""))
        step = 10.0 ** (-len(decimals)) if decimals else 1.0
        text = whole + ("." + decimals if decimals else "") + (percent or "")
        if measured:
            text += " " + m[4]
        found.append(Stated(value * scale, 0.5 * step * scale, bool(percent), text))
    return found


def _close(stated: Stated, expected: float, as_share: bool) -> float | None:
    """Relative difference if the stated number can mean the expected one."""
    target = abs(expected) * (100.0 if as_share and stated.percent else 1.0)
    if as_share and not stated.percent and abs(stated.value) > 1.5:
        return None
    value = abs(stated.value)
    if target == 0:
        return 0.0 if value == 0 else None
    # Rounding as stated passes: "1.8 million" covers 1.75 to 1.85 million.
    if abs(value - target) <= stated.precision:
        return 0.0
    return abs(value - target) / target


@dataclass
class FigureResult:
    figure: Figure
    values: list[float] = field(default_factory=list)
    matched: str | None = None
    closest: tuple[str, float] | None = None


# A zero figure is often stated in words ("no loss was recorded").
_ZERO_WORDS = re.compile(
    r"\b(zero|none|no (?:[\w-]+ ){0,2}"
    r"(loss|alerts?|change|gain|emissions|disturbances?|deforestation))\b",
    re.I,
)


def _check_figure(
    figure: Figure, tables, stated: list[Stated], answer: str = ""
) -> FigureResult:
    result = FigureResult(figure)
    for formula in figure.alternatives:
        as_share = isinstance(formula, Combined) and formula.func == "ratio"
        for value in candidates(formula, tables):
            result.values.append(value)
            if value == 0 and (m := _ZERO_WORDS.search(answer)):
                result.matched = m[0]
                return result
            for number in stated:
                difference = _close(number, value, as_share)
                if difference is None:
                    continue
                if difference <= TOLERANCE:
                    result.matched = number.text
                    return result
                if result.closest is None or difference < result.closest[1]:
                    result.closest = (number.text, difference)
    return result


def evaluate_figures(agent_state: dict[str, Any], figure_text: str) -> dict[str, Any]:
    """figure_match: every asked figure the data can give appears in the reply.

    ``null`` when the case names no figure, or no asked figure can be computed
    from what was pulled (nothing pulled, a table that cannot be read, a
    column it lacks). ``0.0`` when a computable figure is missing from the
    reply; ``1.0`` when every computable one is there.
    """
    result: dict[str, Any] = {
        "figure_match_score": None,
        "figure_match_reason": None,
        "actual_figures": None,
    }
    figures = parse_figures(figure_text)
    if not figures:
        return result
    tables = pulled_tables(agent_state)
    if not tables:
        result["figure_match_reason"] = "no pulled table could be read; abstained"
        return result
    answer = extract_final_answer_text(agent_state.get("messages", []))
    stated = stated_numbers(answer)
    parts, scored, missed = [], 0, 0
    for figure in figures:
        if figure.ref:
            continue
        checked = _check_figure(figure, tables, stated, answer)
        if not checked.values:
            parts.append(f"{figure.text}: not computable from the pull")
            continue
        scored += 1
        expected = format_number(checked.values[0])
        if checked.matched:
            parts.append(f"{figure.text} = {expected}: reply states {checked.matched}")
        else:
            missed += 1
            near = (
                f", closest {checked.closest[0]} ({checked.closest[1]:.1%})"
                if checked.closest else ", no comparable number"
            )
            parts.append(f"{figure.text} = {expected}: not in the reply{near}")
    result["actual_figures"] = "; ".join(parts)[:600]
    result["figure_match_reason"] = result["actual_figures"]
    if scored:
        result["figure_match_score"] = 0.0 if missed else 1.0
    return result


def claim_sentence(
    agent_state: dict[str, Any], figure_text: str, claim_text: str
) -> tuple[str | None, str]:
    """The claim sentence the data makes true, or None with the reason."""
    figures = parse_figures(figure_text)
    claim = parse_claim(claim_text, len(figures))
    tables = pulled_tables(agent_state)
    if not tables:
        return None, "no pulled table could be read"

    def value(position: int) -> float | None:
        # The union of every pull first: a claim compares across pulls.
        for formula in figures[position - 1].alternatives:
            for rows in (_union(tables), *tables):
                try:
                    return compute(formula, rows)
                except _NotComputable:
                    continue
        return None

    left = value(int(claim.left)) if claim.left_is_figure else claim.left
    right = value(int(claim.right)) if claim.right_is_figure else claim.right
    if left is None or right is None:
        return None, "a figure the claim compares is not computable from the pull"
    holds = {
        ">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right,
    }[claim.op]
    detail = f"{format_number(left)} {claim.op} {format_number(right)} is {holds}"
    return (claim.if_true if holds else claim.if_false), detail


# ------------------------------------------------- the two judged checks


def evaluate_figure_claim(
    agent_state: dict[str, Any], figure_text: str, claim_text: str
) -> dict[str, Any]:
    """figure_claim_match: the reply states the conclusion the data supports."""
    from goldset.evaluators.llm_judges import llm_judge_claim

    result: dict[str, Any] = {
        "figure_claim_match_score": None,
        "figure_claim_match_score_reason": None,
        "actual_figure_claim": None,
        "judge_errors": [],
    }
    if not claim_text or not figure_text:
        return result
    sentence, detail = claim_sentence(agent_state, figure_text, claim_text)
    result["actual_figure_claim"] = detail if sentence is None else f"{sentence} ({detail})"
    answer = extract_final_answer_text(agent_state.get("messages", []))
    if sentence is None or not answer:
        return result
    try:
        judged = llm_judge_claim(sentence, answer)
    except Exception as error:
        result["figure_claim_match_score_reason"] = f"JUDGE ERROR: {error}"
        result["judge_errors"] = ["figure_claim_match"]
        return result
    result["figure_claim_match_score"] = 1.0 if judged["score"] else 0.0
    result["figure_claim_match_score_reason"] = f"{sentence}: {judged['reason']}"
    return result


def _period_text(start: str, end: str, tolerance_days: int) -> str:
    def plain(day: str, is_end: bool) -> str:
        # A whole calendar year reads as the year.
        if re.fullmatch(r"\d{4}-01-01", day) and not is_end:
            return day[:4]
        if re.fullmatch(r"\d{4}-12-31", day) and is_end:
            return day[:4]
        return day

    if start and end:
        first, last = plain(start, False), plain(end, True)
        text = first if first == last else f"from {first} to {last}"
    elif start:
        text = f"from {plain(start, False)} to the latest data available"
    else:
        text = f"up to {plain(end, True)}"
    if tolerance_days:
        text += f" (give or take {tolerance_days} days)"
    return text


def evaluate_answer_period(
    agent_state: dict[str, Any],
    query: str,
    start_date: str,
    end_date: str,
    tolerance_days: int = 0,
) -> dict[str, Any]:
    """answer_period_match: the reply's figures cover exactly the asked period."""
    from goldset.evaluators.llm_judges import llm_judge_answer_period
    from goldset.evaluators.utils import normalize_end_date, normalize_start_date

    result: dict[str, Any] = {
        "answer_period_match_score": None,
        "answer_period_match_score_reason": None,
        "actual_answer_period": None,
        "judge_errors": [],
    }
    start = normalize_start_date(start_date) if start_date else ""
    end = normalize_end_date(end_date) if end_date else ""
    answer = extract_final_answer_text(agent_state.get("messages", []))
    if not (start or end) or not answer:
        return result
    period = _period_text(start, end, tolerance_days)
    try:
        judged = llm_judge_answer_period(query, period, answer)
    except Exception as error:
        result["answer_period_match_score_reason"] = f"JUDGE ERROR: {error}"
        result["judge_errors"] = ["answer_period_match"]
        return result
    result["actual_answer_period"] = judged["reason"]
    result["answer_period_match_score_reason"] = f"asked {period}: {judged['reason']}"
    if judged["verdict"] != "not_applicable":
        result["answer_period_match_score"] = 1.0 if judged["verdict"] == "pass" else 0.0
    return result
