"""Write the cases of a reviewed language pair sheet into a case store.

    uv run python tools/pairs_from_sheet.py --sheet pt-pairs-reviewed.csv \\
        --language pt --query-column portuguese_query --date 2026-11-25 --dry-run

The sheet is ``<lang>-pairs-reviewed.csv`` from "Adding a language" in
``benchmarks/README.md``. Each row becomes cases in ``--cases-dir``
(``cases/challenge`` by default):

- a ``translated`` row: the question as ``<member id>-<lang>``, with the
  member's set, cohort and ``expected``. The member (``english_id``, which
  must still have the uid ``english_uid``) is its ``twin``.
- a ``native`` row: two cases with one ``expected``, read from the row's
  ``expected_verified`` (one line of YAML; the helper keys ``aoi_name`` and
  ``aoi_source`` are left out, and ``aoi_name`` goes to the notes). The
  English twin takes the next free id of its set (``ch-quant-206``) and the
  question sits beside it (``ch-quant-206-pt``).

Notes: ``lineage`` and ``pair_id`` on every case; ``use_cases`` and
``synthetic``; ``language_review`` on the question only; and on a native
pair ``benchmark_type``, ``verified``, ``precedent`` and ``aoi_name``.
``--date`` is the day the sheet was reviewed and checked, written into the
``lineage``, ``language_review`` and ``verified`` notes.

Every row is checked before anything is written. A problem in any row (an
``UNVERIFIED`` value, a member whose uid is not ``english_uid``, a set and
cohort the store lacks, a ``pair_id`` the sheet repeats or the store already
holds, and so on) is listed, nothing is written and the tool exits 1. The
``pair_id`` check refuses a second run over the same rows, which would write
each native pair again under new ids; to add rows later, pass a sheet that
holds only the new ones. ``--dry-run`` checks and writes nothing.

Then run ``tools/check.py --fix`` and ``tools/coverage_doc.py``, both with
``--cases-dir``, and commit their output with the new cases.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_from_sheet import member_type  # noqa: E402
from benchmark_languages import SET_TYPES, type_of  # noqa: E402

from goldset.benchmark import USE_CASES  # noqa: E402
from goldset.canonical import LANGUAGES  # noqa: E402
from goldset.store import Case, load_store, twin_problem, write_case  # noqa: E402

# Every row needs these; native rows also read ``verify_precedent`` if the
# sheet has it.
COLUMNS = ("pair_id", "kind", "use_case", "type", "set", "cohort", "english_id",
           "english_uid", "english_query", "source", "expected_verified")
# The sheet's query types, as ``benchmark_languages.py`` reads them back from
# ``notes.benchmark_type`` (the BEF sheet's names).
SHEET_TYPE = {"geospatial": "spatial", "dataset": "spatial", "refusal": "scope"}
# Keys of ``expected_verified`` that help the review and no case asserts.
HELPER_KEYS = ("aoi_name", "aoi_source")
VERIFIED = ("expectations checked {day} against 2026 members, the catalog, "
            "local GADM and prod /api/aois; no agent run yet")
NUMBERED = re.compile(r"(?P<prefix>[a-z]+(?:-[a-z]+)*)-(?P<number>\d+)")


def id_prefixes(store: list[Case]) -> tuple[dict[str, str], Counter]:
    """The id prefix of each set (``ch-quant``) and the highest number each
    prefix has used, from the store's numbered English cases."""
    prefixes: dict[str, set[str]] = defaultdict(set)
    highest: Counter = Counter()
    for case in store:
        match = NUMBERED.fullmatch(case.id)
        if match:
            prefixes[case.set].add(match["prefix"])
            highest[match["prefix"]] = max(highest[match["prefix"]],
                                           int(match["number"]))
    return {s: next(iter(p)) for s, p in prefixes.items() if len(p) == 1}, highest


