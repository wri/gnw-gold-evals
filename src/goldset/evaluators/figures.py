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

Replies to cases in another language (Spanish, Indonesian, Portuguese,
French) are read with ``language`` set (see "local number formats" below).
English cases take the original parser, unchanged, so the frozen English
BENCHMARK scores as before.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

import httpx

from goldset.canonical import require_language
from goldset.evaluators.answer_evaluator import extract_final_answer_text
from goldset.evaluators.chart_numeric import format_number
from goldset.evaluators.reply_language import detect_language

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
    # The second reading of a number whose shape reads two ways ("1.209").
    other: Stated | None = None
    # One group of a plain-space number ("345" of "12 345"): it can only
    # abstain, never match as a first reading.
    part: bool = False


def stated_numbers(
    answer: str, language: str = "en", *, usual_mark: str | None = None
) -> list[Stated]:
    """Every number in the reply, scaled by the words after it.

    ``usual_mark`` replaces the case language's usual decimal mark for a
    number whose shape reads two ways, when the reply is known to follow
    another language's habit. English cases ignore it.
    """
    require_language(language)
    if language != "en":
        # A decomposed accent would cut "millón" short at the "o".
        answer = unicodedata.normalize("NFC", answer or "")
        return _stated_numbers_local(answer, language, usual_mark)
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


# ------------------------------------------------- local number formats
#
# Indonesian, Brazilian Portuguese and most Spanish-speaking countries write
# "1.209,32" where English writes "1,209.32" (Mexico and Central America
# write it as English does); French writes "1 209,32". Horizon's replies do
# not follow the case language reliably, so a number is read in this order:
#
# 1. By its own shape, when that is clear: "1.209,32", "12,5", "1.234.567".
#    It has one reading.
# 2. When its shape reads two ways ("1.209"), the reply's own convention
#    (the mark its clear numbers agree on) gives the first reading.
# 3. Failing that, Horizon's habit in the case language gives the first; a
#    reply that is plainly English follows the English habit instead.
#
# Spaces group thousands too ("1 209"); see ``_spaced_readings``.
#
# A shape-ambiguous number always keeps its second reading, however sure the
# first looks: a reply mixes conventions, so a figure that matches only the
# second reading abstains (AJ, 2026-11-18: abstain when a number has no clear
# reading) and never fails. A wrong figure matches neither reading.
#
# The habit is measured, not assumed. Of Horizon's replies to external users
# that show a convention (traces to 2026-10-20): Spanish 657 dot-decimal to
# 26 comma-decimal; Indonesian 135 comma-decimal to 12 dot-decimal. Counted
# the same way (traces to 2026-11-19): Portuguese 69 comma-decimal to 7
# dot-decimal; French 133 comma-decimal to 12 dot-decimal. Every one of them
# written in Portuguese or French uses the comma (in the local trace copy to
# 2026-10-19 the dot-decimal ones are in English, bar one in Spanish), and
# French groups thousands with a space.

_USUAL_DECIMAL_MARK = {"es": ".", "id": ",", "pt": ",", "fr": ","}

# "billón" is the long-scale billion, 10^12. "mil" is a scale in Spanish and
# Portuguese only: in an Indonesian or French reply it is not one, and "ribu"
# is not one in a Spanish reply. Portuguese is Brazilian (AJ, 2026-11-19):
# "bilhão" is 10^9, and the European "bilião" is no scale, so it can never
# pass as 10^9; "mil milhões" is 10^9 in either country. In a French reply
# "milliard" is 10^9 and "billion" has its French meaning, 10^12 (AJ,
# 2026-11-19); a reply to a French case that reads as English is no French
# reply, so there it keeps its English meaning (``_ENGLISH_MEANING``).
_LOCAL_SCALES = {
    "es": {
        **_SCALES,
        "mil": 1e3, "miles": 1e3,
        "millón": 1e6, "millon": 1e6, "millones": 1e6,
        "mil millones": 1e9, "miles de millones": 1e9,
        "millardo": 1e9, "millardos": 1e9,
        "billón": 1e12, "billon": 1e12, "billones": 1e12,
    },
    "id": {
        **_SCALES,
        "ribu": 1e3, "rb": 1e3,
        "juta": 1e6, "jt": 1e6,
        "miliar": 1e9, "milyar": 1e9,
        "triliun": 1e12, "trilyun": 1e12,
    },
    "pt": {
        **_SCALES,
        "mil": 1e3,
        "milhão": 1e6, "milhao": 1e6, "milhões": 1e6, "milhoes": 1e6,
        "mil milhões": 1e9, "mil milhoes": 1e9,
        "bilhão": 1e9, "bilhao": 1e9, "bilhões": 1e9, "bilhoes": 1e9,
        "trilhão": 1e12, "trilhao": 1e12, "trilhões": 1e12, "trilhoes": 1e12,
    },
    "fr": {
        **_SCALES,
        "mille": 1e3, "millier": 1e3, "milliers": 1e3,
        "million": 1e6, "millions": 1e6,
        "milliard": 1e9, "milliards": 1e9,
        "billion": 1e12, "billions": 1e12,
    },
}
# Scale words the case language and English spell alike but read apart.
_ENGLISH_MEANING = {"fr": {"billion": 1e9, "billions": 1e9}}
_LOCAL_UNITS = (*_UNITS, "hectárea", "hectáreas", "hectarea", "hectareas",
                "hektar", "hektare", "tonelada", "toneladas", "ton")
