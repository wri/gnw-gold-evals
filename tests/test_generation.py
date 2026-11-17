"""Unit tests for the numeric-case generation/promotion tooling.

The load-bearing piece is ``promote_cases.build_case``: the CSV → YAML field
mapping is the port's contract (canopy scored only when explicit, blank
forest filter → no_selection, two-period rows lose the date expectation,
every row expects a data pull). The LLM is never involved here — wordings
are inputs.

Usage
$ uv run python -m pytest tests/test_generation.py -v
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "generation"))

promote = importlib.util.module_from_spec(
    spec := importlib.util.spec_from_file_location(
        "promote_cases", ROOT / "generation" / "promote_cases.py"
    )
)
spec.loader.exec_module(promote)

generate = importlib.util.module_from_spec(
    spec2 := importlib.util.spec_from_file_location(
        "generate_cases", ROOT / "generation" / "generate_cases.py"
    )
)
spec2.loader.exec_module(generate)

from dataset_config import DATASET_CONFIGS, config_for_manifest  # noqa: E402


def _row(**overrides) -> dict:
    row = {
        "query": "How much tree cover did Brazil lose in 2023?",
        "expected_aoi_ids": "BRA",
        "expected_dataset_id": "4",
        "expected_dataset_name": "tree_cover_loss",
        "expected_start_date": "2023-01-01",
        "expected_end_date": "2023-12-31",
        "expected_canopy_cover": "30",
        "expected_forest_filter": "",
        "expected_clarification": "",
        "judge_instruction": "No forest-type filter should be applied.",
        "test_id": "gt-quant-01",
        "intent": "quantification",
        "eval_subtype": "single_year",
        "manifest_id": "m-tcl-quant-01",
        "evaluators": "",
    }
    row.update(overrides)
    return row


def _build(row):
    return promote.build_case(row, "ch-quant-001", "ready", "test-lineage", "31a4d1e")


def test_basic_mapping_and_hierarchy():
    case = _build(_row())
    assert (case.set, case.group, case.id) == ("quantification", "tcl", "ch-quant-001")
    assert case.expected["aoi_ids"] == "BRA"
    assert case.expected["dataset_id"] == "4"
    assert case.expected["start_date"] == "2023-01-01"
    assert case.expected["data_pull"] == "TRUE"
    assert case.notes["manifest_id"] == "m-tcl-quant-01"
    assert case.notes["judge_instruction"].startswith("No forest-type")
    assert case.notes["lineage"] == "test-lineage gt-quant-01"
    assert "31a4d1e" in case.notes["verified"]
    assert case.validate() == []


def test_default_canopy_is_noted_not_scored():
    # wordings never state the default, so the state may not carry it either
    case = _build(_row())
    assert "dataset_parameters" not in case.expected
    assert "default 30" in case.notes["canopy"]


def test_non_default_canopy_becomes_parameters_json():
    case = _build(_row(expected_canopy_cover="75"))
    assert case.expected["dataset_parameters"] == (
        '[{"name":"canopy_cover","values":[75]}]'
    )


def test_blank_forest_filter_scores_no_selection():
    # the primary-forest-substitution detector: opting out must be enforced
    case = _build(_row())
    assert case.expected["context_layer"] == "no_selection"
    filtered = _build(_row(expected_forest_filter="primary_forest"))
    assert filtered.expected["context_layer"] == "primary_forest"
    # datasets without forest layers get no context expectation
    alerts = _build(
        _row(
            expected_dataset_name="integrated_alerts",
            expected_dataset_id="11",
            manifest_id="m-ialert-quant-01",
        )
    )
    assert "context_layer" not in alerts.expected


def test_two_period_whitelist_suppresses_dates():
    row = _row(
        intent="comparison",
        eval_subtype="two_period",
        evaluators="clarification;aoi;dataset;parameters;data_pull;answer;chart_type;ground_truth",
    )
    case = promote.build_case(row, "ch-comp-001", "ready", "", "31a4d1e")
    assert "start_date" not in case.expected
    assert "end_date" not in case.expected
    # a whitelist that includes date keeps the expectation
    dated = _row(evaluators="date;aoi;dataset")
    assert "start_date" in _build(dated).expected


def test_unscored_params_land_in_notes():
    case = _build(
        _row(
            expected_dataset_name="deforestation_sluc_emission_factors_by_agricultural_crop",
            expected_dataset_id="9",
            expected_canopy_cover="",
            expected_crop_types="soy",
            expected_gas_types="co2",
        )
    )
    assert case.group == "sluc"
    assert case.notes["crop_types"].startswith("soy")
    assert case.notes["gas_types"].startswith("co2")
    assert "dataset_parameters" not in case.expected


def test_next_id_numbers_scans_per_prefix():
    highest = promote.next_id_numbers(
        ["ch-quant-003", "ch-quant-010", "ch-trend-002", "ch-aoi-131", "junk"]
    )
    assert highest == {"ch-quant": 10, "ch-trend": 2, "ch-aoi": 131}


def test_config_for_manifest_matches_longest_slug():
    assert (
        config_for_manifest("tree_cover_loss__quantification.manifest.csv").slug
        == "tree_cover_loss"
    )
    assert (
        config_for_manifest("tree_cover__comparison.manifest.csv").slug == "tree_cover"
    )


def test_mechanical_expected_construction():
    cfg = DATASET_CONFIGS["tree_cover_loss"]
    manifest_row = {
        "manifest_id": "m-tcl-quant-01",
        "intent": "quantification",
        "eval_subtype": "single_year",
        "aoi_ids": "BRA",
        "start_year": "2023",
        "end_year": "2023",
        "canopy_cover": "",
        "forest_filter": "",
        "judge_note": "note",
        "expected_language": "en",
        "evaluators": "",
    }
    case_row = generate._case_from_wording(cfg, manifest_row, "wording", 0)
    assert case_row["expected_start_date"] == "2023-01-01"
    assert case_row["expected_end_date"] == "2023-12-31"
    assert case_row["expected_canopy_cover"] == "30"  # default filled in
    assert case_row["expected_dataset_id"] == "4"
    assert case_row["test_id"] == "tcl-quant-01a"
    assert case_row["test_group"] == "tcl"
    # blank date_mode emits no dates
    blank_cfg = DATASET_CONFIGS["sbtn_natural_lands_map"]
    blank_row = dict(
        manifest_row, manifest_id="m-sbtn-quant-01", canopy_cover="", forest_filter=""
    )
    blank_case = generate._case_from_wording(blank_cfg, blank_row, "w", 0)
    assert blank_case["expected_start_date"] == ""
    assert blank_case["expected_end_date"] == ""
