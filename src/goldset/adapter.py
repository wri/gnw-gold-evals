"""Convert a store ``Case`` into the ``ExpectedData`` the evaluators read.

Case YAML stores expectation keys without the ``expected_`` prefix.
``ExpectedData`` wants the prefix and does its own parsing (semicolon lists,
tri-state booleans), so this module only adds the prefix: one parser, not two.

The case uid rides along as a pydantic extra field, but nothing relies on it:
the ledger takes its uid from the stored case (``run_cases`` in ``cli.py``),
because a templated query resolves to different text, and so to a different
uid, at run time.
"""

from __future__ import annotations

from goldset.eval_types import ExpectedData
from goldset.store import Case


def _to_expected(case: Case, expected: dict[str, str]) -> ExpectedData:
    payload = {f"expected_{key}": value for key, value in expected.items()}
    return ExpectedData(
        test_id=case.id,
        test_group=case.group or "unknown",
        status=case.status,
        uid=case.uid,
        **payload,
    )


def case_to_expected(case: Case) -> ExpectedData:
    return _to_expected(case, case.expected)


def turn_to_expected(case: Case, turn: dict) -> ExpectedData:
    """One turn of a multi-turn case, same prefixing rules."""
    return _to_expected(case, turn.get("expected") or {})