_KM2_PHRASE = (
    r"kil[oó]metros?\s+cuadrados?|(?:kilometer|km)\s+persegi"
    r"|quil[oóô]metros?\s+quadrados?|kilom[èe]tres?\s+carr[ée]s?"
)
# Space-grouped thousands: a head of one to three digits, then groups of
# exactly three ("1 209", "12 345 678"). A head of four digits ("2024 120")
# is no grouping.
_SPACE_GROUPED = r"\d{1,3}(?:[ \u00a0\u202f\u2009]\d{3})+(?!\d)"
_LOCAL_NUMBER = re.compile(
    r"(?<![\w.])(-?(?:" + _SPACE_GROUPED + r"|\d+)(?:[.,]\d+)*)"
    r"\s*(%|percent|per cent|por ciento|por cien|porciento|persen"
    r"|por cento|porcento|pour cent|pourcent)?"
    r"\s*(miles\s+de\s+millones|mil\s+millones|mil\s+milh[õo]es|" + _KM2_PHRASE
    + r"|[^\W\d_][^\W_]*)?",
    re.I,
)
_KM2_WORDS = re.compile(_KM2_PHRASE)
_GROUP_SPACE = re.compile(r"[ \u00a0\u202f\u2009]")


def _spaced_readings(raw: str) -> list[tuple[str, str, bool, bool]]:
    """(number, text, carries the reply's suffix, is a part) readings of a
    matched number.

    A no-break, narrow no-break or thin space only groups digits, so the
    number is read joined. A plain space may separate two figures in a list
    ("5 200 ha" for "5" and "200 ha"): the joined number is the first
    reading and its parts are second readings that can only abstain. A
    group with a leading zero ("000" of "1 000") is never a number alone,
    so it is no part at all.
    """
    pieces = _GROUP_SPACE.split(raw)
    joined = "".join(pieces)
    if len(pieces) == 1:
        return [(raw, raw, True, False)]
    if " " not in raw:
        return [(joined, raw, True, False)]
    last = len(pieces) - 1
    return [(joined, raw, True, False)] + [
        (piece, piece, index == last, True)
        for index, piece in enumerate(pieces)
        if not (len(piece) > 1 and piece.startswith("0"))
    ]


def _decimal_mark(number: str) -> str | None:
    """The decimal mark a number shows by its shape: "." or ",", "" for a
    number that shows none (an integer with or without grouping), or None
    when the shape reads two ways ("1.209")."""
    dots, commas = number.count("."), number.count(",")
    if not dots and not commas:
        return ""
    if dots and commas:
        return "." if number.rfind(".") > number.rfind(",") else ","
    mark = "." if dots else ","
    if dots + commas > 1:
        return ""  # a repeated mark groups thousands
    whole, fraction = number.lstrip("-").split(mark)
    if len(fraction) != 3 or len(whole) > 3 or whole == "0":
        return mark
    return None


def _read(number: str, decimal: str) -> tuple[float, float] | None:
    """(value, step of the last stated digit) with ``decimal`` ("." or ",")
    as the decimal mark; None when the grouping is not in threes."""
    group = _other_mark(decimal)
    whole, _, fraction = number.partition(decimal)
    if group in fraction:
        return None
    head, *groups = whole.lstrip("-").split(group)
    if groups and (not 1 <= len(head) <= 3 or any(len(g) != 3 for g in groups)):
        return None
    value = float(whole.replace(group, "") + ("." + fraction if fraction else ""))
    return value, 10.0 ** (-len(fraction)) if fraction else 1.0


