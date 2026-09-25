"""Tool-scope validator: did the agent stay inside the tools a case allows?

``forbidden_tools_absent`` reads the tool calls the agent actually made
(``messages[].tool_calls``, the same surface ``evaluate_date_extraction`` and
the run artifacts read) and fails if any tool the case forbids appears.

Why it exists: the CHALLENGE ``map`` set asserts "show X on the map" is
served by ``pick_dataset`` alone. Nothing else in the harness can say that:
``data_pull: 'FALSE'`` switches the pull checks *off* rather than asserting
no pull, ``scope`` classifies a clean pick-and-stop as ``none`` (the
``refuse`` class) and never sees ``pick_aoi``, and an empty ``aoi_ids`` means
"no expectation", not "no AOI".

Opt-in: it fires only on rows that set ``forbidden_tools``, so GOLD is
unaffected. The tool list lives in the case (``;``-separated, hashed into
the uid) rather than in code, so a case says exactly what it forbids and a
change of policy is a visible uid change, not a silent semantics shift.

Multi-turn caveat: thread state accumulates messages across turns, so a
later turn also sees earlier turns' tool calls. Use it on single-turn rows
(or on turn 1) only.
"""

from __future__ import annotations

from typing import Any


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def called_tool_names(agent_state: dict[str, Any]) -> list[str]:
    """Every tool name the agent called, in call order (duplicates kept)."""
    names: list[str] = []
    for message in agent_state.get("messages") or []:
        for call in _field(message, "tool_calls") or []:
            name = _field(call, "name")
            if name:
                names.append(str(name).strip())
    return names


def _parse_forbidden(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value).split(";")
    return [str(item).strip().lower() for item in items if str(item).strip()]


def evaluate_forbidden_tools(
    agent_state: dict[str, Any],
    expected_forbidden_tools: Any,
) -> dict[str, Any]:
    """Score 1.0 when none of the forbidden tools was called, 0.0 otherwise.

    ``null`` when the row sets no ``forbidden_tools``, and ``null`` when the
    state carries no ``messages`` key at all: without the message list the
    harness cannot tell "called nothing" from "could not see", and an
    unreadable signal must abstain rather than pass (guards.py convention).
    An empty message list is readable and scores.
    """
    result: dict[str, Any] = {
        "forbidden_tools_absent_score": None,
        "actual_forbidden_tools_called": None,
        "actual_tool_names": None,
    }
    forbidden = _parse_forbidden(expected_forbidden_tools)
    if not forbidden:
        return result
    if "messages" not in agent_state:
        result["actual_forbidden_tools_called"] = "no messages in state; abstained"
        return result

    names = called_tool_names(agent_state)
    result["actual_tool_names"] = "; ".join(names) or None
    offending = sorted({n for n in names if n.lower() in forbidden})
    result["forbidden_tools_absent_score"] = 0.0 if offending else 1.0
    result["actual_forbidden_tools_called"] = "; ".join(offending) or None
    return result
