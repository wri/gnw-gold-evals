"""Build a curated BENCHMARK version from a reviewed sheet export.

    uv run python tools/benchmark_from_sheet.py \\
        --seed seeds/benchmark-v2026-proposed.csv --version 2026-draft-2

Where ``benchmark_sample.py`` draws a stratified sample, a curated version
is a list someone chose: each sheet row names a CHALLENGE case
(``challenge_id``, or a new case carrying ``notes.benchmark_id``) plus the
use-case facets the page groups by. The tool does two things:

1. **Tags the cases.** Each member case gets ``notes`` for its sheet row:
   ``benchmark_id``, ``benchmark_type``, ``jtbd``, ``impact_pathway``,
   ``user_groups``, ``user_story_refs``, ``synthetic``, ``refresh_risk``.
   Notes are unhashed, so tagging never changes a uid.
2. **Writes the manifest** (``benchmarks/<version>.json``, contract in
   ``goldset.benchmark``). Rows whose case is not ``ready`` are left out and
   listed under ``sampling.excluded`` with the case's status reason.

Type mapping from the sheet's ``benchmark_query_type`` onto the page's axis:
quantification, comparison, trend, monitoring and causal map to themselves;
``spatial`` splits by store set (aoi -> geospatial, dataset -> dataset);
``scope`` (refuse or clarify) -> refusal. Impact pathways are stored by
number ("x" = cross-cutting); JTBD numbers as given. A frozen manifest is
never rewritten.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_sample import stages_for  # noqa: E402

from goldset.benchmark import (  # noqa: E402
    QUERY_TYPES,
    SCHEMA_VERSION,
    STAGE_ORDER,
    from_dict,
    render,
)
from goldset.store import Case, load_store, read_manifest, write_case  # noqa: E402

DIRECT = {"quantification", "comparison", "trend", "monitoring", "causal"}


def member_type(sheet_type: str, case: Case) -> str:
    if sheet_type in DIRECT:
        return sheet_type
    if sheet_type == "spatial":
        return {"aoi": "geospatial", "dataset": "dataset"}[case.set]
    if sheet_type == "scope":
        return "refusal"
    raise SystemExit(f"{case.id}: unknown benchmark_query_type {sheet_type!r}")


def parse_pathways(text: str) -> list[str]:
    if text.strip().lower().startswith("cross-cutting"):
        return ["x"]
    found = sorted(set(re.findall(r"(?:^|;\s*)([1-5])\b", text)))
    if not found:
        raise SystemExit(f"unparseable impact_pathway {text!r}")
    return found


def parse_jobs(text: str) -> list[str]:
    jobs = [j.strip() for j in text.split(",") if j.strip()]
    return sorted(set(jobs), key=int)


def parse_groups(text: str) -> list[str]:
    return [g.strip() for g in text.split(";") if g.strip()]


def tag(case: Case, row: dict) -> Case:
    notes = dict(case.notes)
    notes.update({
        "benchmark_id": row["benchmark_id"],
        "benchmark_type": row["benchmark_query_type"],
        "jtbd": row["jtbd"],
        "impact_pathway": row["impact_pathway"],
        "user_groups": row["user_groups"],
        "synthetic": "TRUE" if row["synthetic"].upper() == "TRUE" else "FALSE",
    })
    for key in ("user_story_refs", "refresh_risk"):
        if row.get(key):
            notes[key] = row[key]
    return Case(id=case.id, status=case.status, group=case.group, query=case.query,
                expected=case.expected, notes=notes, turns=case.turns, set=case.set)


def build(seed: Path, cases_dir: Path, version: str, created: str, write_tags: bool) -> dict:
    store = [(p, c) for p, c, _u in load_store(cases_dir)]
    by_id = {c.id: c for _p, c in store}
    by_bid = {c.notes.get("benchmark_id"): c for _p, c in store if c.notes.get("benchmark_id")}
    members, excluded = [], []
    for row in csv.DictReader(seed.open(encoding="utf-8")):
        case = by_id.get(row["challenge_id"]) if row["challenge_id"] else by_bid.get(row["benchmark_id"])
        if case is None:
            raise SystemExit(f"{row['benchmark_id']}: no CHALLENGE case found")
        tagged = tag(case, row)
        if write_tags and tagged.notes != case.notes:
            write_case(cases_dir, tagged)
        if case.status != "ready":
            excluded.append({"benchmark_id": row["benchmark_id"], "id": case.id,
                             "status": case.status,
                             "reason": case.notes.get("status_reason", "")})
            continue
        members.append({
            "uid": case.uid,
            "id": case.id,
            "type": member_type(row["benchmark_query_type"], case),
            "set": case.set,
            "cohort": case.group,
            "difficulty": case.notes.get("difficulty", ""),
            "stages": stages_for(case),
            "benchmark_id": row["benchmark_id"],
            "jobs": parse_jobs(row["jtbd"]),
            "pathways": parse_pathways(row["impact_pathway"]),
            "user_groups": parse_groups(row["user_groups"]),
            "synthetic": row["synthetic"].upper() == "TRUE",
        })
    manifest = read_manifest(cases_dir) or {}
    measured = {m["type"] for m in members}
    return {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "status": "draft",
        "created": created,
        "frozen": None,
        "source": {"cases_dir": cases_dir.as_posix(),
                   "caseset_version": manifest.get("caseset_version")},
        "sampling": {
            "tool": "tools/benchmark_from_sheet.py",
            "method": "curated: one member per sheet row",
            "seed_file": seed.as_posix(),
            "excluded": excluded,
        },
        "stage_order": list(STAGE_ORDER),
        "types": [{**t, "measured": t["key"] in measured} for t in QUERY_TYPES],
        "members": members,
        "errata": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/challenge"))
    parser.add_argument("--out-dir", type=Path, default=Path("benchmarks"))
    parser.add_argument("--no-tag", action="store_true",
                        help="build the manifest without writing case notes")
    args = parser.parse_args()
    out = args.out_dir / f"{args.version}.json"
    import json
    existing = from_dict(json.loads(out.read_text(encoding="utf-8"))) if out.exists() else None
    if existing and existing.status != "draft":
        print(f"{out} is {existing.status}: frozen manifests are never rewritten")
        return 1
    created = existing.raw.get("created") if existing else date.today().isoformat()
    data = build(args.seed, args.cases_dir, args.version, created, not args.no_tag)
    if existing:
        data["errata"] = existing.raw.get("errata", [])
    problems = from_dict(data).validate()
    if problems:
        raise SystemExit("; ".join(problems))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"wrote {out}: {len(data['members'])} members, {len(data['sampling']['excluded'])} excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
