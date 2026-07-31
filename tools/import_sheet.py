"""Import the GOLD Google-Sheet CSV export into the case store.

Usage::

    uv run python tools/import_sheet.py --csv path/to/gold.csv
    uv run python tools/import_sheet.py --url "https://docs.google.com/...gid=0"
    uv run python tools/import_sheet.py --csv gold.csv --prune

Column handling (lossless by construction):

- ``test_id`` / ``status`` / ``test_group`` / ``query`` -> case metadata
- ``expected_*``  -> ``expected`` (prefix stripped; participates in the uid)
- everything else -> ``notes``   (prefix ``note_`` stripped; NOT hashed)

Rows with an empty query are skipped and counted. Duplicate test_ids abort
the import. Re-importing an unchanged sheet is byte-idempotent. ``--prune``
deletes case files whose id no longer appears in the sheet; without it,
orphans are reported but kept.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.canonical import normalize_text
from goldset.store import (
    Case,
    build_manifest,
    case_path,
    load_store,
    write_case,
    write_manifest,
)

META_COLUMNS = {"test_id", "status", "test_group", "query"}
HEADER_SCAN_ROWS = 5
HEADER_SCAN_COLS = 10


def find_header(rows: list[list[str]]) -> int:
    """Index of the header row: the first of the top rows containing a cell
    equal to ``query``. Tolerates human preamble above the headers."""
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        if "query" in [cell.strip() for cell in row[:HEADER_SCAN_COLS]]:
            return i
    raise ValueError("no header row found: no 'query' cell in the first rows")


def note_key(column: str) -> str:
    key = normalize_text(column).lower().replace(" ", "_")
    return key.removeprefix("note_")


def parse_cases(text: str) -> tuple[list[Case], int]:
    """Parse the sheet CSV into cases. Returns (cases, skipped_empty_query)."""
    rows = list(csv.reader(io.StringIO(text)))
    header_index = find_header(rows)
    header = [cell.strip() for cell in rows[header_index]]
    missing = META_COLUMNS - set(header)
    if missing:
        raise ValueError(f"sheet is missing required columns: {sorted(missing)}")

    cases: list[Case] = []
    skipped = 0
    for row in rows[header_index + 1 :]:
        record = dict(zip(header, [cell for cell in row]))
        if not normalize_text(record.get("query")):
            skipped += 1
            continue
        expected = {
            column.removeprefix("expected_"): normalize_text(value)
            for column, value in record.items()
            if column.startswith("expected_") and normalize_text(value)
        }
        notes = {
            note_key(column): normalize_text(value)
            for column, value in record.items()
            if column not in META_COLUMNS
            and not column.startswith("expected_")
            and normalize_text(value)
        }
        cases.append(
            Case(
                id=normalize_text(record["test_id"]),
                status=normalize_text(record["status"]).lower(),
                group=normalize_text(record["test_group"]),
                query=normalize_text(record["query"]),
                expected=expected,
                notes=notes,
            )
        )

    duplicate_ids = {c.id for c in cases if [x.id for x in cases].count(c.id) > 1}
    if duplicate_ids:
        raise ValueError(f"duplicate test_ids in sheet: {sorted(duplicate_ids)}")
    return cases, skipped


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def run_import(text: str, cases_dir: Path, source: str, prune: bool) -> int:
    cases, skipped = parse_cases(text)
    problems = [p for case in cases for p in case.validate()]
    if problems:
        print("invalid cases, aborting:", *problems, sep="\n  ")
        return 1

    written = [write_case(cases_dir, case) for case in cases]
    manifest = build_manifest(cases, source)
    write_manifest(cases_dir, manifest)

    wanted = {case_path(cases_dir, case).resolve() for case in cases}
    orphans = [
        path
        for path, _case, _uid in load_store(cases_dir)
        if path.resolve() not in wanted
    ]
    for path in orphans:
        if prune:
            path.unlink()
        print(f"{'pruned' if prune else 'ORPHAN (use --prune)'}: {path}")

    print(
        f"imported {len(written)} cases ({skipped} empty-query rows skipped), "
        f"caseset_version={manifest['caseset_version']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", type=Path, help="path to a sheet CSV export")
    group.add_argument("--url", help="CSV export URL of the sheet")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases"))
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()

    if args.csv:
        text, source = args.csv.read_text(encoding="utf-8"), str(args.csv.name)
    else:
        text, source = fetch(args.url), args.url
    return run_import(text, args.cases_dir, source, args.prune)


if __name__ == "__main__":
    raise SystemExit(main())
