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
from pathlib import Path
from typing import Any

from goldset.ledger import read_run
from goldset.plain.reference import bare_id
from goldset.plain.score import Attempt, as_read, offer_key
from goldset.runner.artifacts import artifact_name

PAGE = Path("results/benchmark/pages/20261028T124051Z_prod.json")
RUNS = Path("results/benchmark/runs")
ARTIFACTS = Path("results/benchmark/artifacts")


def _page(page: Path) -> dict[str, Any]:
    return json.loads(page.read_text(encoding="utf-8"))


def _artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with gzip.open(path) as handle:
        return json.load(handle)


def load(uids: set[str], page: Path = PAGE, runs: Path = RUNS,
         artifacts: Path = ARTIFACTS) -> dict[str, tuple[str, list[Attempt]]]:
    """Every attempt Horizon made at ``uids`` in the draft-5 result, with the
    moment its run resolved dates at: uid -> (started, attempts)."""
    data = _page(page)
    started = {s["run_id"]: s["started"] for s in data["run"]["sources"]}
    run_of = {q["uid"]: q["run_id"] for q in data["questions"] if q["uid"] in uids}
    missing = uids - set(run_of)
    if missing:
        raise ValueError(f"{len(missing)} questions are not on the draft-5 page")
    ledgers = {run_id: {entry["uid"]: entry for entry in read_run(runs / f"{run_id}.json")["results"]}
               for run_id in set(run_of.values())}
    questions = {}
    for uid, run_id in run_of.items():
        entry = ledgers[run_id][uid]
        attempts = []
        for trial, record in enumerate(entry.get("trials") or [entry], start=1):
            artifact = _artifact(artifacts / run_id / artifact_name(uid, trial))
            # No artefact means the attempt never produced a state: no reply.
            if record.get("no_answer") or not artifact:
                attempts.append(Attempt(""))
                continue
            nudge = artifact.get("nudge") if isinstance(artifact.get("nudge"), dict) else None
            attempts.append(Attempt(
                text=as_read(str(artifact.get("final_answer") or ""), nudge),
                nudge=nudge,
                pulled=tuple(str(r["source_url"]) for r in artifact.get("statistics_refs") or []
                             if r.get("source_url")),
            ))
        questions[uid] = (started[run_id], attempts)
    return questions


def known_areas(page: Path = PAGE, artifacts: Path = ARTIFACTS
                ) -> tuple[dict[str, str], dict[str, str]]:
    """Every area Horizon picked or offered in the draft-5 runs: bare id ->
    source, and offer key -> name (names let a judge read an area offer
    written in prose)."""
    sources: dict[str, str] = {}
    names: dict[str, str] = {}
    for run in _page(page)["run"]["sources"]:
        for path in (artifacts / run["run_id"]).glob("*.json.gz"):
            artifact = _artifact(path) or {}
            selection = artifact.get("aoi_selection")
            areas = selection.get("aois", []) if isinstance(selection, dict) else []
            nudge = artifact.get("nudge") if isinstance(artifact.get("nudge"), dict) else {}
            if nudge.get("type") == "aoi_choice":
                areas = [*areas, *(nudge.get("data") or [])]
            for area in areas:
                if isinstance(area, dict) and area.get("src_id") and area.get("source"):
                    sources[bare_id(str(area["src_id"]))] = str(area["source"])
                    if area.get("name"):
                        names[offer_key(area["src_id"])] = str(area["name"])
    return sources, names
