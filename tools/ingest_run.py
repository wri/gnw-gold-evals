"""Ingest a gnw-evals run (the ``*_detailed.csv``) into the results ledger.

    uv run python tools/ingest_run.py \
      --detailed ../gnw-evals/outputs/gold_run6_..._detailed.csv \
      --environment staging --build "GNW 2026.7.29.1" --ff experimental \
      --harness-sha unknown

Joining (see results/README.md): rows carrying a ``uid`` column (exports
from this repo) join directly — and if that uid is no longer in the store,
the row is stale, full stop; falling back to a weaker join would re-key old
scores onto edited case content, the exact misattribution uids exist to
prevent. Only rows with no uid at all (legacy sheet runs) fall back to
``test_id`` plus an exact-normalised-query match against the current store,
a warned, weaker join. Rows that match neither are recorded with
``stale_case: true``: never dropped, never re-keyed, excluded from
regression math.

Idempotent: same inputs and flags produce a byte-identical ledger file.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import summarize_buckets
from goldset.canonical import normalize_text
from goldset.ledger import (
    check_name_from_column,
    majority_from_mean,
    make_run_id,
    parse_score,
    reason_name_from_column,
    write_run,
)
from goldset.store import load_store, read_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
REASON_TRIM = 500
_FILENAME_TS = re.compile(r"(\d{8})_(\d{6})")


def started_from_filename(path: Path) -> str | None:
    match = _FILENAME_TS.search(path.name)
    if not match:
        return None
    date, time = match.groups()
    return (
        f"{date[:4]}-{date[4:6]}-{date[6:]}T{time[:2]}:{time[2:4]}:{time[4:]}Z"
    )


# Scalar expected_* columns with stable rendering in the detailed CSV —
# the drift-detection surface for the weak (test_id) join. List-rendered
# columns (aoi_ids, suggested_datasets, ...) are format-unstable and
# excluded; reconciliation covers their absence separately.
DRIFT_COLUMNS = (
    "dataset_id",
    "context_layer",
    "start_date",
    "end_date",
    "answer",
    "text",
)


def expectation_drift(row: dict, case) -> list[str]:
    """Columns present in the CSV whose value differs from the case's
    current expectation. A case *gaining* new expectations since the run is
    not drift — the run simply didn't test them."""
    drifted = []
    for column in DRIFT_COLUMNS:
        csv_value = normalize_text(row.get(f"expected_{column}"))
        if not csv_value:
            continue
        if csv_value != normalize_text(case.expected.get(column)):
            drifted.append(column)
    return drifted


def build_entry(row: dict, by_id: dict, by_uid: set, num_trials: int = 1) -> dict:
    """One ledger entry from one detailed-CSV row, joined to the store."""
    checks = {}
    reasons = {}
    for column, cell in row.items():
        check = check_name_from_column(column)
        if check is not None:
            # multi-trial CSVs put the trial mean in the score column
            checks[check] = (
                parse_score(cell)
                if num_trials == 1
                else majority_from_mean(cell, num_trials)
            )
        reason_for = reason_name_from_column(column)
        if reason_for is not None and normalize_text(cell):
            reasons[reason_for] = normalize_text(cell)[:REASON_TRIM]

    entry: dict = {"uid": None, "id": normalize_text(row.get("test_id"))}
    row_uid = normalize_text(row.get("uid"))
    if row_uid:
        if row_uid in by_uid:
            entry["uid"] = row_uid
        else:
            # The row asserts a specific case version that no longer
            # exists; re-keying via test_id+query would attribute its
            # scores to the case's edited content.
            entry["stale_case"] = True
    else:
        case = by_id.get(entry["id"])
        if case is not None and normalize_text(row.get("query")) == normalize_text(
            case.query
        ):
            drift = expectation_drift(row, case)
            if drift:
                # The run scored different expectations than the case now
                # holds — re-keying it would attribute old results to new
                # content, the exact misattribution uids exist to prevent.
                entry["stale_case"] = True
                entry["drift"] = drift
            else:
                entry["uid"] = case.uid
                entry["joined_by"] = "test_id"
        else:
            entry["stale_case"] = True

    entry["checks"] = checks
    if reasons:
        entry["reasons"] = reasons
    latency = normalize_text(row.get("duration_seconds"))
    if latency:
        entry["latency_s"] = round(float(latency), 1)
    trace_url = normalize_text(row.get("trace_url"))
    if trace_url:
        entry["trace_url"] = trace_url
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detailed", type=Path, required=True)
    # defaults are repo-root-relative so the tool works from any cwd
    parser.add_argument("--cases-dir", type=Path, default=REPO_ROOT / "cases/v2")
    parser.add_argument("--results-dir", type=Path, default=REPO_ROOT / "results")
    parser.add_argument("--environment", required=True, choices=["staging", "prod"])
    parser.add_argument("--build", required=True, help="agent build, e.g. 'GNW 2026.7.29.1'")
    parser.add_argument("--ff", default=None, help="agent tool profile, if any")
    parser.add_argument("--harness-repo", default="gnw-evals")
    parser.add_argument("--harness-sha", required=True, help="'unknown' is acceptable and honest")
    parser.add_argument("--judge-model", default="claude-haiku-4-5")
    parser.add_argument("--num-trials", type=int, default=1)
    parser.add_argument("--started", default=None, help="ISO-8601 UTC; default: parsed from the CSV filename")
    args = parser.parse_args()

    started = args.started or started_from_filename(args.detailed)
    if not started:
        print("cannot determine start time: pass --started")
        return 1

    manifest = read_manifest(args.cases_dir)
    if manifest is None:
        print(f"no manifest under {args.cases_dir} — import cases first")
        return 1
    cases = [case for _path, case, _uid in load_store(args.cases_dir)]
    by_id = {case.id: case for case in cases}
    by_uid = {case.uid for case in cases}

    with args.detailed.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print(f"{args.detailed}: no data rows")
        return 1

    entries = [
        build_entry(row, by_id, by_uid, num_trials=args.num_trials) for row in rows
    ]
    stale = sum(1 for e in entries if e.get("stale_case"))
    stale_uid = sum(
        1
        for row, e in zip(rows, entries)
        if e.get("stale_case") and normalize_text(row.get("uid"))
    )
    weak = sum(1 for e in entries if e.get("joined_by") == "test_id")
    if weak:
        print(f"warning: {weak} rows joined by test_id+query (no uid column)")
    if stale_uid:
        print(
            f"warning: {stale_uid} rows carry a uid no longer in the store "
            "-> stale_case (case content edited since the run?)"
        )

    run = {
        "run_id": make_run_id(started, args.environment, args.ff),
        "started": started,
        "environment": args.environment,
        "build": args.build,
        "ff": args.ff,
        "harness": {"repo": args.harness_repo, "sha": args.harness_sha},
        "judge_model": args.judge_model,
        "num_trials": args.num_trials,
        "caseset_version": manifest["caseset_version"],
        "results": entries,
    }
    run["buckets"] = summarize_buckets(entries)
    path = write_run(args.results_dir, run)
    print(
        f"wrote {path} — {len(entries)} rows "
        f"({len(entries) - stale} matched, {stale} stale)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
