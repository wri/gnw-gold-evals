"""Build a curated BENCHMARK version from a reviewed sheet export.

    uv run python tools/benchmark_from_sheet.py \\
        --seed seeds/benchmark-v2026-bef-2026-10-22.csv --version 2026-draft-3

Where ``benchmark_sample.py`` draws a stratified sample, a curated version
is a list someone chose: each sheet row names a CHALLENGE case plus the
use-case facets the page groups by. A row resolves to its case by
``challenge_id`` or, for a synthetic row without one, by its exact query
text (sheets renumber ``benchmark_id`` between drafts, so the id is never
used to find a case). The tool does two things:

1. **Tags the cases.** Each member case gets ``notes`` for its sheet row
   (``benchmark_id``, ``benchmark_type``, the use-case facets, ``synthetic``,
   ``user_story_refs``, ``refresh_risk``), and cases that carry a
   ``benchmark_id`` but are not in the sheet lose their membership notes.
   Notes are unhashed, so tagging never changes a uid.
2. **Writes the manifest** (``benchmarks/<version>.json``, contract in
   ``goldset.benchmark``). Rows whose case is not ``ready`` are left out and
   listed under ``sampling.excluded`` with the case's status reason.

Two sheet layouts are read, told apart by their type column:

- ``benchmark_query_type`` (the proposed set, 2026-draft-2): JTBD jobs,
  impact pathways (stored by number, "x" = cross-cutting) and user groups.
- ``query_type`` (the BEF set, from 2026-draft-3): priority use cases
  ``UC1``..``UC6`` (one Y/blank column each), plus engagement, AOI type,
  capability and grounding as case notes.

Type mapping onto the page's axis: quantification, comparison, trend,
monitoring, causal and portfolio map to themselves; ``spatial`` splits by
store set (aoi -> geospatial, dataset -> dataset); ``scope`` (refuse or
clarify) -> refusal. A frozen manifest is never rewritten.
"""

from __future__ import annotations

import argparse
import csv
import json
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
    USE_CASES,
    from_dict,
    render,
)
from goldset.store import Case, load_store, read_manifest, write_case  # noqa: E402

DIRECT = {"quantification", "comparison", "trend", "monitoring", "causal", "portfolio"}
# Notes that record membership of a sheet rather than facts about the case;
# removed from cases the current sheet no longer lists.
MEMBERSHIP_NOTES = ("benchmark_id", "benchmark_type", "jtbd", "impact_pathway",
                    "user_groups", "use_cases", "engagement", "aoi_type",
                    "capability", "grounding")


def member_type(sheet_type: str, case: Case) -> str:
    if sheet_type in DIRECT:
        return sheet_type
    if sheet_type == "spatial":
        return {"aoi": "geospatial", "dataset": "dataset"}[case.set]
    if sheet_type == "scope":
        return "refusal"
    raise SystemExit(f"{case.id}: unknown benchmark query type {sheet_type!r}")


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


def parse_use_cases(row: dict) -> list[str]:
    marked = [uc for uc in USE_CASES if row.get(uc, "").strip().upper() == "Y"]
    if not marked:
        raise SystemExit(f"{row['benchmark_id']}: no use case marked")
    tags = {t.strip() for t in row.get("tags", "").split(";") if t.strip()}
    if tags and tags != set(marked):
        raise SystemExit(f"{row['benchmark_id']}: tags {sorted(tags)} disagree with UC columns {marked}")
    return marked


def is_bef(row: dict) -> bool:
    return "query_type" in row


def sheet_type(row: dict) -> str:
    return row["query_type"] if is_bef(row) else row["benchmark_query_type"]


def is_synthetic(row: dict) -> bool:
    if is_bef(row):
        return row["source"].strip().lower().startswith("new")
    return row["synthetic"].upper() == "TRUE"


def row_notes(row: dict) -> dict[str, str]:
    notes = {
        "benchmark_id": row["benchmark_id"],
        "benchmark_type": sheet_type(row),
        "synthetic": "TRUE" if is_synthetic(row) else "FALSE",
    }
    if is_bef(row):
        notes["use_cases"] = ";".join(parse_use_cases(row))
        for key in ("engagement", "aoi_type", "capability", "grounding"):
            if row.get(key, "").strip():
                notes[key] = row[key].strip()
        refs = row.get("story_refs", "")
    else:
        notes.update({"jtbd": row["jtbd"], "impact_pathway": row["impact_pathway"],
                      "user_groups": row["user_groups"]})
        refs = row.get("user_story_refs", "")
    if refs.strip():
        notes["user_story_refs"] = refs.strip()
    if row.get("refresh_risk", "").strip():
        notes["refresh_risk"] = row["refresh_risk"].strip()
    return notes


def row_facets(row: dict) -> dict:
    if is_bef(row):
        return {"use_cases": parse_use_cases(row)}
    return {"jobs": parse_jobs(row["jtbd"]),
            "pathways": parse_pathways(row["impact_pathway"]),
            "user_groups": parse_groups(row["user_groups"])}


def with_notes(case: Case, notes: dict[str, str]) -> Case:
    return Case(id=case.id, status=case.status, group=case.group, query=case.query,
                expected=case.expected, notes=notes, turns=case.turns, set=case.set)


def tag(case: Case, row: dict) -> Case:
    notes = {k: v for k, v in case.notes.items() if k not in MEMBERSHIP_NOTES}
    notes.update(row_notes(row))
    return with_notes(case, notes)


def untag(case: Case) -> Case:
    return with_notes(case, {k: v for k, v in case.notes.items() if k not in MEMBERSHIP_NOTES})


def _query_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def resolve(row: dict, by_id: dict[str, Case], by_query: dict[str, Case]) -> Case:
    if row.get("challenge_id", "").strip():
        case = by_id.get(row["challenge_id"].strip())
        if case is None:
            raise SystemExit(f"{row['benchmark_id']}: challenge_id {row['challenge_id']} not in the store")
        if _query_key(case.query) != _query_key(row["query"]):
            raise SystemExit(f"{row['benchmark_id']}: {case.id}'s query differs from the sheet's")
        return case
    case = by_query.get(_query_key(row["query"]))
    if case is None:
        raise SystemExit(f"{row['benchmark_id']}: no CHALLENGE case has this query: {row['query']!r}")
    return case


def build(seed: Path, cases_dir: Path, version: str, created: str, write_tags: bool) -> dict:
    store = [c for _p, c, _u in load_store(cases_dir)]
    by_id = {c.id: c for c in store}
    by_query = {_query_key(c.query): c for c in store if not c.is_multiturn}
    members, excluded, listed = [], [], set()
    for row in csv.DictReader(seed.open(encoding="utf-8-sig")):
        case = resolve(row, by_id, by_query)
        if case.id in listed:
            raise SystemExit(f"{row['benchmark_id']}: {case.id} is listed twice")
        listed.add(case.id)
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
            "type": member_type(sheet_type(row), case),
            "set": case.set,
            "cohort": case.group,
            "difficulty": case.notes.get("difficulty", ""),
            "stages": stages_for(case),
            "benchmark_id": row["benchmark_id"],
            **row_facets(row),
            "synthetic": is_synthetic(row),
        })
    if write_tags:
        for case in store:
            if case.id not in listed and "benchmark_id" in case.notes:
                write_case(cases_dir, untag(case))
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
