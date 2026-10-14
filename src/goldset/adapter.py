"""Bridge between the case store and the ported harness types.

``Case.expected`` keys are stored without the ``expected_`` prefix; the
harness's ``ExpectedData`` (ported verbatim from gnw-evals) wants prefixed
fields and applies its own parsing (semicolon splits, tri-state booleans).
The adapter re-prefixes and lets those validators do exactly what they did
in gnw-evals — no second parsing layer to drift.

The case ``uid`` rides along as a pydantic extra field (both harness models
are ``extra="allow"``), so it flows untouched through ``run_test`` into the
``TestResult`` and out to the ledger.

Ground truth enters here too, and this is the **only** place it does. A case's
``ground_truth`` selector is already re-prefixed to ``expected_ground_truth`` by
the loop below, like any other expectation; the *values* fetched for it at run
start are not from the case, so they are attached separately and unprefixed.
``ground_truth`` defaults to ``None``, and that default is the guarantee that a
case without one is built exactly as it was before this existed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goldset.eval_types import ExpectedData
from goldset.store import Case

if TYPE_CHECKING:
    from goldset.groundtruth import GroundTruth


def _to_expected(
    case: Case,
    expected: dict[str, str],
    ground_truth: GroundTruth | None = None,
) -> ExpectedData:
    payload = {f"expected_{key}": value for key, value in expected.items()}
    if ground_truth is not None:
        payload["ground_truth_values"] = list(ground_truth.values)
        # "" rather than None so the field keeps its declared str type; an
        # unresolved selector becomes a row error when the check is built.
        payload["ground_truth_unresolved"] = ground_truth.unresolved or ""
    return ExpectedData(
        test_id=case.id,
        test_group=case.group or "unknown",
        status=case.status,
        uid=case.uid,
        **payload,
    )


def case_to_expected(
    case: Case, ground_truth: GroundTruth | None = None
) -> ExpectedData:
    return _to_expected(case, case.expected, ground_truth)


def turn_to_expected(
    case: Case, turn: dict, ground_truth: GroundTruth | None = None
) -> ExpectedData:
    """One turn of a multi-turn case, same prefixing rules.

    Takes ``ground_truth`` for signature parity with ``case_to_expected``; no
    multi-turn case carries a ``ground_truth`` selector today, so it is always
    ``None`` in practice.
    """
    return _to_expected(case, turn.get("expected") or {}, ground_truth)
