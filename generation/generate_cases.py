"""Generate candidate numeric-case wordings from a permutation manifest.

Ported from gnw-evals ``eval-metrics-slice-1``. For every manifest row with
fewer existing cases than its ``n_cases`` target, this script asks an LLM to
write the missing prompt wordings (honouring the per-cell instruction files)
and constructs the full case row mechanically from the manifest parameters:
the LLM only ever writes the query text, never expected values.

Existing coverage is counted from the CHALLENGE store (``notes.manifest_id``)
plus any pending candidates file, so re-runs only fill gaps. Candidates land
in ``scratch/candidates/`` (gitignored) for review; promotion into the store
is ``generation/promote_cases.py``, deliberately a separate reviewed step.

Usage:
    uv run python generation/generate_cases.py --dataset tree_cover_loss --intent quantification
    uv run python generation/generate_cases.py --dataset integrated_alerts --intent trend --dry-run
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import dotenv
from dataset_config import DATASET_CONFIGS, DatasetConfig
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from goldset.store import load_store  # noqa: E402

MANIFEST_DIR = REPO_ROOT / "generation" / "manifests"
CASES_DIR = REPO_ROOT / "cases" / "challenge"
CANDIDATES_DIR = REPO_ROOT / "scratch" / "candidates"
INSTRUCTIONS_DIR = Path(__file__).resolve().parent

# The gnw-evals promoted-case column order; promote_cases.py consumes it.
CASE_COLUMNS = [
    "query",
    "expected_aoi_ids",
    "expected_subregion",
    "expected_aoi_source",
    "expected_dataset_id",
    "expected_dataset_name",
    "expected_context_layer",
    "expected_start_date",
    "expected_end_date",
    "expected_answer",
    "expected_clarification",
    "expected_chart_type",
    "expected_canopy_cover",
    "expected_forest_filter",
    "expected_intersections",
    "expected_crop_types",
    "expected_gas_types",
    "expected_land_cover_classes",
    "judge_instruction",
    "expected_language",
    "test_group",
    "status",
    "test_id",
    "intent",
    "eval_subtype",
    "manifest_id",
    "evaluators",
]

# ISO3 → prose, for the row brief the LLM reads. Extend as manifests use more
# AOIs; unknown codes fall through to the code itself.
COUNTRY_NAMES = {
    "BRA": "Brazil",
    "IDN": "Indonesia",
    "COD": "the Democratic Republic of the Congo",
    "CRI": "Costa Rica",
    "GBR": "the United Kingdom",
    "COL": "Colombia",
    "PER": "Peru",
    "MYS": "Malaysia",
    "IND": "India",
    "GHA": "Ghana",
    "CIV": "Côte d'Ivoire",
    "BOL": "Bolivia",
    "MEX": "Mexico",
    "AUS": "Australia",
    "USA": "the United States",
}


class Wordings(BaseModel):
    """Structured output: the generated prompt wordings only."""

    wordings: list[str] = Field(
        description="The generated user prompts, one string per requested wording",
    )


def _existing_wordings(slug: str, intent: str) -> dict[str, list[str]]:
    """Existing queries per manifest row (store cases plus pending candidates)."""
    wordings: dict[str, list[str]] = {}
    if CASES_DIR.exists():
        for _path, case, _uid in load_store(CASES_DIR):
            manifest_id = case.notes.get("manifest_id", "")
            if case.set == intent and manifest_id.startswith("m-"):
                wordings.setdefault(manifest_id, []).append(case.query)
    candidates = CANDIDATES_DIR / f"{slug}__{intent}.candidates.csv"
    if candidates.exists():
        with open(candidates, encoding="utf-8") as f:
            for case in csv.DictReader(f):
                manifest_id = (case.get("manifest_id") or "").strip()
                if manifest_id:
                    wordings.setdefault(manifest_id, []).append(case.get("query", ""))
    return wordings


def _date_brief(cfg: DatasetConfig, row: dict) -> str:
    if cfg.date_mode == "dates":
        return (
            f"- window: {row['start_date']} to {row['end_date']} "
            "(state the dates explicitly)"
        )
    if cfg.date_mode == "blank":
        return (
            "- window: this dataset ignores/fixes the reporting period; do NOT "
            "state a specific year or range in the prompt"
        )
    single = row["start_year"] == row["end_year"]
    return f"- window: {row['start_year']} to {row['end_year']}" + (
        " (single year)" if single else ""
    )


def _row_brief(cfg: DatasetConfig, row: dict) -> str:
    countries = "; ".join(
        COUNTRY_NAMES.get(a, a) for a in row["aoi_ids"].split(";") if a
    )
    lines = [
        f"- intent: {row['intent']}, subtype: {row['eval_subtype']}",
        f"- country/countries: {countries}",
        _date_brief(cfg, row),
    ]
    if cfg.canopy_default is not None:
        canopy = row.get("canopy_cover") or cfg.canopy_default
        lines.append(
            f"- canopy threshold: {canopy}"
            + (
                " (default: do NOT mention it)"
                if canopy == cfg.canopy_default
                else " (MUST be stated)"
            ),
        )
    if cfg.forest_layers:
        lines.append(
            f"- forest filter: {row.get('forest_filter') or 'none (plain tree cover; opt out of forest-type filters explicitly)'}",
        )
    if "intersections" in cfg.params and not cfg.fixed_intersections:
        lines.append(
            f"- context layer / intersection: {row.get('intersections') or 'none'}",
        )
    if "crop_types" in cfg.params:
        lines.append(f"- crop(s): {row.get('crop_types') or 'unspecified'}")
    if "gas_types" in cfg.params:
        lines.append(f"- gas(es): {row.get('gas_types') or 'unspecified'}")
    if "land_cover_classes" in cfg.params:
        lines.append(
            f"- land-cover class(es): {row.get('land_cover_classes') or 'unspecified'}",
        )
    lines.append(f"- phrasing style: {row['phrasing']}")
    lines.append(f"- language: {row.get('expected_language') or 'en'}")
    if row.get("judge_note"):
        lines.append(
            f"- scoring context (do not quote in the prompt): {row['judge_note']}",
        )
    if row.get("notes"):
        lines.append(f"- notes: {row['notes']}")
    return "\n".join(lines)


def _generation_prompt(
    cfg: DatasetConfig,
    row: dict,
    n_wordings: int,
    instructions: str,
    existing_wordings: list[str],
) -> str:
    existing_block = ""
    if existing_wordings:
        joined = "\n".join(f"  - {w}" for w in existing_wordings)
        existing_block = (
            f"\nWordings that already exist for this permutation (yours must "
            f"differ meaningfully in structure and vocabulary):\n{joined}\n"
        )
    return f"""You write user prompts for evaluating a geospatial AI assistant \