def _other_mark(mark: str) -> str:
    """The decimal mark that is not ``mark``."""
    return "," if mark == "." else "."


def _suffix_word(suffix: str | None) -> str:
    """The word after a number, lower-cased with its spaces collapsed."""
    return " ".join((suffix or "").lower().split())


def _stated_as(
    reading: tuple[float, float], scale: float, percent: str | None, text: str
) -> Stated:
    return Stated(reading[0] * scale, 0.5 * reading[1] * scale, bool(percent), text)


def _word_scale(
    word: str, language: str, english: bool = False
) -> tuple[float, bool]:
    """(scale, whether the word makes the number a measure) for the word
    after a number; ``english`` when the reply reads as English."""
    scale = _LOCAL_SCALES[language].get(word, 1.0)
    if english:
        scale = _ENGLISH_MEANING.get(language, {}).get(word, scale)
    if word.startswith(_KM2) or _KM2_WORDS.fullmatch(word):
        scale = 100.0  # km² to hectares
    return scale, scale != 1.0 or word in _LOCAL_UNITS


def _reply_decimal_mark(matches: list[re.Match[str]], language: str) -> str | None:
    """The decimal mark the reply's clear numbers agree on, if they do.

    A number is evidence only when it cannot be a version, a time or a
    coordinate ("GADM 4.1", "10.30"): it shows both marks ("1.209,32"),
    repeats one as grouping in threes ("1.234.567"), or has one clear mark
    and a percent sign, scale word or unit after it ("10,46%", "2,5 juta").
    """
    marks = set()
    for m in matches:
        number = "".join(_GROUP_SPACE.split(m[1]))
        mark = _decimal_mark(number)
        if mark:
            word = _suffix_word(m[3])
            if (
                ("." in number and "," in number)
                or m[2]
                or _word_scale(word, language)[1]
            ):
                marks.add(mark)
        elif mark == "" and ("." in number or "," in number):
            # "1.234.567" groups with dots, so its decimal mark is the comma;
            # a date or version ("31.12.2024") groups in nothing and says nothing.
            implied = _other_mark("." if "." in number else ",")
            if _read(number, implied):
                marks.add(implied)
    return marks.pop() if len(marks) == 1 else None


def _stated_numbers_local(
    answer: str, language: str, usual_mark: str | None
) -> list[Stated]:
    """``stated_numbers`` for a non-English case; ``answer`` is NFC."""
    matches = list(_LOCAL_NUMBER.finditer(answer))
    reply_mark = _reply_decimal_mark(matches, language)
    # The local meaning of a shared scale word belongs to a reply detected in
    # the case language; a short or mixed reply gets the English one.
    english = (
        language in _ENGLISH_MEANING and detect_language(answer)[0] != language
    )
    found = []
    for m in matches:
        for number, shown, carries, part in _spaced_readings(m[1]):
            percent = m[2] if carries else None
            suffix = m[3] if carries else None
            word = _suffix_word(suffix)
            scale, measured = _word_scale(word, language, english)
            plain = "." not in number and "," not in number
            if plain and not (percent or measured) and re.fullmatch(
                r"(19|20)\d\d", number.lstrip("-")
            ):
                continue  # a year, not a figure
            text = shown + (percent or "") + (" " + suffix if measured else "")
            mark = _decimal_mark(number)
            if mark is None:
                # The reply's mark, else the usual one, only picks the first
                # reading.
                usual = reply_mark or usual_mark or _USUAL_DECIMAL_MARK[language]
                marks = [usual, _other_mark(usual)]
            else:
                # No decimal part: the decimal mark is the one the grouping
                # leaves.
                marks = [mark or _other_mark("." if "." in number else ",")]
            readings = [_read(number, m_) for m_ in marks]
            if readings[0] is None:
                continue  # "1.23.4567": not a number this parser can read

            first = replace(
                _stated_as(readings[0], scale, percent, text), part=part
            )
            if len(readings) > 1 and readings[1] is not None:
                first = replace(
                    first, other=_stated_as(readings[1], scale, percent, text)
                )
            found.append(first)
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
    # A stated number that matches only by its second reading (see Stated).
    unsure: str | None = None


