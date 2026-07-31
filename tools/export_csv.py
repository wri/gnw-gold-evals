"""Export the case store to a gnw-evals-compatible CSV.

Bridge tool: until the harness is ported (PR-03), runs still execute via
gnw-evals' ``--test-file``. This makes the repo the source of truth today
with zero harness changes::

    uv run python tools/export_csv.py --out /tmp/gold.csv
    # then, in gnw-evals:
    #   uv run gnw_evals --test-file /tmp/gold.csv --sample-size -1 ...

The ``uid`` is carried in a trailing column; gnw-evals ignores unknown
columns, and the results importer (PR-02) joins on it.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.store import load_store

# Sheet-conventional ordering for the fields gnw-evals reads; unknown
# expected_* fields are appended alphabetically so nothing is dropped.
PREFERRED_EXPECTED_ORDER = [
    "aoi_ids",
    "aoi_source",
    "dataset_id",
    "dataset_name",
    "dataset_parameters",
    "context_layer",
    "start_date",
    "end_date",
    "answer",
    "clarification",
    "text",
    "suggested_datasets",
    "nudge_type",
    "nudge_options",
    "dashboard_created",
    "dashboard_widgets",
]


def expected_columns(cases) -> list[str]:
    keys = {key for case in cases for key in case.expected}
    ordered = [key for key in PREFERRED_EXPECTED_ORDER if key in keys]
    ordered += sorted(keys - set(ordered))
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=Path("cases"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--status-exclude",
        default="",
        help="comma-separated statuses to drop (e.g. 'not doing,todo')",
    )
    args = parser.parse_args()

    excluded = {s.strip().lower() for s in args.status_exclude.split(",") if s.strip()}
    cases = [case for _path, case, _uid in load_store(args.cases_dir)]
    cases = [case for case in cases if case.status.lower() not in excluded]
    if not cases:
        print("no cases to export (check --cases-dir / --status-exclude)")
        return 1
    cases.sort(key=lambda case: case.id)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = expected_columns(cases)
    header = (
        ["test_id", "status", "test_group", "query"]
        + [f"expected_{field}" for field in fields]
        + ["uid"]
    )
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for case in cases:
            writer.writerow(
                [case.id, case.status, case.group, case.query]
                + [case.expected.get(field, "") for field in fields]
                + [case.uid]
            )
    print(f"wrote {len(cases)} cases -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
