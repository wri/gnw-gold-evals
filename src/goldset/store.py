"""The on-disk case store: one YAML file per case, plus a generated manifest.

Layout::

    cases/<version>/           # v1 (frozen baseline) or v2 (working set)
      MANIFEST.json            # generated: caseset_version and an id-to-uid index
      <group-slug>/<id>.yaml   # one case per file

Stores whose cases carry the optional ``set`` field (CHALLENGE) gain one
directory level — ``<set-slug>/<group-slug>/<id>.yaml`` — so new sets can
sit side by side (``aoi/``, ...). ``set`` is organisational like ``group``:
never hashed into the uid, so assigning or renaming it mints no versions.

Case files are the source of truth and are edited by hand. After any edit,
follow the after-edit ritual in README.md, "Changing cases": its first step,
``tools/check.py --fix``, recomputes uids and the manifest, and
``tools/check.py`` alone verifies them (CI runs it). ``write_case`` output is
deterministic, so rewriting an unchanged case produces a byte-identical file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from goldset.canonical import (
    LANGUAGES,
    case_uid,
    caseset_version,
    conversation_uid,
    normalize_text,
)
from goldset.runner.multiturn import SNAPSHOT_FIELDS

MANIFEST_NAME = "MANIFEST.json"
# Per-store identity rule, recorded in MANIFEST.json: when true, multi-turn
# uids also hash each turn's deltas (see canonical.conversation_uid). Absent
# means false, which keeps the frozen cases/v1 uids exactly as imported.
UID_INCLUDES_DELTAS = "uid_includes_deltas"

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


_DELTA_KINDS = ("changed", "retain", "absent")


@dataclass(frozen=True)
class Case:
    """A single GOLD case. Frozen: edits produce a new instance.

    Single-turn cases carry ``query`` + ``expected``. Multi-turn cases
    carry ``turns`` instead: a list of ``{query, expected, deltas}``
    dicts, where ``deltas`` (turn >= 2 only) asserts state transitions
    between turns (``changed`` / ``retain`` / ``absent`` field lists).

    ``uid_includes_deltas`` is the owning store's identity rule (its
    manifest flag), not case content: it is never written to the YAML, and
    ``load_store`` sets it from the store's manifest.
    """

    id: str
    status: str
    group: str
    query: str = ""
    expected: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    turns: tuple = ()
    set: str = ""  # optional hierarchy level above group (e.g. CHALLENGE "aoi")
    uid_includes_deltas: bool = False
    language: str = "en"  # the query's language; part of the uid unless "en"
    twin: str = ""  # id of the English case that shares this case's expectations

    @property
    def is_multiturn(self) -> bool:
        return bool(self.turns)

    @property
    def uid(self) -> str:
        if self.is_multiturn:
            return conversation_uid(
                self.turns, include_deltas=self.uid_includes_deltas
            )
        return case_uid(self.query, self.expected, self.language)

    def _validate_turns(self) -> list[str]:
        label = self.id or "?"
        problems = []
        if normalize_text(self.query) or self.expected:
            problems.append(f"{label}: multi-turn cases must not set query/expected")
        if len(self.turns) < 2:
            problems.append(f"{label}: multi-turn cases need at least 2 turns")
        for index, turn in enumerate(self.turns, start=1):
            if not isinstance(turn, dict):
                problems.append(f"{label}: turn {index} is not a mapping")
                continue
            if set(turn) - {"query", "expected", "deltas"}:
                problems.append(f"{label}: turn {index} has unknown keys")
            if not normalize_text(turn.get("query")):
                problems.append(f"{label}: turn {index} has an empty query")
            deltas = turn.get("deltas") or {}
            if deltas and index == 1:
                problems.append(f"{label}: turn 1 cannot assert deltas")
            if set(deltas) - set(_DELTA_KINDS):
                problems.append(f"{label}: turn {index} has unknown delta kinds")
            for kind in _DELTA_KINDS:
                fields = deltas.get(kind) or []
                if not isinstance(fields, (list, tuple)):
                    problems.append(
                        f"{label}: turn {index} deltas.{kind} must be a list"
                    )
                    continue
                unknown_fields = sorted(
                    str(field) for field in fields if field not in SNAPSHOT_FIELDS
                )
                if unknown_fields:
                    problems.append(
                        f"{label}: turn {index} deltas.{kind} has unknown "
                        f"fields {unknown_fields} (valid: "
                        f"{sorted(SNAPSHOT_FIELDS)})"
                    )
        return problems

    def validate(self) -> list[str]:
        """Return a list of problems; empty means the case is well-formed."""
        problems = []
        if not normalize_text(self.id):
            problems.append("missing id")
        if not normalize_text(self.status):
            problems.append(f"{self.id or '?'}: missing status")
        if self.is_multiturn:
            problems += self._validate_turns()
        elif not normalize_text(self.query):
            problems.append(f"{self.id or '?'}: empty query")
        if self.language not in LANGUAGES:
            problems.append(
                f"{self.id or '?'}: language {self.language!r} is not one of "
                f"{LANGUAGES}"
            )
        elif self.language != "en" and self.is_multiturn:
            # A multi-turn uid does not cover the language.
            problems.append(f"{self.id or '?'}: multi-turn cases must be in English")
        if self.twin and self.language == "en":
            problems.append(
                f"{self.id or '?'}: only a case in another language names a twin"
            )
        if self.twin and self.twin == self.id:
            problems.append(f"{self.id or '?'}: a case cannot be its own twin")
        for mapping, label in ((self.expected, "expected"), (self.notes, "notes")):
            for key, value in mapping.items():
                if not isinstance(value, str):
                    problems.append(
                        f"{self.id or '?'}: {label}.{key} is {type(value).__name__},"
                        " expected string"
                    )
        return problems


def group_slug(group: str) -> str:
    """Directory-safe slug for a test_group value; empty groups collect
    under ``ungrouped``."""
    slug = _SLUG_RE.sub("-", normalize_text(group).lower().replace(" ", "-"))
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-") or "ungrouped"


def case_to_dict(case: Case) -> dict:
    """Serialisable mapping in stable key order; empty sections dropped."""
    data: dict = {
        "id": case.id,
        "uid": case.uid,
        "status": case.status,
    }
    if case.set:
        data["set"] = case.set
    data["group"] = case.group
    if case.language != "en":
        data["language"] = case.language
    if case.twin:
        data["twin"] = case.twin
    if case.is_multiturn:
        data["turns"] = [dict(turn) for turn in case.turns]
    else:
        data["query"] = case.query
        data["expected"] = {
            k: v for k, v in case.expected.items() if normalize_text(v)
        }
    notes = {k: v for k, v in case.notes.items() if normalize_text(v)}
    if notes:
        data["notes"] = notes
    return data


def case_path(root: Path, case: Case) -> Path:
    if case.set:
        return root / group_slug(case.set) / group_slug(case.group) / f"{case.id}.yaml"
    return root / group_slug(case.group) / f"{case.id}.yaml"


def write_case(root: Path, case: Case) -> Path:
    problems = case.validate()
    if problems:
        raise ValueError(f"refusing to write invalid case: {problems}")
    path = case_path(root, case)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        case_to_dict(case), sort_keys=False, allow_unicode=True, width=88
    )
    path.write_text(text, encoding="utf-8")
    return path


def read_case(path: Path, uid_includes_deltas: bool = False) -> tuple[Case, str]:
    """Load a case file. Returns (case, stored_uid): the stored uid is what
    the file claims; ``case.uid`` is what the content hashes to. A mismatch
    means the file was edited without running ``check.py --fix``.
    ``uid_includes_deltas`` is the owning store's identity rule."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: not a mapping")
    unknown = set(raw) - {
        "id", "uid", "status", "set", "group", "language", "twin", "query",
        "expected", "notes", "turns",
    }
    if unknown:
        raise ValueError(f"{path}: unknown top-level keys {sorted(unknown)}")
    turns = tuple(
        {
            "query": str(turn.get("query", "")),
            "expected": {
                str(k): str(v) for k, v in (turn.get("expected") or {}).items()
            },
            **({"deltas": turn["deltas"]} if turn.get("deltas") else {}),
        }
        for turn in (raw.get("turns") or [])
        if isinstance(turn, dict)
    )
    case = Case(
        id=str(raw.get("id", "")),
        status=str(raw.get("status", "")),
        set=str(raw.get("set", "")),
        group=str(raw.get("group", "")),
        query=str(raw.get("query", "")),
        expected={str(k): str(v) for k, v in (raw.get("expected") or {}).items()},
        notes={str(k): str(v) for k, v in (raw.get("notes") or {}).items()},
        turns=turns,
        uid_includes_deltas=uid_includes_deltas,
        language=str(raw.get("language", "en")),
        twin=str(raw.get("twin", "")),
    )
    return case, str(raw.get("uid", ""))


