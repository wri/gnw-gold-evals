"""Horizon's side: its stored draft-5 attempts, read back for rescoring.

The 78.4% page names, per question, the run its attempts came from (five
runs on 27 and 28 October). Each attempt's artefact keeps the reply, the
nudge it offered and links to the tables it pulled; the run ledger says
which attempts got no reply. Artefacts are gitignored, so they are read
from the machine that ran draft-5 (``results/benchmark/artifacts``).
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PAGE = Path("results/benchmark/pages/20261028T124051Z_prod.json")
RUNS = Path("results/benchmark/runs")
ARTIFACTS = Path("results/benchmark/artifacts")


@dataclass
class Attempt:
    trial: int
    reply: str = ""
    nudge: dict[str, Any] | None = None
    pulled_links: list[str] = field(default_factory=list)
    no_answer: bool = False


@dataclass
class Question:
    uid: str
    run_id: str
    started: str  # ISO timestamp the run's dates were resolved at
    attempts: list[Attempt]


def _artifact(run_id: str, uid: str, trial: int, root: Path) -> dict[str, Any] | None:
    name = f"{uid}.json.gz" if trial == 1 else f"{uid}_t{trial}.json.gz"
    path = root / run_id / name
    if not path.exists():
        return None
    with gzip.open(path) as handle:
        return json.load(handle)


def load(uids: set[str], page: Path = PAGE, runs: Path = RUNS,
         artifacts: Path = ARTIFACTS) -> dict[str, Question]:
    """Every attempt Horizon made at ``uids`` in the draft-5 result."""
    data = json.loads(page.read_text(encoding="utf-8"))
    started = {s["run_id"]: s["started"] for s in data["run"]["sources"]}
    run_of = {q["uid"]: q["run_id"] for q in data["questions"] if q["uid"] in uids}
    missing = uids - set(run_of)
    if missing:
        raise ValueError(f"{len(missing)} questions are not on the draft-5 page")
    ledgers: dict[str, dict[str, Any]] = {}
    for run_id in set(run_of.values()):
        run = json.loads((runs / f"{run_id}.json").read_text(encoding="utf-8"))
        ledgers[run_id] = {entry["uid"]: entry for entry in run["results"]}
    questions = {}
    for uid, run_id in run_of.items():
        entry = ledgers[run_id][uid]
        attempts = []
        for trial, record in enumerate(entry.get("trials") or [entry], start=1):
            artifact = _artifact(run_id, uid, trial, artifacts) or {}
            attempts.append(Attempt(
                trial=trial,
                reply=str(artifact.get("final_answer") or ""),
                nudge=artifact.get("nudge") if isinstance(artifact.get("nudge"), dict) else None,
                pulled_links=[str(r.get("source_url")) for r in artifact.get("statistics_refs") or []
                              if r.get("source_url")],
                # No artefact for an attempt means it never produced a state.
                no_answer=bool(record.get("no_answer")) or not artifact,
            ))
        questions[uid] = Question(uid, run_id, started[run_id], attempts)
    return questions


def known_area_sources(artifacts: Path = ARTIFACTS) -> tuple[dict[str, str], dict[str, str]]:
    """Every area Horizon picked or offered in draft-5: id -> source, and
    id -> name (names let a judge read an area offer written in prose)."""
    sources: dict[str, str] = {}
    names: dict[str, str] = {}
    for path in artifacts.glob("2026102[78]T*_prod/*.json.gz"):
        with gzip.open(path) as handle:
            artifact = json.load(handle)
        selection = artifact.get("aoi_selection")
        areas = selection.get("aois", []) if isinstance(selection, dict) else []
        nudge = artifact.get("nudge") if isinstance(artifact.get("nudge"), dict) else {}
        if nudge.get("type") == "aoi_choice":
            areas = [*areas, *(nudge.get("data") or [])]
        for area in areas:
            if isinstance(area, dict) and area.get("src_id") and area.get("source"):
                bare = re.sub(r"_[1-5]$", "", str(area["src_id"]))
                sources[bare] = str(area["source"])
                if area.get("name"):
                    names[bare] = str(area["name"])
    return sources, names