def plan(rows: list[dict], language: str, column: str, day: str,
         store: list[Case]) -> tuple[list[Case], list[str]]:
    """(the cases the sheet makes, the problems that stop it)."""
    by_id = {case.id: case for case in store}
    groups = {(case.set, case.group) for case in store}
    in_store: dict[str, list[str]] = defaultdict(list)
    for case in store:
        if case.notes.get("pair_id"):
            in_store[case.notes["pair_id"]].append(case.id)
    prefixes, highest = id_prefixes(store)
    stored_types: dict[tuple[str, str], set[str]] = defaultdict(set)
    for case in store:
        if case.language == "en" and case.notes.get("benchmark_type"):
            try:
                stored_types[(case.set, case.group)].add(type_of(case))
            except (SystemExit, KeyError):
                pass  # an odd stored case says nothing about which types fit
    repeats = Counter(row["pair_id"].strip() for row in rows)
    review = f"subagent review {day}; native speaker not yet"
    cases: list[Case] = []
    problems: list[str] = []
    for row in rows:
        # A row longer than the header puts its extra cells under None.
        row = {key: (value or "").strip() for key, value in row.items()
               if key is not None}
        pair_id, query = row["pair_id"], row[column]

        def bad(problem: str, pair_id: str = pair_id) -> None:
            problems.append(f"{pair_id or '?'}: {problem}")

        if not pair_id:
            bad("no pair_id")
            continue
        if repeats[pair_id] > 1:
            bad(f"appears {repeats[pair_id]} times in the sheet")
            continue
        if pair_id in in_store:
            bad(f"already in the store ({', '.join(sorted(in_store[pair_id]))})")
            continue
        if not query:
            bad(f"empty {column}")
            continue
        unknown = [u for u in row["use_case"].split(";") if u.strip() not in USE_CASES]
        if unknown:
            bad(f"use case {unknown[0].strip()!r} is not one of {', '.join(USE_CASES)}")
            continue

        if row["kind"] == "translated":
            member = by_id.get(row["english_id"])
            if member is None:
                bad(f"member {row['english_id']} is not in the store")
            elif member.uid != row["english_uid"]:
                bad(f"member {member.id}: its uid is not {row['english_uid']}"
                    f" (it is {member.uid})")
            elif member.language != "en" or member.is_multiturn:
                bad(f"member {member.id} is not a single-turn English case")
            else:
                cases.append(Case(
                    id=f"{member.id}-{language}", status="ready", set=member.set,
                    group=member.group, language=language, twin=member.id,
                    query=query, expected=dict(member.expected),
                    notes={
                        "lineage": f"multilingual BENCHMARK {day}: translation of "
                                   f"{member.id} ({pair_id})",
                        "pair_id": pair_id,
                        "use_cases": member.notes.get("use_cases", row["use_case"]),
                        "language_review": review,
                        "synthetic": member.notes.get("synthetic", ""),
                    },
                ))
            continue
        if row["kind"] != "native":
            bad(f"kind {row['kind']!r} is neither translated nor native")
            continue

        set_, cohort = row["set"], row["cohort"]
        if (set_, cohort) not in groups:
            bad(f"the store has no {set_}/{cohort} (set/cohort)")
            continue
        if not row["english_query"]:
            bad("empty english_query")
            continue
        if "UNVERIFIED" in row["expected_verified"]:
            bad("an expected value is still UNVERIFIED")
            continue
        try:
            # BaseLoader keeps every scalar the text the sheet holds: safe_load
            # would turn NO into False, 0.10 into 0.1 and TRUE into True.
            raw = yaml.load(row["expected_verified"], Loader=yaml.BaseLoader)
        except yaml.YAMLError as error:
            bad(f"expected_verified is not YAML: {error}".splitlines()[0])
            continue
        raw = raw if isinstance(raw, dict) else {}
        nested = [(k, v) for k, v in raw.items() if not isinstance(v, str)]
        if nested:
            key, value = nested[0]
            kind = "a list" if isinstance(value, list) else "a mapping"
            bad(f"expected_verified: {key} is {kind}, not one text value; "
                "quote it ('...') if it is text")
            continue
        expected = {k: v.strip() for k, v in raw.items()
                    if k not in HELPER_KEYS and v.strip()}
        if not expected:
            bad("expected_verified holds no expectation")
            continue
        benchmark_type = SHEET_TYPE.get(row["type"], row["type"])
        try:
            measured = member_type(benchmark_type, Case(id=pair_id, status="",
                                                        group=cohort, set=set_))
        except (SystemExit, KeyError):
            bad(f"type {row['type']!r} does not fit the set {set_}")
            continue
        # A set's measured type fits, and so does any type an English case of
        # the same set and cohort already holds (``ch-aoi-160`` is a refusal in
        # the aoi set): the guide asks for a type, set and cohort that has a
        # 2026 member. SET_TYPES lacks refusal, which ``type_of`` reads from
        # the note.
        if (SET_TYPES.get(set_, measured) != measured
                and measured not in stored_types[(set_, cohort)]):
            bad(f"type {row['type']!r} does not fit the set {set_}, "
                f"which measures {SET_TYPES[set_]!r}, and no English "
                f"{set_}/{cohort} case has that type")
            continue
        if set_ not in prefixes:
            bad(f"no single id prefix among the numbered cases of the set {set_}")
            continue
        highest[prefixes[set_]] += 1
        twin_id = f"{prefixes[set_]}-{highest[prefixes[set_]]:03d}"
        source = f", {row['source']}" if row["source"] else ""
        notes = {
            "pair_id": pair_id,
            "benchmark_type": benchmark_type,
            "use_cases": row["use_case"],
            "synthetic": "FALSE",
            "verified": VERIFIED.format(day=day),
            "aoi_name": raw.get("aoi_name", ""),
            "precedent": row.get("verify_precedent", ""),
        }

        def lineage(what: str) -> str:
            return (f"multilingual BENCHMARK {day}: {what} ({pair_id}); "
                    f"real {language} user prompt{source}")

        cases.append(Case(
            id=twin_id, status="ready", set=set_, group=cohort,
            query=row["english_query"], expected=expected,
            notes={"lineage": lineage(f"English twin written for {twin_id}-{language}"),
                   **notes},
        ))
        cases.append(Case(
            id=f"{twin_id}-{language}", status="ready", set=set_, group=cohort,
            language=language, twin=twin_id, query=query, expected=expected,
            notes={"lineage": lineage("prompt as typed"), **notes,
                   "language_review": review},
        ))

    after = {**by_id, **{case.id: case for case in cases}}
    for case_id, count in Counter(case.id for case in cases).items():
        if count > 1 or case_id in by_id:
            problems.append(f"{case_id}: the store or the sheet already has this id")
    for case in cases:
        problems += case.validate()
        if case.language != "en" and (problem := twin_problem(case, after)):
            problems.append(f"{case.id}: {problem}")
    return cases, list(dict.fromkeys(problems))


