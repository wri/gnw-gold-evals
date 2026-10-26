"""Accepted-nudge validator: a clarifying dataset choice can be a right answer.

Some questions are fairly answered by asking which dataset to use, as long
as the choice offered is the right one. AJ decided on 2026-10-26 (BENCHMARK
draft-4 review, the 16 questions that asked back on every attempt) that such
a case passes when the agent's ``dataset_choice`` nudge offers **every**
dataset the case lists; extra options are allowed. A correct direct pull
still passes, so the case has two paths and each attempt is judged on the
one it took:

- **nudge path**: the attempt ended in a ``dataset_choice`` nudge and pulled
  no data. ``accepted_nudge_match`` scores the offered datasets, and the
  checks that presuppose a pull (``PULL_PATH_CHECKS`` in ``buckets.py``) are
  not applicable, so the runner skips their evaluators and records ``null``.
- **pull path**: anything else. ``accepted_nudge_match`` is ``null`` and the
  usual checks score as before, so a prose ask-back without a nudge still
  fails ``data_pull_exists``.

Datasets are matched by the ``dataset_id`` in the nudge's ``data`` entries,
not by option label: labels overlap ("Tree cover loss" is a substring of
"Tree cover loss by dominant driver"), which is why ``nudge_match`` cannot
express this rule.

Opt-in: it fires only on rows that set ``accept_nudge_offering``
(``;``-separated dataset ids, hashed into the uid), so GOLD is unaffected.
Because attempts can take different paths, ``buckets.row_verdict`` judges
these rows by the majority of attempt verdicts, not by per-check majority.
"""

from __future__ import annotations

from typing import Any

from goldset.evaluators.guards import _data_was_pulled
from goldset.evaluators.utils import normalize_value


def _parse_ids(value: Any) -> set[str]:
    if not value:
        return set()
    return {
        normalize_value(item)
        for item in str(value).split(";")
        if normalize_value(item)
    }


def ended_in_dataset_nudge(agent_state: dict[str, Any]) -> bool:
    """True when the attempt stopped at a dataset_choice nudge with no pull."""
    nudge = agent_state.get("nudge")
    if not isinstance(nudge, dict) or nudge.get("type") != "dataset_choice":
        return False
    return not _data_was_pulled(agent_state)


def takes_nudge_path(agent_state: dict[str, Any], expected_offering: Any) -> bool:
    """Whether this attempt is judged on the nudge path (see module doc)."""
    return bool(_parse_ids(expected_offering)) and ended_in_dataset_nudge(agent_state)


def evaluate_accepted_nudge(
    agent_state: dict[str, Any],
    expected_offering: Any,
) -> dict[str, Any]:
    """Score 1.0 when the nudge offers every listed dataset, 0.0 otherwise.

    ``null`` when the row sets no ``accept_nudge_offering`` and when the
    attempt took the pull path (the pull checks speak for it). Also ``null``
    when a dataset_choice nudge carries no dataset ids at all: the harness
    cannot tell what was offered, and an unreadable signal must abstain
    rather than pass or fail (guards.py convention).
    """
    result: dict[str, Any] = {
        "accepted_nudge_match_score": None,
        "actual_nudge_dataset_ids": None,
    }
    expected = _parse_ids(expected_offering)
    if not expected or not ended_in_dataset_nudge(agent_state):
        return result

    entries = agent_state["nudge"].get("data") or []
    offered = {
        normalize_value(entry.get("dataset_id"))
        for entry in entries
        if isinstance(entry, dict) and normalize_value(entry.get("dataset_id"))
    }
    if not offered:
        result["actual_nudge_dataset_ids"] = (
            "dataset_choice nudge carries no dataset ids; abstained"
        )
        return result

    result["actual_nudge_dataset_ids"] = "; ".join(sorted(offered))
    result["accepted_nudge_match_score"] = 1.0 if expected <= offered else 0.0
    return result
