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
"""

from __future__ import annotations

from typing import Any

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
    return problems
