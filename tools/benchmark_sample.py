"""Sample a BENCHMARK version from the CHALLENGE store.

    uv run python tools/benchmark_sample.py --version 2026-draft

Writes ``benchmarks/<version>.json`` (contract: ``goldset.benchmark``).
Sampling is deterministic: the same store, seed and rules give a
byte-identical manifest. Regenerating is a deliberate act, never CI's: a
manifest's membership only changes when someone re-runs this and commits
the diff, so a CHALLENGE edit cannot silently reshuffle even a draft
(``tools/check_benchmark.py`` reports members it knocked out instead).
Re-running over an existing draft reuses its seed, per-type count,
creation date and errata. A frozen manifest is never regenerated.

Rules (AJ, 2026-09-29):

- ``--per-type`` members (default 20) for every measured query type
  (``goldset.benchmark.QUERY_TYPES`` with sets), from ``ready`` cases only.
- Geospatial (aoi) and Dataset draw from **easy + medium only**: the hard
  cohorts are extremely hard and would pin the North Star to the frontier
  rather than track improvement. Sets without difficulty labels
  (the numeric intents) are unfiltered.
- Strata: difficulty x cohort where the set labels difficulty, cohort
  otherwise. Slots are allocated proportionally by largest remainder, with
  ties broken by stratum name; cases within a stratum are drawn by a
  seeded shuffle of uid-sorted cases, so only the seed, not file order,
  decides membership.
- Per member, the pipeline stages it exercises are frozen from the checks
  its expectations imply (dedicated and shared buckets alike), which makes
  the type x stage coverage matrix a pure read of the manifest.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.benchmark import (  # noqa: E402
    QUERY_TYPES,
    SCHEMA_VERSION,
    STAGE_ORDER,
    from_dict,
    render,
)
from goldset.buckets import buckets_for, implied_checks_for_case  # noqa: E402
from goldset.store import Case, load_store, read_manifest  # noqa: E402

DIFFICULTY_FILTER = {"aoi": ("easy", "medium"), "dataset": ("easy", "medium")}


def stages_for(case: Case) -> list[str]:
    exercised = {b for check in implied_checks_for_case(case) for b in buckets_for(check)}
    return [s for s in STAGE_ORDER if s in exercised]


def eligible(cases: list[Case], set_name: str) -> list[Case]:
    allowed = DIFFICULTY_FILTER.get(set_name)
    pool = [c for c in cases if c.set == set_name and c.status == "ready"
            and not c.is_multiturn]
    if allowed:
        pool = [c for c in pool if c.notes.get("difficulty") in allowed]
    return pool


def stratum_of(case: Case) -> str:
    difficulty = case.notes.get("difficulty", "")
    return f"{difficulty}/{case.group}" if difficulty else case.group


def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Largest-remainder proportional allocation of n slots over strata,
    capped by stratum size; deterministic tie-break by stratum name."""
    total = sum(sizes.values())
    if n >= total:
        return dict(sizes)
    quotas = {k: n * v / total for k, v in sizes.items()}
    alloc = {k: int(q) for k, q in quotas.items()}
    order = sorted(sizes, key=lambda k: (-(quotas[k] - alloc[k]), k))
    for k in order[: n - sum(alloc.values())]:
        alloc[k] += 1
    return alloc


def sample_type(cases: list[Case], set_name: str, per_type: int, seed: int) -> list[Case]:
    strata: dict[str, list[Case]] = defaultdict(list)
    for case in eligible(cases, set_name):
        strata[stratum_of(case)].append(case)
    alloc = allocate({k: len(v) for k, v in strata.items()}, per_type)
    chosen: list[Case] = []
    for name in sorted(strata):
        pool = sorted(strata[name], key=lambda c: c.uid)
        random.Random(f"{seed}:{set_name}:{name}").shuffle(pool)
        chosen += pool[: alloc[name]]
    return sorted(chosen, key=lambda c: c.id)


def build(cases_dir: Path, version: str, per_type: int, seed: int,
          created: str) -> dict:
    cases = [case for _p, case, _u in load_store(cases_dir)]
    manifest = read_manifest(cases_dir) or {}
    members = []
    strata_record: dict[str, dict[str, int]] = {}
    for qtype in QUERY_TYPES:
        for set_name in qtype["sets"]:
            chosen = sample_type(cases, set_name, per_type, seed)
            if not chosen:
                continue  # no eligible cases yet: the type stays unmeasured
            if len(chosen) < per_type:
                raise SystemExit(
                    f"{set_name}: only {len(chosen)} eligible cases for "
                    f"{per_type} slots"
                )
            counts: dict[str, int] = defaultdict(int)
            for case in chosen:
                counts[stratum_of(case)] += 1
                members.append({
                    "uid": case.uid,
                    "id": case.id,
                    "type": qtype["key"],
                    "set": case.set,
                    "cohort": case.group,
                    "difficulty": case.notes.get("difficulty", ""),
                    "stages": stages_for(case),
                })
            strata_record[qtype["key"]] = dict(sorted(counts.items()))
    return {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "status": "draft",
        "created": created,
        "frozen": None,
        "source": {
            "cases_dir": cases_dir.as_posix(),
            "caseset_version": manifest.get("caseset_version"),
        },
        "sampling": {
            "tool": "tools/benchmark_sample.py",
            "method": "stratified, largest-remainder proportional allocation",
            "per_type": per_type,
            "seed": seed,
            "eligible": "status ready; aoi and dataset restricted to difficulty easy/medium",
            "strata": "difficulty/cohort where the set labels difficulty, else cohort",
            "allocation": strata_record,
        },
        "stage_order": list(STAGE_ORDER),
        "types": [
            {**t, "measured": t["key"] in strata_record} for t in QUERY_TYPES
        ],
        "members": members,
        "errata": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/challenge"))
    parser.add_argument("--out-dir", type=Path, default=Path("benchmarks"))
    parser.add_argument("--per-type", type=int, default=None,
                        help="default 20, or the existing draft's value")
    parser.add_argument("--seed", type=int, default=None,
                        help="default 2026, or the existing draft's value")
    args = parser.parse_args()

    out = args.out_dir / f"{args.version}.json"
    existing = from_dict(json.loads(out.read_text(encoding="utf-8"))) if out.exists() else None
    if existing and existing.status != "draft":
        print(f"{out} is {existing.status}: frozen manifests are never regenerated")
        return 1
    previous = existing.sampling if existing else {}
    per_type = args.per_type or previous.get("per_type", 20)
    seed = args.seed if args.seed is not None else previous.get("seed", 2026)
    created = existing.raw.get("created") if existing else date.today().isoformat()
    data = build(args.cases_dir, args.version, per_type, seed, created)
    if existing:
        data["errata"] = existing.raw.get("errata", [])
    text = render(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}: {len(data['members'])} members")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