# A zero figure is often stated in words ("no loss was recorded").
_ZERO_WORDS = re.compile(
    r"\b(zero|none|no (?:[\w-]+ ){0,2}"
    r"(loss|alerts?|change|gain|emissions|disturbances?|deforestation))\b",
    re.I,
)
# "cero" counts only before a loss noun ("cero alertas"): "deforestación cero"
# and "cero emisiones netas" name a target. Words that turn the phrase into
# "no data" or an idiom ("sin embargo", "sin información", "sin duda") are
# excluded between the cue and the noun.
_ES_SKIP = (
    "embargo|contar|incluir|datos|informaci[óo]n|registros?"
    "|precedentes|importar|duda"
)
_PT_SKIP = "contar|incluir|dados|informaç(?:ão|ões)|registros?|precedentes|dúvida"
_FR_SKIP = "compter|inclure|donn[ée]es?|informations?|jeux?|précédents?|doute"
# French "changement" that goes on to name a measured noun is no zero (see below).
_FR_CHANGE = (
    r"changements?(?! (?:dans|des?|du|sur|en|d['’]) ?"
    r"(?:(?:les|la|le|des|de la) |l['’])?"
    r"(?:pertes?|alertes?|gains?|émissions|perturbations?|déforestation))"
)
# The negation or "without" must take the measured noun at once, after at most
# one quantifier: a gap of up to two words let "sin distinguir las pérdidas"
# and "tanpa membedakan kehilangan" (an infinitive, then a noun of another
# clause) pass as a stated zero. "no hubo" and "tidak ada" need a measured
# noun: "no hubo reducción de las pérdidas" states a change, not a zero.
# "cambio" and "perubahan" do not count when they go on to name a measured
# noun ("no hubo cambio en las pérdidas": the loss itself is not said to be 0).
# "eventos de" / "hectáreas de" and "kejadian" only count a measured noun.
_LOCAL_ZERO_WORDS = {
    "es": re.compile(
        r"\b(?:cero (?:hect[áa]reas|ha)"
        r"|cero (?:(?!"+_ES_SKIP+r")[\w-]+ ){0,2}"
        r"(?:p[ée]rdidas?|alertas?|cambios?|ganancias?|perturbaci\w+)"
        r"|(?:no (?:se )?(?:ha |han )?"
        r"(?:registr|detect|observ|report|encontr|identific)\w+|no hay|no existen?"
        r"|no ha habido|no hubo|tampoco hubo|no presenta|sin|ning[úu]n|ningun[ao])"
        r" (?:(?:ning[úu]n|ningun[ao]s?|nuev[ao]s?) )?"
        r"(?:(?:eventos|hect[áa]reas) de )?"
        r"(?:p[ée]rdidas?|alertas?|ganancias?|emisiones|perturbaci\w+"
        r"|deforestaci[óo]n"
        r"|cambios?(?! (?:en|de) (?:(?:la|las|el|los) )?"
        r"(?:p[ée]rdidas?|alertas?|ganancias?|emisiones|perturbaci\w+"
        r"|deforestaci[óo]n))))\b",
        re.I,
    ),
    "id": re.compile(
        r"\b(?:nihil|nol (?:hektare?|ha|peringatan)|(?:tidak ada|tak ada|belum ada"
        r"|tanpa|tidak terdapat|tidak ditemukan|tidak terdeteksi|tidak tercatat"
        r"|tidak terjadi|tidak mengalami) (?:adanya )?(?:kejadian )?"
        r"(?:kehilangan|peringatan|penambahan|emisi|gangguan|deforestasi"
        r"|perubahan(?! (?:kehilangan|peringatan|emisi|gangguan|deforestasi))))\b",
        re.I,
    ),
    # As in Spanish: "zero" and "zéro" count only before a loss noun
    # ("desmatamento zero", "zéro déforestation" name a target), and words
    # that turn the phrase into "no data" or an idiom are excluded.
    "pt": re.compile(
        r"\b(?:zero (?:hectares?|ha)"
        r"|zero (?:(?!"+_PT_SKIP+r")[\w-]+ ){0,2}"
        r"(?:perdas?|alertas?|mudanças?|alteraç(?:ão|ões)|ganhos?"
        r"|perturbaç(?:ão|ões))"
        # "Não houve redução das perdas", "nenhuma redução das perdas" and
        # "sem considerar as perdas" say nothing about a zero loss: these cues
        # take the measured noun at once, after at most one quantifier and an
        # "eventos de" / "hectares de" bridge, never a verb or another noun.
        # "mudança" and "alteração" do not count when they go on to name a
        # measured noun ("nenhuma mudança nas perdas": the loss itself is not
        # said to be 0).
        r"|(?:n[ãa]o (?:se )?(?:foi |foram |houve |há )?"
        r"(?:registr|detect|observ|report|encontr|identific|verific)\w+"
        r"|n[ãa]o (?:houve|h[áa]|ocorreu|ocorreram|exist\w+|apresent\w+)"
        r"|sem|nenhum|nenhuma)"
        r" (?:(?:nenhum[a]?s?|qualquer|novos?|novas?) )?"
        r"(?:(?:eventos?|hectares?|ocorr[êe]ncias?) de )?"
        r"(?:perdas?|alertas?|ganhos?|emissões|perturbaç(?:ão|ões)|desmatamento"
        r"|hectares?"
        r"|(?:mudanças?|alteraç(?:ão|ões))"
        r"(?! (?:(?:em|de) (?:(?:as|os|a|o) )?|d[ao]s? |n[ao]s? )"
        r"(?:perdas?|alertas?|ganhos?|emissões|perturbaç(?:ão|ões)"
        r"|desmatamento)))"
        # "A perda foi nula"; a negation between noun and word ("não foi nula")
        # turns it round, so none may sit between them.
        r"|(?:perdas?|alertas?|mudanças?|alteraç(?:ão|ões)|ganhos?|emissões"
        r"|perturbaç(?:ão|ões)|desmatamento)"
        r" (?:(?!n[ãa]o\b|nunca\b)[\w-]+ ){0,6}nul[oa]s?)\b",
        re.I,
    ),
    "fr": re.compile(
        r"\b(?:z[ée]ro (?:hectares?|ha)"
        r"|z[ée]ro (?:(?!"+_FR_SKIP+r")[\w-]+ ){0,2}"
        r"(?:pertes?|alertes?|changements?|gains?|perturbations?)"
        # "aucune" takes the measured noun at once, after at most one
        # quantifier and a "hectares de" / "cas de" bridge: "aucune réduction
        # des pertes" states a change, not a zero. "changement" does not count
        # when it goes on to name a measured noun ("aucun changement dans les
        # pertes": the loss itself is not said to be 0).
        r"|aucune? (?:(?:nouvel(?:le)?s?|nouveaux?|aucune?) )?"
        r"(?:(?:hectares?|[ée]v[ée]nements?|cas) d(?:e |['’]))?"
        r"(?:pertes?|alertes?|gains?|émissions|perturbations?"
        r"|déforestation|hectares?"
        r"|"+_FR_CHANGE+r")"
        # "pas de" and "sans" state a zero only as an existence statement:
        # "ne permettent pas de distinguer", "n'est pas de la déforestation"
        # and "sans distinguer les pertes" do not, so the noun follows at
        # once (after one adjective at most).
        r"|(?:n['’]y a (?:pas (?:eu )?|eu )d(?:e |['’])"
        r"|n['’](?:a|ont) pas (?:été )?(?:détect|enregistr|observ|constat"
        r"|identifi|signal)\w* (?:d(?:e |['’]))?"
        r"|sans )"
        r"(?:(?!"+_FR_SKIP+r"|les\b|des\b|la\b|du\b)[\wé-]+ )?"
        r"(?:pertes?|alertes?|gains?|émissions|perturbations?"
        r"|déforestation|"+_FR_CHANGE+r")"
        # "La perte a été nulle"; a negation between noun and word ("n'est
        # pas nulle") turns it round, so none may sit between them.
        r"|(?:pertes?|alertes?|changements?|gains?|émissions|perturbations?"
        r"|déforestation)"
        r" (?:(?!pas\b|ne\b|n['’]|jamais\b)[\w’'-]+ ){0,6}nulles?)\b"
        # A sentence that opens on "Pas de" (a bullet, a title) is the same
        # existence statement; mid-sentence "pas de" is not.
        r"|(?:^|[.!?\n:;])[\s*_>•-]*pas d(?:e |['’])"
        r"(?:(?!"+_FR_SKIP+r"|les\b|des\b|la\b|du\b)[\wé-]+ )?"
        r"(?:pertes?|alertes?|gains?|émissions|perturbations?"
        r"|déforestation|"+_FR_CHANGE+r")\b",
        re.I,
    ),
}
# In Portuguese "no" is "in the" ("no Tree cover loss") and "zero" names a
# target ("desmatamento zero"), so the English cues misread a Portuguese
# reply: one that reads as Portuguese is read with its own cues only.
_OWN_ZERO_CUES_ONLY = frozenset({"pt"})


