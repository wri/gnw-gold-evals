"""Bridge between the case store and the ported harness types.

``Case.expected`` keys are stored without the ``expected_`` prefix; the
harness's ``ExpectedData`` (ported verbatim from gnw-evals) wants prefixed
fields and applies its own parsing (semicolon splits, tri-state booleans).
The adapter re-prefixes and lets those validators do exactly what they did
in gnw-evals — no second parsing layer to drift.

The case ``uid`` rides along as a pydantic extra field (both harness models
are ``extra="allow"``), so it flows untouched through ``run_test`` into the
``TestResult`` and out to the ledger.
"""

from __future__ import annotations

from goldset.eval_types import ExpectedData
from goldset.store import Case


def case_to_expected(case: Case) -> ExpectedData:
    payload = {f"expected_{key}": value for key, value in case.expected.items()}
    return ExpectedData(
        test_id=case.id,
        test_group=case.group or "unknown",
        status=case.status,
        uid=case.uid,
        **payload,
    )
