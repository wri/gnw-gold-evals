"""The ``expected.ground_truth`` selector: which figure out of the response.

    AGG(column)
    AGG(column) WHERE column=value

``AGG`` is ``sum`` / ``max`` / ``min`` / ``count``. An explicit aggregate is
**mandatory** — a bare column reference would be ambiguous whenever the filter
matches more than one row, which is live: 1-038 pulls 2 AOIs and 1-059 pulls 254,
so ``area_ha WHERE year=2019`` would silently reduce 254 rows by an implicit
rule nobody wrote down.

Parsed and applied in code, never by a judge — ``docs/specs/PLAN.md`` §6:
numbers in code, structure and semantics to the judge.

The selector names the **API's** column, not the agent's. The agent renames
columns in its pandas codeact (1-076's chart says ``loss_area_ha`` where the API
says ``area_ha``), so authoring from an artifact's ``charts_data`` is a trap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

AGGREGATES = {
    "sum": lambda values: sum(values),
    "max": lambda values: max(values),
    "min": lambda values: min(values),
    "count": lambda values: float(len(values)),
}

# `WHERE` is matched case-insensitively and the selector is normalised before
# use, because the string is hashed into the uid: `WHERE` and `where` must not
# mint two uids for what is the same test.
_SELECTOR = re.compile(
    r"^\s*(?P<agg>\w+)\s*\(\s*(?P<column>[\w.]+)\s*\)"
    r"(?:\s+where\s+(?P<key>[\w.]+)\s*=\s*(?P<value>.+?))?\s*$",
    re.IGNORECASE,
)


class SelectorError(Exception):
    """The selector is malformed, or does not resolve against a response."""


@dataclass(frozen=True)
class Selector:
    aggregate: str
    column: str
    filter_column: str | None = None
    filter_value: str | None = None

    def canonical(self) -> str:
        text = f"{self.aggregate}({self.column})"
        if self.filter_column is not None:
            text += f" WHERE {self.filter_column}={self.filter_value}"
        return text


def parse_selector(raw: str) -> Selector:
    match = _SELECTOR.match(raw or "")
    if not match:
        raise SelectorError(
            f"cannot parse ground_truth {raw!r}; expected "
            "'AGG(column)' or 'AGG(column) WHERE column=value'"
        )
    aggregate = match.group("agg").lower()
    if aggregate not in AGGREGATES:
        raise SelectorError(
            f"unknown aggregate {aggregate!r}; expected one of {sorted(AGGREGATES)}"
        )
    value = match.group("value")
    if value is not None:
        value = value.strip().strip("'\"")
    return Selector(aggregate, match.group("column"), match.group("key"), value)


def _rows(result: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """The analytics API answers column-oriented; rows are easier to filter."""
    if not result:
        return []
    return [dict(zip(result, values)) for values in zip(*result.values())]


def apply_selector(selector: Selector, result: dict[str, list[Any]]) -> float:
    """Resolve a selector against one analytics response.

    Raises ``SelectorError`` when the response lacks the column or the filter
    matches nothing. That is AC #4: a case whose metric is absent must **error**,
    never pass vacuously — an empty match summing to 0.0 would silently become a
    real-looking expected value.
    """
    if selector.column not in result:
        raise SelectorError(
            f"column {selector.column!r} not in the response "
            f"(columns: {sorted(result)})"
        )
    rows = _rows(result)

    if selector.filter_column is not None:
        if selector.filter_column not in result:
            raise SelectorError(
                f"filter column {selector.filter_column!r} not in the response "
                f"(columns: {sorted(result)})"
            )
        wanted = selector.filter_value
        rows = [row for row in rows if str(row.get(selector.filter_column)) == wanted]
        if not rows:
            raise SelectorError(
                f"no rows where {selector.filter_column}={wanted!r}; "
                "the metric this case needs is absent from the fetched data"
            )

    values = [
        float(row[selector.column])
        for row in rows
        if isinstance(row.get(selector.column), (int, float))
        and not isinstance(row.get(selector.column), bool)
    ]
    if not values:
        raise SelectorError(
            f"no numeric values in column {selector.column!r} after filtering"
        )
    return float(AGGREGATES[selector.aggregate](values))
