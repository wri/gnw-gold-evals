"""Build the languages companion of a BENCHMARK version.

    uv run python tools/benchmark_languages.py \\
        --version 2026-languages --pairs-with 2026

The companion holds the questions in other languages. Each is its own
CHALLENGE case (``language: es`` or ``id``) paired with an English ``twin``
that shares its expectations, so the pair's score gap measures the language
alone. The English version is never changed: the companion names its
members by uid (``twin_uid``) and does not hold them.

Members, from the ``ready`` cases of the store:

- every case in another language, with ``language`` and ``twin_uid``. When
  its twin is an active member of the ``--pairs-with`` version, it takes
  that member's type and optional facets (use cases, jobs, pathways, user
  groups, synthetic), so both halves of a pair sit in the same groups;
- each English twin that is not a member of the ``--pairs-with`` version: a
  new English question written for the pair. It carries no ``twin_uid``,
  because a Spanish and an Indonesian case can share one twin.

A pair with a case that is not ``ready`` is left out and listed under
``sampling.excluded``, and so is a case in another language that names no
twin. A twin that is missing from the store, is not English or holds other
expectations (``goldset.store.twin_problem``) stops the build. Re-running over an
existing draft keeps its creation date, errata and ``pairs_with`` (a flag
that names another version stops the run). A frozen manifest is never
rewritten.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_from_sheet import member_type  # noqa: E402
from benchmark_sample import stages_for  # noqa: E402

from goldset.benchmark import (  # noqa: E402
    QUERY_TYPES,
    SCHEMA_VERSION,
    STAGE_ORDER,
    Benchmark,
    Member,
    from_dict,
    load_benchmark,
    render,
)
from goldset.store import Case, load_store, read_manifest, twin_problem  # noqa: E402

SET_TYPES = {name: t["key"] for t in QUERY_TYPES for name in t["sets"]}


def type_of(case: Case) -> str:
    """The type of a case no sheet row describes: its ``benchmark_type``
    note, read as a sheet type, else the type that measures its set."""
    if case.notes.get("benchmark_type"):
        return member_type(case.notes["benchmark_type"], case)
    if case.set not in SET_TYPES:
        raise SystemExit(f"{case.id}: no query type measures the set {case.set!r}")
    return SET_TYPES[case.set]


def live_facets(case: Case) -> dict:
    return {"uid": case.uid, "id": case.id, "set": case.set, "cohort": case.group,
            "difficulty": case.notes.get("difficulty", ""),
            "stages": tuple(stages_for(case))}


def build(cases_dir: Path, version: str, paired: Benchmark | None,
          created: str) -> dict:
    cases = [case for _p, case, _u in load_store(cases_dir)]
    by_id = {case.id: case for case in cases}
    paired_members = {m.uid: m for m in paired.active_members} if paired else {}
    members: dict[str, Member] = {}
    excluded = []
    for native in sorted(cases, key=lambda c: c.id):
        if native.language == "en":
            continue
        if not native.twin:
            excluded.append({"id": native.id, "twin": "", "status": native.status,
                             "reason": "names no twin"})
            continue
        problem = twin_problem(native, by_id)
        if problem:
            hint = "; run tools/twin_case.py" if "differs" in problem else ""
            raise SystemExit(f"{native.id}: {problem}{hint}")
        twin = by_id[native.twin]
        not_ready = [c for c in (native, twin) if c.status != "ready"]
        if not_ready:
            excluded.append({
                "id": native.id,
                "twin": twin.id,
                "status": not_ready[0].status,
                "reason": not_ready[0].notes.get("status_reason", ""),
            })
            continue
        twin_member = paired_members.get(twin.uid)
        if twin_member is None:
            twin_member = Member(type=type_of(twin), **live_facets(twin))
            members[twin.id] = twin_member
        # The sheet row id stays with the English member it names.
        members[native.id] = replace(
            twin_member, **live_facets(native), benchmark_id="",
            language=native.language, twin_uid=twin.uid,
        )
    if not members and not excluded:
        raise SystemExit(f"{cases_dir}: no case is in another language")
    ordered = [members[key].to_dict() for key in sorted(members)]
    measured = {m["type"] for m in ordered}
    manifest = read_manifest(cases_dir) or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "status": "draft",
        "created": created,
        "frozen": None,
        **({"pairs_with": paired.version} if paired else {}),
        "source": {"cases_dir": cases_dir.as_posix(),
                   "caseset_version": manifest.get("caseset_version")},
        "sampling": {
            "tool": "tools/benchmark_languages.py",
            "method": "every ready case in another language, plus its English "
                      "twin when the paired version does not hold it",
            "excluded": excluded,
        },
        "stage_order": list(STAGE_ORDER),
        "types": [{**t, "measured": t["key"] in measured} for t in QUERY_TYPES],
        "members": ordered,
        "errata": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--pairs-with", default="",
                        help="the English version, in --out-dir, whose members "
                             "the companion pairs with")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/challenge"))
    parser.add_argument("--out-dir", type=Path, default=Path("benchmarks"))
    args = parser.parse_args(argv)
    out = args.out_dir / f"{args.version}.json"
    existing = load_benchmark(out) if out.exists() else None
    if existing and existing.status != "draft":
        print(f"{out} is {existing.status}: frozen manifests are never rewritten")
        return 1
    # A rerun keeps the draft's pairing: dropping it would turn every twin
    # the English version holds into a new member.
    kept = existing.pairs_with if existing else ""
    if args.pairs_with and kept and args.pairs_with != kept:
        raise SystemExit(
            f"{out} pairs with {kept!r}, not {args.pairs_with!r}; "
            "delete the draft to pair it with another version"
        )
    pairs_with = args.pairs_with or kept
    paired = None
    if pairs_with:
        paired_path = args.out_dir / f"{pairs_with}.json"
        if not paired_path.exists():
            raise SystemExit(f"--pairs-with {pairs_with}: no {paired_path}")
        paired = load_benchmark(paired_path)
    created = existing.raw.get("created") if existing else date.today().isoformat()
    data = build(args.cases_dir, args.version, paired, created)
    if existing:
        data["errata"] = existing.raw.get("errata", [])
    problems = from_dict(data).validate()
    if problems:
        raise SystemExit("; ".join(problems))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"wrote {out}: {len(data['members'])} members, "
          f"{len(data['sampling']['excluded'])} excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
