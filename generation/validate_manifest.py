"""Validate permutation manifests against the dataset catalog and the store.

Ported from gnw-evals ``eval-metrics-slice-1``. The manifest is the
prompt-coverage denominator: every row is a permutation a well-tested cell
should cover. This script fails loudly on rows that could not produce a
valid analytics query, and reports coverage of manifest rows by CHALLENGE
cases (matched on ``notes.manifest_id``).

Each manifest's dataset is resolved from its filename via
``generation/dataset_config.py``; its validation surface (legal canopy
values, context layers, year range) comes from that dataset's catalog YAML
in ``--catalog-dir`` (a project-zeno checkout — the committed
``cases/zeno_catalog.json`` snapshot is too trimmed for this).

Usage:
    uv run python generation/validate_manifest.py \
        --catalog-dir ../project-zeno/src/agent/datasets/catalog
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import yaml
from dataset_config import DatasetConfig, config_for_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from goldset.store import load_store  # noqa: E402

MANIFEST_DIR = REPO_ROOT / "generation" / "manifests"
CASES_DIR = REPO_ROOT / "cases" / "challenge"

VALID_PHRASINGS = {"direct", "conversational", "imprecise"}
_AOI_ID = re.compile(r"^[A-Z]{3}$")  # GADM level-0 slice; widen per phase
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Date-expression classes legal per date_mode.
_DATE_EXPRESSIONS = {
    "years": {"absolute_year", "absolute_range"},
    "dates": {"absolute_date", "absolute_date_range", "relative_recent"},
    "blank": {"none", "fixed"},
}


def _load_catalog(catalog_path: Path) -> dict:
    """Extract the validation surface from the dataset catalog YAML."""
    data = yaml.safe_load(catalog_path.read_text())
    canopy_values: set[str] = set()
    for param in data.get("parameters") or []:
        if param.get("name") == "canopy_cover":
            canopy_values = {str(v) for v in param.get("values") or []}
    forest_filters = {
        str(layer.get("value")) for layer in data.get("context_layers") or []
    }
    # Alert-stream datasets declare no end_date (open-ended to "today");
    # year bounds are only consulted for date_mode="years" datasets, which
    # always declare both, so a wide default is safe.
    return {
        "dataset_id": str(data["dataset_id"]),
        "canopy_values": canopy_values,
        "forest_filters": forest_filters,
        "start_year": int(str(data.get("start_date") or "0001")[:4]),
        "end_year": int(str(data.get("end_date") or "9999")[:4]),
    }


def _validate_row(row: dict, cfg: DatasetConfig, catalog: dict) -> list[str]:
    errors = []
    rid = row.get("manifest_id", "<missing id>")

    if row.get("intent") not in cfg.intents:
        errors.append(
            f"{rid}: intent {row.get('intent')!r} not applicable to {cfg.slug} "
            f"(applicable: {sorted(cfg.intents)})",
        )
    if not row.get("eval_subtype"):
        errors.append(f"{rid}: empty eval_subtype")

    aoi_ids = [a for a in (row.get("aoi_ids") or "").split(";") if a]
    if not aoi_ids:
        errors.append(f"{rid}: no aoi_ids")
    for aoi in aoi_ids:
        if not _AOI_ID.match(aoi):
            errors.append(f"{rid}: aoi id {aoi!r} is not a GADM level-0 ISO3 code")

    errors.extend(_validate_dates(row, cfg, catalog))
    errors.extend(_validate_params(row, cfg, catalog))

    if row.get("phrasing") not in VALID_PHRASINGS:
        errors.append(f"{rid}: phrasing {row.get('phrasing')!r} unknown")
    try:
        if int(row["n_cases"]) < 1:
            errors.append(f"{rid}: n_cases must be >= 1")
    except (KeyError, ValueError):
        errors.append(f"{rid}: n_cases must be an integer")

    return errors


def _validate_dates(row: dict, cfg: DatasetConfig, catalog: dict) -> list[str]:
    rid = row.get("manifest_id", "<missing id>")
    errors: list[str] = []
    expr = row.get("date_expression")
    if expr not in _DATE_EXPRESSIONS[cfg.date_mode]:
        errors.append(
            f"{rid}: date_expression {expr!r} not valid for date_mode "
            f"{cfg.date_mode!r} (expected one of "
            f"{sorted(_DATE_EXPRESSIONS[cfg.date_mode])})",
        )

    if cfg.date_mode == "years":
        try:
            start, end = int(row["start_year"]), int(row["end_year"])
            if not (catalog["start_year"] <= start <= end <= catalog["end_year"]):
                errors.append(
                    f"{rid}: years {start}-{end} outside catalog range "
                    f"{catalog['start_year']}-{catalog['end_year']} or reversed",
                )
        except (KeyError, ValueError):
            errors.append(f"{rid}: start_year/end_year must be 4-digit years")
    elif cfg.date_mode == "dates":
        for col in ("start_date", "end_date"):
            value = (row.get(col) or "").strip()
            if not _ISO_DATE.match(value):
                errors.append(f"{rid}: {col} {value!r} must be YYYY-MM-DD")
    return errors


def _validate_params(row: dict, cfg: DatasetConfig, catalog: dict) -> list[str]:
    rid = row.get("manifest_id", "<missing id>")
    errors: list[str] = []

    canopy = (row.get("canopy_cover") or "").strip()
    if canopy:
        if cfg.canopy_default is None:
            errors.append(
                f"{rid}: {cfg.slug} takes no canopy_cover but row sets {canopy!r}",
            )
        elif catalog["canopy_values"] and canopy not in catalog["canopy_values"]:
            errors.append(
                f"{rid}: canopy {canopy!r} not a legal catalog value "
                f"{sorted(catalog['canopy_values'])}",
            )

    forest_filter = (row.get("forest_filter") or "").strip()
    if forest_filter and forest_filter not in cfg.forest_layers:
        errors.append(
            f"{rid}: forest_filter {forest_filter!r} not a context layer of "
            f"{cfg.slug} (legal: {sorted(cfg.forest_layers) or 'none'})",
        )

    intersections = (row.get("intersections") or "").strip()
    if intersections and "intersections" not in cfg.params:
        errors.append(
            f"{rid}: {cfg.slug} takes no intersections but row sets {intersections!r}",
        )

    for col, param in (("crop_types", "crop_types"), ("gas_types", "gas_types")):
        value = (row.get(col) or "").strip()
        if value and param not in cfg.params:
            errors.append(f"{rid}: {cfg.slug} takes no {param} but row sets {value!r}")
    return errors


def _store_case_counts(cases_dir: Path) -> dict[str, int]:
    """Cases per manifest_id across the CHALLENGE store."""
    counts: dict[str, int] = {}
    if not cases_dir.exists():
        return counts
    for _path, case, _uid in load_store(cases_dir):
        manifest_id = case.notes.get("manifest_id", "")
        if manifest_id:
            counts[manifest_id] = counts.get(manifest_id, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", type=Path, required=True,
                        help="Directory of dataset catalog YAMLs "
                             "(project-zeno .../datasets/catalog)")
    parser.add_argument("--manifest-dir", type=Path, default=MANIFEST_DIR)
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    args = parser.parse_args()

    manifests = sorted(args.manifest_dir.glob("*.manifest.csv"))
    if not manifests:
        raise SystemExit(f"no *.manifest.csv files in {args.manifest_dir}")

    counts = _store_case_counts(args.cases_dir)
    all_ids: set[str] = set()
    all_errors: list[str] = []
    for manifest_path in manifests:
        try:
            cfg = config_for_manifest(manifest_path.name)
        except KeyError as exc:
            all_errors.append(str(exc))
            continue
        catalog_path = args.catalog_dir / f"{cfg.slug}.yml"
        if not catalog_path.exists():
            all_errors.append(
                f"{manifest_path.name}: no catalog YAML at {catalog_path}",
            )
            continue
        catalog = _load_catalog(catalog_path)
        if catalog["dataset_id"] != cfg.dataset_id:
            all_errors.append(
                f"{manifest_path.name}: catalog dataset_id {catalog['dataset_id']} "
                f"!= config {cfg.dataset_id}",
            )

        with open(manifest_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        ids = [r.get("manifest_id", "") for r in rows]
        all_ids.update(ids)
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            all_errors.append(f"{manifest_path.name}: duplicate ids {duplicates}")

        for row in rows:
            all_errors.extend(_validate_row(row, cfg, catalog))

        covered = sum(1 for r in rows if counts.get(r["manifest_id"], 0) > 0)
        pct = f"{covered / len(rows):.0%}" if rows else "n/a"
        print(f"{manifest_path.name}: {len(rows)} rows")
        print(
            f"  prompt coverage: {covered}/{len(rows)} rows have at least one case ({pct})",
        )
        short = [
            f"{r['manifest_id']} ({counts.get(r['manifest_id'], 0)}/{r['n_cases']})"
            for r in rows
            if counts.get(r["manifest_id"], 0) < int(r["n_cases"] or 1)
        ]
        if short:
            print(f"  below n_cases target: {', '.join(short)}")

    unknown = {i for i in counts if i not in all_ids}
    if unknown:
        all_errors.append(f"store cases reference unknown manifest ids {sorted(unknown)}")

    if all_errors:
        print("\nVALIDATION ERRORS:", file=sys.stderr)
        for error in all_errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("\nAll manifests valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
