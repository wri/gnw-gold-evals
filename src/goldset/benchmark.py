"""BENCHMARK: a frozen, versioned subset of CHALLENGE cases.

CHALLENGE grows and changes; the BENCHMARK does not. A version is one
manifest file, ``benchmarks/<version>.json``, that pins its members by
**uid**. Membership is an act on the set, not on any case, so no case file
carries a tag.

Because a uid is a content hash, editing a member case mints a new uid and
the old one disappears from the store: the member silently drops out of
the benchmark. ``tools/check_benchmark.py`` makes that loud (CI). A broken
member is never edited in place: an erratum voids it, and voided members
leave the denominator of every report of that version.

Everything a report groups by (query type, difficulty, cohort, the
pipeline stages a member exercises) is frozen into the member at sampling
time, so a later taxonomy or case-note change cannot move members between
types mid-version.

This module is the manifest contract only: load, validate, member uids,
and the manifest hash a run records. Sampling lives in
``tools/benchmark_sample.py``; rates are computed by consumers
(``tools/challenge_rollup.py --benchmark``, the FE /evals page).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from goldset.buckets import BUCKETS

SCHEMA_VERSION = 1
STATUSES = ("draft", "frozen", "retired")

# Stakeholder attribution order (AJ, 2026-09-04): a failed question is
# attributed to its earliest failing stage in this order. Distinct from
# goldset.buckets.BUCKETS, whose order is presentational.
STAGE_ORDER = ("scope", "retrieval", "analysis", "explanation", "output")
assert set(STAGE_ORDER) == set(BUCKETS)

# The query-type axis: the FE's 11-type taxonomy (QUERY_TYPES in
# project-zeno-next src/features/evals/model/config.ts) with Spatial split
# into Geospatial (find the place) and Dataset (find the data) — two
# separate types, never pooled (AJ, 2026-09-29). A type with no sets is
# listed so reports can say "not yet measured" rather than omit it.
QUERY_TYPES: tuple[dict[str, Any], ...] = (
    {"key": "refusal", "label": "Refusal", "sets": []},
    {"key": "identification", "label": "Identification", "sets": []},
    {"key": "geospatial", "label": "Geospatial", "sets": ["aoi"]},
    {"key": "dataset", "label": "Dataset", "sets": ["dataset"]},
    {"key": "quantification", "label": "Quantification", "sets": ["quantification"]},
    {"key": "monitoring", "label": "Monitoring", "sets": []},
    {"key": "comparison", "label": "Comparison", "sets": ["comparison"]},
    {"key": "trend", "label": "Trend", "sets": ["trend"]},
    {"key": "conceptual", "label": "Conceptual", "sets": []},
    {"key": "risk", "label": "Risk", "sets": []},
    {"key": "causal", "label": "Causal", "sets": []},
    {"key": "feasibility", "label": "Feasibility", "sets": []},
)

MEMBER_FIELDS = ("uid", "id", "type", "set", "cohort", "difficulty", "stages")


@dataclass(frozen=True)
class Member:
    uid: str
    id: str
    type: str
    set: str
    cohort: str
    difficulty: str  # "" where the source case carries no label
    stages: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "id": self.id,
            "type": self.type,
            "set": self.set,
            "cohort": self.cohort,
            "difficulty": self.difficulty,
            "stages": list(self.stages),
        }


@dataclass(frozen=True)
class Erratum:
    uid: str
    date: str
    reason: str


@dataclass(frozen=True)
class Benchmark:
    version: str
    status: str
    frozen: str | None
    source: dict[str, Any]
    sampling: dict[str, Any]
    types: tuple[dict[str, Any], ...]
    members: tuple[Member, ...]
    errata: tuple[Erratum, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def voided_uids(self) -> set[str]:
        return {e.uid for e in self.errata}

    @property
    def active_members(self) -> tuple[Member, ...]:
        """Members that count: every member not voided by an erratum."""
        voided = self.voided_uids
        return tuple(m for m in self.members if m.uid not in voided)

    @property
    def member_uids(self) -> set[str]:
        return {m.uid for m in self.active_members}

    def validate(self) -> list[str]:
        """Structural problems; empty means well-formed. Store integrity
        (uids exist and are ready) is ``tools/check_benchmark.py``'s job."""
        problems = []
        if not self.version:
            problems.append("missing version")
        if self.status not in STATUSES:
            problems.append(f"status {self.status!r} not in {STATUSES}")
        if self.status == "frozen" and not self.frozen:
            problems.append("a frozen benchmark needs a frozen date")
        type_keys = [t.get("key") for t in self.types]
        if len(set(type_keys)) != len(type_keys):
            problems.append("duplicate type keys")
        seen: set[str] = set()
        for m in self.members:
            if m.uid in seen:
                problems.append(f"{m.id}: duplicate member uid {m.uid}")
            seen.add(m.uid)
            if m.type not in type_keys:
                problems.append(f"{m.id}: unknown type {m.type!r}")
            unknown = [s for s in m.stages if s not in STAGE_ORDER]
            if unknown:
                problems.append(f"{m.id}: unknown stages {unknown}")
        for e in self.errata:
            if e.uid not in seen:
                problems.append(f"erratum {e.uid} does not name a member")
            if not e.date or not e.reason:
                problems.append(f"erratum {e.uid} needs a date and a reason")
        return problems


def manifest_sha(path: Path) -> str:
    """Hash of the manifest bytes, recorded on every benchmark run so a
    reader can tell which manifest (errata included) scored it."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def from_dict(data: dict[str, Any]) -> Benchmark:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"benchmark schema_version {data.get('schema_version')!r}, "
            f"expected {SCHEMA_VERSION}"
        )
    members = []
    for raw in data.get("members", []):
        missing = [k for k in MEMBER_FIELDS if k not in raw]
        if missing:
            raise ValueError(f"member {raw.get('id', '?')} missing {missing}")
        members.append(Member(
            uid=raw["uid"], id=raw["id"], type=raw["type"], set=raw["set"],
            cohort=raw["cohort"], difficulty=raw["difficulty"],
            stages=tuple(raw["stages"]),
        ))
    errata = tuple(
        Erratum(uid=e["uid"], date=e.get("date", ""), reason=e.get("reason", ""))
        for e in data.get("errata", [])
    )
    return Benchmark(
        version=data.get("version", ""),
        status=data.get("status", ""),
        frozen=data.get("frozen"),
        source=data.get("source", {}),
        sampling=data.get("sampling", {}),
        types=tuple(data.get("types", [])),
        members=tuple(members),
        errata=errata,
        raw=data,
    )


def load_benchmark(path: Path) -> Benchmark:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    bench = from_dict(data)
    problems = bench.validate()
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return bench


def render(data: dict[str, Any]) -> str:
    """Deterministic serialisation, so regenerating a manifest from the
    same inputs is a byte-identical no-op."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
