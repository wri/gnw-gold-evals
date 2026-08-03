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
        # A dataset_choice nudge IS a dataset suggestion (H4). The
        # ``suggested_datasets`` state field above is populated in 0 of 1,298
        # retained case-trials: the pick_aoi/pick_dataset -> nudge migration
        # (wri/project-zeno#770) moved suggestion onto the nudge surface, and
        # dataset_choice appears 162 times there. Without this, every row
        # expecting ``suggest`` failed on a field the product no longer writes,
        # so the "suggest" coverage the case set claimed was fictional.
        # aoi_choice and friends remain ``clarify`` — a different class.
        if nudge.get("type") == "dataset_choice":
            return "suggest"
        return "clarify"
    return "none"


def evaluate_scope(agent_state: dict[str, Any], expected_scope: str) -> dict[str, Any]:
    """Score the observed scope class against the expectation.

    ``expected_scope`` accepts ``;``-separated alternatives, matching the
    dataset_id convention (cases/README.md): some rows are legitimately
    either-way and a single pin makes them flap. 1-089 is the reference case —
    its own ``text`` expectation licenses two behaviours ("Refuses … **or**
    acknowledge and caution that TCL is annual"), and the agent does both across
    identical trials, so ``refuse;clarify`` is the honest expectation.

    Any invalid alternative abstains for the whole expectation rather than
    silently scoring on the remainder — a typo must be loud, not lenient.
    """
    result: dict[str, Any] = {"scope_match_score": None, "actual_scope": None}
    alternatives = [
        _EXPECTED_ALIASES.get(part.strip().lower(), part.strip().lower())
        for part in str(expected_scope).split(";")
        if part.strip()
    ]
    if not alternatives:
        return result

    invalid = [alt for alt in alternatives if alt not in VALID_SCOPES]
    if invalid:
        result["actual_scope"] = (
            f"invalid expected_scope {expected_scope!r}; abstained"
        )
        return result

    actual = classify_scope(agent_state)
    result["actual_scope"] = actual
    wanted = {"none" if alt == "refuse" else alt for alt in alternatives}
    result["scope_match_score"] = 1.0 if actual in wanted else 0.0
    return result