def store_uid_includes_deltas(root: Path) -> bool:
    """The store's ``uid_includes_deltas`` manifest flag; absent is False."""
    value = (read_manifest(root) or {}).get(UID_INCLUDES_DELTAS, False)
    if not isinstance(value, bool):
        raise ValueError(
            f"{root / MANIFEST_NAME}: {UID_INCLUDES_DELTAS} must be true or "
            f"false, not {value!r}"
        )
    return value


def load_store(
    root: Path, uid_includes_deltas: bool | None = None
) -> list[tuple[Path, Case, str]]:
    """All cases under ``root``, sorted by path for determinism. Their uids
    follow the store's manifest flag unless ``uid_includes_deltas`` is given
    (``check.py --fix --uid-includes-deltas`` turning the rule on)."""
    if uid_includes_deltas is None:
        uid_includes_deltas = store_uid_includes_deltas(root)
    entries = []
    for path in sorted(root.rglob("*.yaml")):
        case, stored_uid = read_case(path, uid_includes_deltas)
        entries.append((path, case, stored_uid))
    return entries


def build_manifest(
    cases: list[Case], source: str, uid_includes_deltas: bool = False
) -> dict:
    """Deterministic manifest: set version + per-case index, sorted by id.
    The ``uid_includes_deltas`` key is written only when true, so a store
    without the rule (cases/v1) keeps a byte-identical manifest."""
    mismatched = sorted(
        c.id for c in cases if c.uid_includes_deltas != uid_includes_deltas
    )
    if mismatched:
        raise ValueError(
            f"cases {mismatched} were loaded with a different "
            f"{UID_INCLUDES_DELTAS} rule than this manifest records "
            f"({uid_includes_deltas}); their uids would not match"
        )
    ordered = sorted(cases, key=lambda c: c.id)
    manifest: dict = {
        "caseset_version": caseset_version(c.uid for c in ordered),
        "case_count": len(ordered),
        "source": source,
    }
    if uid_includes_deltas:
        manifest[UID_INCLUDES_DELTAS] = True
    manifest["cases"] = [
        {
            "id": c.id,
            "uid": c.uid,
            **({"set": c.set} if c.set else {}),
            "group": c.group,
            "status": c.status,
        }
        for c in ordered
    ]
    return manifest


def write_manifest(root: Path, manifest: dict) -> Path:
    path = root / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def read_manifest(root: Path) -> dict | None:
    path = root / MANIFEST_NAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
