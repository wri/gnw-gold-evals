"""Scope-bucket validator (PR-06 S1): did the agent do the right *kind* of
work — deterministically, from state, replacing reliance on the suite's two
flakiest judges (±0.29 / ±0.23 std over 3 trials) for scope classification.

Observable classes, in precedence order (an agent that pulls data has
analysed, whatever else it also did):

    analyse  — a data pull happened
    suggest  — datasets suggested, no pull
    clarify  — a nudge was issued, no pull
    none     — none of the above (matches an expected ``refuse``)

Known limitation (S3, deferred): on builds without ``send_nudge`` the agent
clarifies in prose and leaves the nudge state empty — that classifies as
``none``. Populate ``expected_scope: clarify`` only on nudge-capable rows.

Evidence: 1-085 ("How do fires impact nature in Spain?") ran a full
analysis when the sheet expected dataset suggestions — caught here as
expected ``suggest`` vs observed ``analyse``.
"""

from __future__ import annotations

from typing import Any

from goldset.evaluators.guards import _data_was_pulled

VALID_SCOPES = ("analyse", "suggest", "clarify", "refuse")

_EXPECTED_ALIASES = {"analyze": "analyse"}


def classify_scope(agent_state: dict[str, Any]) -> str:
    if _data_was_pulled(agent_state):
        return "analyse"
    if agent_state.get("suggested_datasets"):
        return "suggest"
    nudge = agent_state.get("nudge") or {}
    if isinstance(nudge, dict) and nudge.get("type"):
        return "clarify"
    return "none"


def evaluate_scope(agent_state: dict[str, Any], expected_scope: str) -> dict[str, Any]:
    result: dict[str, Any] = {"scope_match_score": None, "actual_scope": None}
    expected = _EXPECTED_ALIASES.get(
        expected_scope.strip().lower(), expected_scope.strip().lower()
    )
    if not expected:
        return result
    if expected not in VALID_SCOPES:
        result["actual_scope"] = f"invalid expected_scope {expected_scope!r}; abstained"
        return result

    actual = classify_scope(agent_state)
    result["actual_scope"] = actual
    wanted = "none" if expected == "refuse" else expected
    result["scope_match_score"] = 1.0 if actual == wanted else 0.0
    return result
