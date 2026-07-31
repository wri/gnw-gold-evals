"""The on-disk case store: one YAML file per case, plus a generated manifest.

Layout::

    cases/
      MANIFEST.json          # generated — caseset_version + id->uid index
      <group-slug>/<id>.yaml # one case per file, PR-reviewable

Case files are the source of truth and are hand-editable. After any edit,
``tools/check.py --fix`` recomputes uids and the manifest; ``tools/check.py``
alone verifies them (CI-friendly). Regeneration is idempotent: importing an
unchanged sheet produces byte-identical files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from goldset.canonical import case_uid, caseset_version, normalize_text

MANIFEST_NAME = "MANIFEST.json"

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True)
class Case:
    """A single GOLD case. Frozen: edits produce a new instance."""

    id: str
    status: str
    group: str
    query: str
    expected: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return case_uid(self.query, self.expected)

    def validate(self) -> list[str]:
        """Return a list of problems; empty means the case is well-formed."""
        problems = []
        if not normalize_text(self.id):
            problems.append("missing id")
        if not normalize_text(self.query):
            problems.append(f"{self.id or '?'}: empty query")
        if not normalize_text(self.status):
            problems.append(f"{self.id or '?'}: missing status")
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
        "group": case.group,
        "query": case.query,
        "expected": {k: v for k, v in case.expected.items() if normalize_text(v)},
    }
    notes = {k: v for k, v in case.notes.items() if normalize_text(v)}
    if notes:
        data["notes"] = notes
    return data


def case_path(root: Path, case: Case) -> Path:
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


def read_case(path: Path) -> tuple[Case, str]:
    """Load a case file. Returns (case, stored_uid) — the stored uid is what
    the file claims; ``case.uid`` is what the content hashes to. A mismatch
    means the file was edited without running ``check.py --fix``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: not a mapping")
    unknown = set(raw) - {"id", "uid", "status", "group", "query", "expected", "notes"}
    if unknown:
        raise ValueError(f"{path}: unknown top-level keys {sorted(unknown)}")
    case = Case(
        id=str(raw.get("id", "")),
        status=str(raw.get("status", "")),
        group=str(raw.get("group", "")),
        query=str(raw.get("query", "")),
        expected={str(k): str(v) for k, v in (raw.get("expected") or {}).items()},
        notes={str(k): str(v) for k, v in (raw.get("notes") or {}).items()},
    )
    return case, str(raw.get("uid", ""))


def load_store(root: Path) -> list[tuple[Path, Case, str]]:
    """All cases under ``root``, sorted by path for determinism."""
    entries = []
    for path in sorted(root.rglob("*.yaml")):
        case, stored_uid = read_case(path)
        entries.append((path, case, stored_uid))
    return entries


def build_manifest(cases: list[Case], source: str) -> dict:
    """Deterministic manifest: set version + per-case index, sorted by id."""
    ordered = sorted(cases, key=lambda c: c.id)
    return {
        "caseset_version": caseset_version(c.uid for c in ordered),
        "case_count": len(ordered),
        "source": source,
        "cases": [
            {"id": c.id, "uid": c.uid, "group": c.group, "status": c.status}
            for c in ordered
        ],
    }


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
