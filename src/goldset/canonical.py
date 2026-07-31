"""Content-addressed identity for GOLD cases.

A case's ``uid`` is a truncated SHA-256 over a canonical JSON serialisation
of its query plus every non-empty expectation. Editing the prompt or any
expected value therefore mints a new uid; metadata (status, group, notes)
does not participate, so triage annotations never masquerade as a new
version of the test.

The ``caseset_version`` is a hash over the sorted uids of every case in the
store: any edit to any case, or adding/removing one, changes the set
version. Results ledgers key on both, so a score is always pinned to the
exact case content it ran against.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

UID_LENGTH = 16


def normalize_text(value: object) -> str:
    """Normalise a cell value for hashing: str, unified newlines, stripped."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def canonical_payload(query: str, expected: Mapping[str, object]) -> str:
    """Deterministic JSON string a case uid is computed over.

    Empty expectations are dropped so that adding a blank column to the
    source never changes identity. Key order never matters.
    """
    clean = {key: normalize_text(value) for key, value in expected.items()}
    clean = {key: value for key, value in clean.items() if value}
    payload = {"expected": clean, "query": normalize_text(query)}
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def case_uid(query: str, expected: Mapping[str, object]) -> str:
    """uid = sha256(canonical payload), truncated to UID_LENGTH hex chars."""
    digest = hashlib.sha256(
        canonical_payload(query, expected).encode("utf-8")
    ).hexdigest()
    return digest[:UID_LENGTH]


def conversation_uid(turns: Iterable[Mapping[str, object]]) -> str:
    """uid for a multi-turn case: hash over every turn's query + expected,
    **in order** — turn order is test content, so reordering turns mints a
    new version. Delta assertions and metadata do not participate, matching
    the single-turn rule that annotations never mint versions."""
    payload = json.dumps(
        [
            json.loads(
                canonical_payload(
                    str(turn.get("query", "")),
                    turn.get("expected") or {},  # type: ignore[arg-type]
                )
            )
            for turn in turns
        ],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:UID_LENGTH]


def caseset_version(uids: Iterable[str]) -> str:
    """Version of the whole set: hash of the sorted uids, order-insensitive."""
    joined = "\n".join(sorted(uids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:UID_LENGTH]
