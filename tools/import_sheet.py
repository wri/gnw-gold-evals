"""Import a GOLD Google-Sheet tab (CSV export) into the case store.

Usage::

    uv run python tools/import_sheet.py --gid 123456789     # tab of $SPREADSHEET_ID
    uv run python tools/import_sheet.py --csv path/to/gold.csv
    uv run python tools/import_sheet.py --url "https://docs.google.com/...gid=0"
    uv run python tools/import_sheet.py --gid 0 --prune

Every imported case records its origin in ``notes.source_tab``; ``--prune``
is **scoped to that source** — it only deletes orphans the same tab
imported earlier, and reports (never touches) unmanaged orphans. A row
whose ``test_id`` already exists from a *different* source errors unless
``--update`` is passed. A sheet ``uid`` column, if present, is never
trusted (uids are always recomputed) but is compared: rows whose sheet uid
differs are listed as "edited on sheet since last push".

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


# Sheet columns that are sync metadata, never case content.
SYNC_COLUMNS = {"uid", "last_changed"}


def parse_cases(text: str, source_tab: str = "") -> tuple[list[Case], int, list[str]]:
    """Parse the sheet CSV into cases.

    Returns (cases, skipped_empty_query, sheet_edited_ids) — the last being
    rows whose sheet ``uid`` column no longer matches their recomputed uid,
    i.e. edited on the sheet since the last push (P5).
    """
    rows = list(csv.reader(io.StringIO(text)))
    header_index = find_header(rows)
    header = [cell.strip() for cell in rows[header_index]]
    missing = META_COLUMNS - set(header)
    if missing:
        raise ValueError(f"sheet is missing required columns: {sorted(missing)}")

    cases: list[Case] = []
    skipped = 0
    sheet_edited: list[str] = []
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
            and column not in SYNC_COLUMNS
            and not column.startswith("expected_")
            and normalize_text(value)
        }
        if source_tab:
            notes["source_tab"] = source_tab
        case = Case(
            id=normalize_text(record["test_id"]),
            status=normalize_text(record["status"]).lower(),
            group=normalize_text(record["test_group"]),
            query=normalize_text(record["query"]),
            expected=expected,
            notes=notes,
        )
        sheet_uid = normalize_text(record.get("uid"))
        if sheet_uid and sheet_uid != case.uid:
            sheet_edited.append(case.id)
        cases.append(case)

    duplicate_ids = {c.id for c in cases if [x.id for x in cases].count(c.id) > 1}
    if duplicate_ids:
        raise ValueError(f"duplicate test_ids in sheet: {sorted(duplicate_ids)}")
    return cases, skipped, sheet_edited


def fetch(url: str) -> str:
    # utf-8-sig: Google/Excel CSV exports may lead with a BOM, which would
    # otherwise glue itself onto the first header cell ("﻿test_id").
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8-sig")


def run_import(
    text: str,
    cases_dir: Path,
    source: str,
    prune: bool,
    source_tab: str = "",
    update: bool = False,
) -> int:
    cases, skipped, sheet_edited = parse_cases(text, source_tab=source_tab)
    problems = [p for case in cases for p in case.validate()]
    if problems:
        print("invalid cases, aborting:", *problems, sep="\n  ")
        return 1

    store = load_store(cases_dir)
    existing = {case.id: case for _p, case, _u in store}
    existing_paths = {case.id: path for path, case, _u in store}

    # P4: a row colliding with a case from a DIFFERENT source is an error
    # unless --update makes the takeover explicit. Without a source_tab we
    # cannot attribute ownership, so the guard does not apply.
    if not update and source_tab:
        collisions = [
            case.id
            for case in cases
            if case.id in existing
            and existing[case.id].notes.get("source_tab", "") != source_tab
        ]
        if collisions:
            print(
                "test_ids already exist from a different source "
                f"(pass --update to take them over): {sorted(collisions)}"
            )
            return 1

    # An import that changes a case's test_group moves its file. Drop the
    # old file first — regardless of source_tab ownership — or the same
    # test_id would exist at two paths and check.py would fail the store.
    for case in cases:
        old_path = existing_paths.get(case.id)
        if old_path and old_path.resolve() != case_path(cases_dir, case).resolve():
            old_path.unlink()
            print(f"moved {case.id}: removed superseded file {old_path}")

    written = [write_case(cases_dir, case) for case in cases]

    # P3: prune is scoped to this import's source — unmanaged orphans
    # (no or different source_tab) are reported, never deleted.
    wanted = {case_path(cases_dir, case).resolve() for case in cases}
    for path, case, _uid in load_store(cases_dir):
        if path.resolve() in wanted:
            continue
        owned = source_tab and case.notes.get("source_tab") == source_tab
        if prune and owned:
            path.unlink()
            print(f"pruned: {path}")
        elif owned:
            print(f"ORPHAN of this tab (use --prune): {path}")
        else:
            print(f"orphan from another source, untouched: {path}")

    survivors = [case for _p, case, _u in load_store(cases_dir)]
    manifest = build_manifest(survivors, source)
    write_manifest(cases_dir, manifest)

    if sheet_edited:
        print(
            f"edited on sheet since last push ({len(sheet_edited)}): "
            + ", ".join(sorted(sheet_edited))
        )
    print(
        f"imported {len(written)} cases ({skipped} empty-query rows skipped), "
        f"caseset_version={manifest['caseset_version']}"
    )
    return 0


def main() -> int:
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", type=Path, help="path to a sheet CSV export")
    group.add_argument("--url", help="CSV export URL of the sheet")
    group.add_argument("--gid", help="tab gid within $SPREADSHEET_ID (P1)")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/v2"))
    parser.add_argument("--prune", action="store_true",
                        help="delete orphans previously imported from this same tab")
    parser.add_argument("--update", action="store_true",
                        help="allow taking over test_ids owned by another source")
    parser.add_argument("--source-tab", default=None,
                        help="override the source_tab label (defaults to gid:<gid> "
                             "or the file/url name)")
    args = parser.parse_args()

    if args.source_tab is not None and not args.source_tab.strip():
        parser.error(
            "--source-tab must not be empty: an empty label would disable "
            "both the cross-source collision guard and --prune scoping"
        )

    if args.gid is not None:
        load_dotenv()
        spreadsheet_id = os.environ.get("SPREADSHEET_ID")
        if not spreadsheet_id:
            print("SPREADSHEET_ID is not set (env or .env)")
            return 1
        url = (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            f"/export?format=csv&gid={args.gid}"
        )
        text, source, source_tab = fetch(url), url, f"gid:{args.gid}"
    elif args.csv:
        text = args.csv.read_text(encoding="utf-8-sig")
        source = str(args.csv.name)
        source_tab = args.csv.stem
    else:
        text, source, source_tab = fetch(args.url), args.url, args.url
    if args.source_tab is not None:
        source_tab = args.source_tab
    return run_import(
        text, args.cases_dir, source, args.prune,
        source_tab=source_tab, update=args.update,
    )


if __name__ == "__main__":
    raise SystemExit(main())
