"""Push phase 1: export the case store as sheet-uploadable CSVs.

    uv run python tools/export_sheet_csv.py --out scratch/push/

Writes two files (docs/caseset-implementation-plan.md §1.2):

- ``cases.csv``     — the tab replacement (File -> Import -> Replace).
  Carries ``uid`` and ``last_changed`` as row-wise version markers sheet
  editors can see but must never edit; the pull ignores and re-verifies
  both.
- ``changelog.csv`` — append-only version history derived from git: one
  row per uid transition per case (test_id, old_uid, new_uid, date,
  commit, subject). Paste-append into a dedicated 'changelog' tab.

Multi-turn cases are skipped with a note (sheet projection is single-turn
until someone needs otherwise). The repo remains the source of truth; the
sheet is a mirror.

Projection caveat: v2's pre-split history lives on the v1 paths — the
v1/v2 copy started fresh lineages, so ``changelog.csv`` for a v2 case
begins at the split, not at the case's original birth (accepted
projection artifact).
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_sheet import META_COLUMNS, SYNC_COLUMNS

from goldset.store import load_store

PREFERRED_EXPECTED_ORDER = [
    "aoi_ids", "aoi_source", "dataset_id", "dataset_name",
    "dataset_parameters", "context_layer", "start_date", "end_date",
    "answer", "clarification", "text", "suggested_datasets",
    "nudge_type", "nudge_options", "dashboard_created", "dashboard_widgets",
    "chart_type", "scope", "class_values",
]
NOTE_ORDER = ["status_reason", "aoi_type"]


def note_columns(entries: list) -> list[str]:
    """Every notes key observed across the exported cases, stable order:
    NOTE_ORDER first (always present, for sheet-layout stability), then the
    rest sorted. Dropping unlisted keys here is not an option — the importer
    replaces ``notes`` wholesale, so a push -> sheet-edit -> re-import round
    trip would wipe any curated metadata the export left out."""
    observed = {key for _path, case in entries for key in case.notes}
    return NOTE_ORDER + sorted(observed - set(NOTE_ORDER))


def note_column_name(key: str) -> str:
    """Sheet column for a notes key. The importer routes any unrecognised
    column into ``notes`` (stripping a ``note_`` prefix), so a key that
    would collide with the meta/sync/expected_/note_ namespaces is emitted
    prefixed to survive the round trip."""
    if key in META_COLUMNS or key in SYNC_COLUMNS:
        return f"note_{key}"
    if key.startswith(("expected_", "note_")):
        return f"note_{key}"
    return key


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _repo_root(cases_dir: Path) -> Path | None:
    top = _git(cases_dir, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def last_changed(repo: Path | None, path: Path) -> str:
    if repo is None:
        return "uncommitted"
    date = _git(repo, "log", "-1", "--format=%cs", "--follow", "--",
                str(path.resolve().relative_to(repo)))
    return date or "uncommitted"


def _history_entries(repo: Path, relative: str) -> list[tuple[str, ...]]:
    """(sha, date, subject, path-at-that-commit) newest first, rename-aware.

    ``git log --follow`` traces renames, but ``git show {sha}:{path}`` needs
    the path the file had *at that commit* — showing the current path fails
    for every pre-rename commit and drops those transitions. ``--name-status``
    yields the per-commit path: the last tab field (the post-commit path on
    R/C lines, the only path otherwise).
    """
    log = _git(repo, "log", "--follow", "--name-status",
               "--format=%x00%H|%cs|%s", "--", relative)
    entries = []
    for block in log.split("\x00"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        sha, date, subject = lines[0].split("|", 2)
        paths = [
            line.split("\t")[-1]
            for line in lines[1:]
            if line[0] in {"A", "M", "R", "C", "T"}
        ]
        if paths:
            entries.append((sha, date, subject, paths[0]))
    return entries


def uid_history(repo: Path | None, path: Path) -> list[dict[str, str]]:
    """uid transitions for one case file, oldest first, from git history."""
    if repo is None:
        return []
    relative = str(path.resolve().relative_to(repo))
    # NB: --follow combined with --reverse silently truncates history to the
    # earliest commit (git quirk) — fetch newest-first and reverse in code.
    transitions = []
    previous_uid: str | None = None
    for sha, date, subject, commit_path in reversed(
        _history_entries(repo, relative)
    ):
        shown = _git(repo, "show", f"{sha}:{commit_path}")
        uid = next(
            (row.split(":", 1)[1].strip() for row in shown.splitlines()
             if row.startswith("uid:")),
            "",
        )
        if uid and uid != previous_uid:
            transitions.append({
                "old_uid": previous_uid or "",
                "new_uid": uid,
                "date": date,
                "commit": sha[:9],
                "subject": subject[:100],
            })
            previous_uid = uid
    return transitions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/v2"))
    parser.add_argument("--out", type=Path, required=True,
                        help="directory for cases.csv + changelog.csv")
    parser.add_argument("--status-exclude", default="")
    args = parser.parse_args()

    excluded = {s.strip().lower() for s in args.status_exclude.split(",") if s.strip()}
    entries = [
        (path, case) for path, case, _uid in load_store(args.cases_dir)
        if case.status.lower() not in excluded
    ]
    multiturn = sum(1 for _p, case in entries if case.is_multiturn)
    if multiturn:
        print(f"note: {multiturn} multi-turn cases skipped (sheet projection "
              "is single-turn)")
    entries = [(p, c) for p, c in entries if not c.is_multiturn]
    if not entries:
        print("nothing to export")
        return 1
    entries.sort(key=lambda item: item[1].id)

    repo = _repo_root(args.cases_dir)
    args.out.mkdir(parents=True, exist_ok=True)

    expected_keys = {k for _p, c in entries for k in c.expected}
    expected_columns = [k for k in PREFERRED_EXPECTED_ORDER if k in expected_keys]
    expected_columns += sorted(expected_keys - set(expected_columns))
    notes_columns = note_columns(entries)

    header = (
        ["test_id", "status"]
        + [note_column_name(k) for k in notes_columns]
        + ["test_group", "query"]
        + [f"expected_{k}" for k in expected_columns]
        + ["uid", "last_changed"]
    )
    cases_path = args.out / "cases.csv"
    with cases_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for path, case in entries:
            writer.writerow(
                [case.id, case.status]
                + [case.notes.get(k, "") for k in notes_columns]
                + [case.group, case.query]
                + [case.expected.get(k, "") for k in expected_columns]
                + [case.uid, last_changed(repo, path)]
            )

    changelog_path = args.out / "changelog.csv"
    rows = 0
    with changelog_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["test_id", "old_uid", "new_uid", "date", "commit", "subject"])
        for path, case in entries:
            for transition in uid_history(repo, path):
                writer.writerow([case.id, transition["old_uid"],
                                 transition["new_uid"], transition["date"],
                                 transition["commit"], transition["subject"]])
                rows += 1

    print(f"wrote {cases_path} ({len(entries)} rows) and "
          f"{changelog_path} ({rows} transitions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