def _day(text: str) -> str:
    return date.fromisoformat(text).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sheet", type=Path, required=True,
                        help="the reviewed pair sheet (CSV)")
    parser.add_argument("--language", required=True,
                        choices=[code for code in LANGUAGES if code != "en"])
    parser.add_argument("--query-column", required=True,
                        help="the column that holds the question in --language "
                             "(spanish_query)")
    parser.add_argument("--date", required=True, type=_day,
                        help="the day the sheet was reviewed, YYYY-MM-DD")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/challenge"))
    parser.add_argument("--dry-run", action="store_true",
                        help="check every row and write nothing")
    args = parser.parse_args(argv)

    with args.sheet.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    missing = [c for c in (*COLUMNS, args.query_column) if c not in columns]
    if missing:
        print(f"{args.sheet}: no column {', '.join(missing)}")
        return 1
    if not rows:
        print(f"{args.sheet}: no rows")
        return 1

    store = [case for _path, case, _uid in load_store(args.cases_dir)]
    cases, problems = plan(rows, args.language, args.query_column, args.date, store)
    counts = Counter(case.language for case in cases)
    summary = (f"{len(rows)} rows: {counts[args.language]} cases in "
               f"{args.language}, {counts['en']} English twins")
    if problems:
        print("\n".join(problems))
        print(f"{len(problems)} problems; nothing written ({summary})")
        return 1
    if args.dry_run:
        print(f"would write {summary}")
        return 0
    for case in cases:
        write_case(args.cases_dir, case)
    print(f"wrote {summary}")
    print(f"next: tools/check.py --fix --cases-dir {args.cases_dir}, then "
          f"tools/coverage_doc.py --cases-dir {args.cases_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