def _zero_words(answer: str, language: str) -> re.Match[str] | None:
    # A reply to a case in another language may still be in English.
    local = _LOCAL_ZERO_WORDS.get(language)
    english = not (
        language in _OWN_ZERO_CUES_ONLY and detect_language(answer)[0] == language
    )
    return (english and _ZERO_WORDS.search(answer)) or (
        local.search(answer) if local else None
    )


def _check_figure(
    figure: Figure,
    tables,
    stated: list[Stated],
    answer: str = "",
    language: str = "en",
) -> FigureResult:
    result = FigureResult(figure)
    for formula in figure.alternatives:
        as_share = isinstance(formula, Combined) and formula.func == "ratio"
        for value in candidates(formula, tables):
            result.values.append(value)
            if value == 0 and (m := _zero_words(answer, language)):
                result.matched = m[0]
                return result
            for number in stated:
                if number.part:
                    continue
                difference = _close(number, value, as_share)
                if difference is None:
                    continue
                if difference <= TOLERANCE:
                    result.matched = number.text
                    return result
                if result.closest is None or difference < result.closest[1]:
                    result.closest = (number.text, difference)
            for number in stated:
                # A part of a spaced number is itself the second reading.
                second = number if number.part else number.other
                if second is None or result.unsure:
                    continue
                difference = _close(second, value, as_share)
                if difference is not None and difference <= TOLERANCE:
                    result.unsure = number.text
    return result