(Global Nature Watch). Each prompt must read like a real user and map to \
exactly one analytics query.

INSTRUCTIONS (follow every rule):

{instructions}

PERMUTATION TO EXPRESS:

{_row_brief(cfg, row)}
{existing_block}
Write exactly {n_wordings} prompt wording(s) for this permutation. Every \
parameter above must be unambiguously derivable from the wording alone \
(except defaults the instructions say not to mention). Return only the \
wordings."""


def _expected_dates(cfg: DatasetConfig, row: dict) -> tuple[str, str]:
    if cfg.date_mode == "dates":
        return row.get("start_date", ""), row.get("end_date", "")
    if cfg.date_mode == "blank":
        return "", ""
    return f"{row['start_year']}-01-01", f"{row['end_year']}-12-31"


def _case_from_wording(
    cfg: DatasetConfig,
    row: dict,
    wording: str,
    variant_index: int,
) -> dict:
    variant = chr(ord("a") + variant_index)
    test_id = f"{row['manifest_id'].removeprefix('m-')}{variant}"
    start_date, end_date = _expected_dates(cfg, row)
    canopy = (
        (row.get("canopy_cover") or cfg.canopy_default)
        if cfg.canopy_default is not None
        else ""
    )
    intersections = cfg.fixed_intersections or (
        row.get("intersections", "") if "intersections" in cfg.params else ""
    )
    return {
        "query": wording,
        "expected_aoi_ids": row["aoi_ids"],
        "expected_subregion": cfg.aoi_subtype,
        "expected_aoi_source": cfg.aoi_source,
        "expected_dataset_id": cfg.dataset_id,
        "expected_dataset_name": cfg.slug,
        "expected_start_date": start_date,
        "expected_end_date": end_date,
        "expected_canopy_cover": canopy,
        "expected_forest_filter": (
            row.get("forest_filter", "") if cfg.forest_layers else ""
        ),
        "expected_intersections": intersections,
        "expected_crop_types": (
            row.get("crop_types", "") if "crop_types" in cfg.params else ""
        ),
        "expected_gas_types": (
            row.get("gas_types", "") if "gas_types" in cfg.params else ""
        ),
        "expected_land_cover_classes": (
            row.get("land_cover_classes", "")
            if "land_cover_classes" in cfg.params
            else ""
        ),
        "judge_instruction": row.get("judge_note", ""),
        "expected_language": row.get("expected_language", "en"),
        "test_group": cfg.cohort,
        "status": "candidate",
        "test_id": test_id,
        "intent": row["intent"],
        "eval_subtype": row["eval_subtype"],
        "manifest_id": row["manifest_id"],
        # Per-case evaluator whitelist (e.g. two_period rows exclude the
        # date check: any sub-window of the compared span is defensible).
        "evaluators": row.get("evaluators", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", dest="slug", required=True,
                        choices=sorted(DATASET_CONFIGS),
                        help="Dataset catalog slug (see generation/dataset_config.py)")
    parser.add_argument("--intent", required=True,
                        choices=["quantification", "comparison", "trend"])
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process N manifest rows")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts instead of calling the LLM")
    args = parser.parse_args()

    dotenv.load_dotenv(REPO_ROOT / ".env")

    cfg = DATASET_CONFIGS[args.slug]
    if args.intent not in cfg.intents:
        raise SystemExit(
            f"intent {args.intent!r} is not applicable to {args.slug} "
            f"(applicable: {sorted(cfg.intents)})",
        )

    manifest_path = MANIFEST_DIR / f"{args.slug}__{args.intent}.manifest.csv"
    if not manifest_path.exists():
        raise SystemExit(f"no manifest at {manifest_path}")
    with open(manifest_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    instructions = (
        (INSTRUCTIONS_DIR / args.slug / "_shared.md").read_text()
        + "\n\n"
        + (INSTRUCTIONS_DIR / args.slug / f"{args.intent}.md").read_text()
    )

    existing = _existing_wordings(args.slug, args.intent)
    todo = [
        (row, int(row["n_cases"]) - len(existing.get(row["manifest_id"], [])))
        for row in rows
        if len(existing.get(row["manifest_id"], [])) < int(row["n_cases"])
    ]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print("All manifest rows already meet their n_cases target.")
        return 0

    print(f"{len(todo)} manifest rows need wordings ({sum(n for _, n in todo)} total)")

    llm = (
        None
        if args.dry_run
        else ChatAnthropic(model=args.model, temperature=1.0, max_tokens=2048)
    )

    candidates: list[dict] = []
    for row, needed in todo:
        prior = existing.get(row["manifest_id"], [])
        prompt = _generation_prompt(cfg, row, needed, instructions, prior)
        if args.dry_run:
            print(f"\n=== {row['manifest_id']} (needs {needed}) ===\n{prompt}")
            continue
        result = llm.with_structured_output(Wordings).invoke(prompt)
        if len(result.wordings) != needed:
            raise RuntimeError(
                f"{row['manifest_id']}: asked for {needed} wordings, "
                f"got {len(result.wordings)}",
            )
        for i, wording in enumerate(result.wordings):
            candidates.append(_case_from_wording(cfg, row, wording, len(prior) + i))
        print(f"  {row['manifest_id']}: {needed} wording(s) generated")

    if args.dry_run or not candidates:
        return 0

    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CANDIDATES_DIR / f"{args.slug}__{args.intent}.candidates.csv"
    exists = out_path.exists()
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CASE_COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(candidates)
    print(f"\n{len(candidates)} candidate case(s) appended to {out_path}")
    print("Review them, then promote with generation/promote_cases.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
