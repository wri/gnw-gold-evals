"""Promote reviewed numeric-case rows (CSV) into the CHALLENGE store.

Takes case rows in the gnw-evals CSV shape — either promoted files ported
from gnw-evals ``eval-metrics-slice-1`` or reviewed candidates from
``generate_cases.py`` — and writes one YAML case per row into
``cases/challenge/<intent>/<cohort>/`` (set = intent, cohort = dataset).

The field mapping is the port's contract (retrieval-first scoring):

- ``expected_aoi_ids`` / ``expected_dataset_id`` / dates map straight onto
  the goldset expected fields. Rows whose ``evaluators`` whitelist omits
  ``date`` (two-period comparisons: any sub-window of the compared span is
  defensible) get NO date expectation.
- ``canopy_cover`` becomes a scored ``dataset_parameters`` expectation ONLY
  when it differs from the dataset's default (the generation rules forbid
  stating the default in the wording); the default is recorded in notes,
  unscored.
- ``forest_filter`` maps to ``context_layer``; for forest-layer datasets a
  blank filter maps to ``no_selection`` — the wordings explicitly opt out,
  so silently applying a filter (the primary-forest-substitution bug) fails.
- Every row gets ``data_pull: TRUE`` (ground truth is computed at run time,
  never stored, so no answer expectation exists to imply the pull checks).
- ``judge_instruction``, crop/gas/land-cover-class parameters, and the
  manifest lineage land in notes — unscored until evaluators exist.

After promoting, run ``tools/check.py --fix --cases-dir cases/challenge``
and ``tools/coverage_doc.py --cases-dir cases/challenge`` and commit all of
it together.

Usage:
    uv run python generation/promote_cases.py <rows.csv> [...] \
        [--lineage "gnw-evals eval-metrics-slice-1"] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from dataset_config import DATASET_CONFIGS, INTENT_ID_PREFIX

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from goldset.store import Case, load_store, write_case  # noqa: E402

CASES_DIR = REPO_ROOT / "cases" / "challenge"

_ID_RE = re.compile(r"^(ch-[a-z]+)-(\d+)$")


def catalog_sha() -> str:
    snapshot = json.loads((REPO_ROOT / "cases" / "zeno_catalog.json").read_text())
    return str(snapshot["source"]["sha"])[:7]


def _whitelisted(row: dict, name: str) -> bool:
    """The gnw-evals per-case evaluator whitelist, reduced to what the port
    needs: an explicit whitelist that omits ``date`` (two-period rows) or
    ``parameters`` suppresses that expectation. An empty whitelist means
    everything applies."""
    whitelist = [e.strip() for e in (row.get("evaluators") or "").split(";") if e.strip()]
    return not whitelist or name in whitelist


def build_case(row: dict, case_id: str,
               status: str, lineage_prefix: str, sha: str) -> Case:
    slug = row["expected_dataset_name"]
    cfg = DATASET_CONFIGS[slug]
    intent = row["intent"]
    if intent not in INTENT_ID_PREFIX:
        raise ValueError(f"{row.get('test_id')}: unknown intent {intent!r}")

    expected: dict[str, str] = {
        "aoi_ids": row["expected_aoi_ids"],
        "dataset_id": row["expected_dataset_id"],
    }
    if _whitelisted(row, "date"):
        if row.get("expected_start_date"):
            expected["start_date"] = row["expected_start_date"]
        if row.get("expected_end_date"):
            expected["end_date"] = row["expected_end_date"]

    notes: dict[str, str] = {}
    canopy = (row.get("expected_canopy_cover") or "").strip()
    if canopy and cfg.canopy_default is not None and _whitelisted(row, "parameters"):
        if canopy != cfg.canopy_default:
            expected["dataset_parameters"] = json.dumps(
                [{"name": "canopy_cover", "values": [int(canopy)]}],
                separators=(",", ":"),
            )
        else:
            notes["canopy"] = f"default {canopy}, unstated in prompt; unscored"

    if cfg.forest_layers:
        expected["context_layer"] = (
            (row.get("expected_forest_filter") or "").strip() or "no_selection"
        )

    clarification = (row.get("expected_clarification") or "").strip()
    if clarification:
        expected["clarification"] = clarification
    else:
        expected["data_pull"] = "TRUE"

    if (row.get("expected_chart_type") or "").strip():
        expected["chart_type"] = row["expected_chart_type"].strip()

    for column, note_key in (
        ("expected_intersections", "intersections"),
        ("expected_crop_types", "crop_types"),
        ("expected_gas_types", "gas_types"),
        ("expected_land_cover_classes", "land_cover_classes"),
    ):
        value = (row.get(column) or "").strip()
        if value:
            notes[note_key] = f"{value} (unscored: no evaluator surface yet)"

    if (row.get("judge_instruction") or "").strip():
        notes["judge_instruction"] = row["judge_instruction"].strip()
    if (row.get("eval_subtype") or "").strip():
        notes["eval_subtype"] = row["eval_subtype"].strip()
    if (row.get("manifest_id") or "").strip():
        notes["manifest_id"] = row["manifest_id"].strip()
    lineage = lineage_prefix
    if (row.get("test_id") or "").strip():
        lineage = f"{lineage_prefix} {row['test_id'].strip()}".strip()
    if lineage:
        notes["lineage"] = lineage
    notes["verified"] = (
        f"expected values constructed mechanically from manifest + catalog "
        f"(zeno@{sha})"
    )

    return Case(
        id=case_id,
        status=status,
        set=intent,
        group=cfg.cohort,
        query=row["query"],
        expected=expected,
        notes=notes,
    )


def next_id_numbers(existing_ids: list[str]) -> dict[str, int]:
    highest: dict[str, int] = {}
    for case_id in existing_ids:
        match = _ID_RE.match(case_id)
        if match:
            prefix, number = match.group(1), int(match.group(2))
            highest[prefix] = max(highest.get(prefix, 0), number)
    return highest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csvs", nargs="+", type=Path, help="case-row CSV file(s)")
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--status", default="ready")
    parser.add_argument("--lineage", default="",
                        help="lineage prefix recorded per case (row test_id appended)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entries = load_store(args.cases_dir)
    existing_uids = {case.uid for _p, case, _u in entries}
    highest = next_id_numbers([case.id for _p, case, _u in entries])
    sha = catalog_sha()

    written = skipped = 0
    for csv_path in args.csvs:
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                prefix = INTENT_ID_PREFIX[row["intent"]]
                highest[prefix] = highest.get(prefix, 0) + 1
                case = build_case(
                    row, f"{prefix}-{highest[prefix]:03d}",
                    args.status, args.lineage, sha,
                )
                if case.uid in existing_uids:
                    highest[prefix] -= 1
                    skipped += 1
                    continue
                existing_uids.add(case.uid)
                written += 1
                if args.dry_run:
                    print(f"would write {case.id} [{case.set}/{case.group}] {case.query[:60]!r}")
                else:
                    write_case(args.cases_dir, case)
    print(f"{written} case(s) written, {skipped} duplicate(s) skipped")
    if written and not args.dry_run:
        print("now run: tools/check.py --fix --cases-dir cases/challenge "
              "&& tools/coverage_doc.py --cases-dir cases/challenge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