def evaluate_figures(
    agent_state: dict[str, Any], figure_text: str, language: str = "en"
) -> dict[str, Any]:
    """figure_match: every asked figure the data can give appears in the reply.

    ``language`` is the case's language; it sets how the reply's numbers are
    read. A figure the reply states only as the second reading of a number
    whose shape reads two ways ("1.209") abstains.

    ``null`` when the case names no figure, or no asked figure can be computed
    from what was pulled (nothing pulled, a table that cannot be read, a
    column it lacks). ``0.0`` when a computable figure is missing from the
    reply; ``1.0`` when every computable one is there.
    """
    require_language(language)
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
    usual_mark = None
    if language != "en":
        # Normalised here as well as in ``stated_numbers``, for the zero-word
        # search: a decomposed accent would split a word there too.
        answer = unicodedata.normalize("NFC", answer)
        # Horizon may answer a case in any other language in English, and an
        # English reply writes "1,209" for 1209 whatever the case language.
        usual_mark = "." if detect_language(answer)[0] == "en" else None
    stated = stated_numbers(answer, language, usual_mark=usual_mark)
    parts, scored, missed = [], 0, 0
    for figure in figures:
        if figure.ref:
            continue
        checked = _check_figure(figure, tables, stated, answer, language)
        if not checked.values:
            parts.append(f"{figure.text}: not computable from the pull")
            continue
        expected = format_number(checked.values[0])
        if not checked.matched and checked.unsure:
            parts.append(
                f"{figure.text} = {expected}: reply states {checked.unsure}, "
                "which reads two ways; abstained"
            )
            continue
        scored += 1
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


def _fixed_period_text(fixed_period: str) -> str:
    match = re.fullmatch(r"\s*(\d{4})\s*-\s*(\d{4})\s*", fixed_period)
    if not match:
        raise ValueError(
            f"accept_fixed_period must be 'YYYY-YYYY', got {fixed_period!r}"
        )
    return f"{match.group(1)} to {match.group(2)}"


def evaluate_answer_period(
    agent_state: dict[str, Any],
    query: str,
    start_date: str,
    end_date: str,
    tolerance_days: int = 0,
    fixed_period: str = "",
) -> dict[str, Any]:
    """answer_period_match: the reply's figures cover exactly the asked period,
    or the case's ``accept_fixed_period`` when the data only come as that."""
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
    fixed = _fixed_period_text(fixed_period) if fixed_period else ""
    answer = extract_final_answer_text(agent_state.get("messages", []))
    if not (start or end) or not answer:
        return result
    period = _period_text(start, end, tolerance_days)
    try:
        judged = llm_judge_answer_period(query, period, answer, fixed)
    except Exception as error:
        result["answer_period_match_score_reason"] = f"JUDGE ERROR: {error}"
        result["judge_errors"] = ["answer_period_match"]
        return result
    result["actual_answer_period"] = judged["reason"]
    result["answer_period_match_score_reason"] = f"asked {period}: {judged['reason']}"
    if judged["verdict"] != "not_applicable":
        result["answer_period_match_score"] = 1.0 if judged["verdict"] == "pass" else 0.0
    return result
