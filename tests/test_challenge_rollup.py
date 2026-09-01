"""Unit tests for tools/challenge_rollup.py.

The rollup is CHALLENGE's verdict mechanism (rates, never regression
counts), so the properties that matter are: errors leave the denominator
(availability, not quality), info-only checks never fail a row, strict
requires every trial clean, stale/uncovered/not-run are reported but never
counted, and targets compare against the majority-verdict rate.

Usage
$ uv run python -m pytest tests/test_challenge_rollup.py -v
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location(
    "challenge_rollup", ROOT / "tools" / "challenge_rollup.py"
)
challenge_rollup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(challenge_rollup)

from goldset.store import Case, build_manifest, write_case, write_manifest  # noqa: E402


def make_store(tmp_path):
    cases = [
        Case(
            id="ch-t-001", status="ready", group="g1",
            query="Go to A", expected={"aoi_ids": "AAA"},
            notes={"difficulty": "easy"},
        ),
        Case(
            id="ch-t-002", status="ready", group="g1",
            query="Go to B", expected={"aoi_ids": "BBB"},
            notes={"difficulty": "easy"},
        ),
        Case(
            id="ch-t-003", status="ready", group="g1",
            query="Go to C", expected={"aoi_ids": "CCC"},
            notes={"difficulty": "hard"},
        ),
        Case(
            id="ch-t-004", status="ready", group="g2",
            query="Go to D", expected={"aoi_ids": "DDD"},
            notes={"difficulty": "medium"},
        ),
        Case(
            id="ch-t-005", status="todo", group="g2",
            query="Go to E", expected={},
            notes={"difficulty": "hard"},
        ),
    ]
    cases_dir = tmp_path / "cases"
    for case in cases:
        write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest(cases, "test"))
    return cases_dir, {case.uid: case for case in cases}


def make_run(uids):
    """pass, fail, error, pass-but-flapping-trials, plus one stale entry."""
    return {
        "run_id": "20260901T000000Z_prod",
        "build": "test-build",
        "environment": "prod",
        "ff": None,
        "num_trials": 3,
        "caseset": "challenge",
        "caseset_version": "abc",
        "results": [
            {   # pass; the info-only 0.0 must not fail the row
                "uid": uids["ch-t-001"],
                "id": "ch-t-001",
                "checks": {"aoi_id_match": 1.0, "date_coverage": 0.0},
            },
            {
                "uid": uids["ch-t-002"],
                "id": "ch-t-002",
                "checks": {"aoi_id_match": 0.0},
            },
            {
                "uid": uids["ch-t-003"],
                "id": "ch-t-003",
                "checks": {},
                "error": "TimeoutError",
            },
            {   # majority pass, one flapping trial -> strict fails
                "uid": uids["ch-t-004"],
                "id": "ch-t-004",
                "checks": {"aoi_id_match": 1.0},
                "trials": {
                    "0": {"checks": {"aoi_id_match": 1.0}},
                    "1": {"checks": {"aoi_id_match": 0.0}},
                    "2": {"checks": {"aoi_id_match": 1.0}},
                },
            },
            {
                "uid": "f" * 16,
                "id": "gone-001",
                "checks": {"aoi_id_match": 1.0},
            },
        ],
    }


def build(tmp_path):
    cases_dir, by_uid = make_store(tmp_path)
    uids = {case.id: uid for uid, case in by_uid.items()}
    run = make_run(uids)
    return challenge_rollup.rollup_run(run, by_uid), cases_dir


def test_wilson_known_value():
    lo, hi = challenge_rollup.wilson(8, 10)
    assert round(lo, 2) == 0.49
    assert round(hi, 2) == 0.94
    assert challenge_rollup.wilson(0, 0) == (0.0, 1.0)


def test_rates_and_denominators(tmp_path):
    rollup, _ = build(tmp_path)
    overall = rollup["overall"]
    # measured = pass, fail, flapping-pass; error and stale excluded
    assert overall["n"] == 3
    assert overall["passed"] == 2
    assert overall["rate"] == 2 / 3
    assert 0.0 <= overall["ci_low"] < overall["rate"] < overall["ci_high"] <= 1.0
    # strict: the flapping row drops out
    assert overall["strict_passed"] == 1
    assert rollup["verdicts"] == {"pass": 2, "fail": 1, "error": 1, "uncovered": 0}


def test_error_is_availability_not_quality(tmp_path):
    rollup, _ = build(tmp_path)
    # 4 non-stale rows, 1 error
    assert rollup["availability"] == 3 / 4
    assert all(e["id"] == "ch-t-003" for e in rollup["errored"])


def test_grouping(tmp_path):
    rollup, _ = build(tmp_path)
    g1 = rollup["by_group"]["g1"]
    assert (g1["n"], g1["passed"]) == (2, 1)
    g2 = rollup["by_group"]["g2"]
    assert (g2["n"], g2["passed"], g2["strict_passed"]) == (1, 1, 0)
    easy = rollup["by_difficulty"]["easy"]
    assert (easy["n"], easy["passed"]) == (2, 1)
    # the errored hard case never enters difficulty tallies
    assert "hard" not in rollup["by_difficulty"]


def test_stale_and_not_run_reported_never_counted(tmp_path):
    rollup, _ = build(tmp_path)
    assert rollup["stale"] == ["gone-001"]
    # the todo case exists in the store but was not in the run
    assert rollup["not_run"] == ["ch-t-005"]


def test_failing_rows_name_the_checks(tmp_path):
    rollup, _ = build(tmp_path)
    assert rollup["failing"] == [
        {
            "id": "ch-t-002",
            "group": "g1",
            "difficulty": "easy",
            "failed_checks": "aoi_id_match",
        }
    ]


def test_targets_and_render(tmp_path):
    rollup, _ = build(tmp_path)
    targets = {"targets": {"g1": 0.9, "g2": 0.5}, "overall": 0.5, "meta": {}}
    text = challenge_rollup.render_markdown([rollup], targets)
    assert "pass rate **66.7%** (2/3" in text
    assert "MET (+16.7 pts)" in text        # overall 66.7 vs 50
    assert "90% / BELOW (-40.0 pts)" in text  # g1 50 vs 90
    assert "Errored rows (availability, not quality)" in text
    assert "ch-t-005" in text  # not-run listing


def test_cross_run_table_warns_on_mixed_config(tmp_path):
    rollup, _ = build(tmp_path)
    other = dict(rollup, num_trials=1, run_id="20260902T000000Z_prod")
    text = challenge_rollup.render_markdown(
        [rollup, other], {"targets": {}, "overall": None, "meta": {}}
    )
    assert "NOT comparable" in text
    assert "Cross-run rates" in text


def test_load_targets_missing_file(tmp_path):
    targets = challenge_rollup.load_targets(tmp_path / "absent.yml")
    assert targets == {"targets": {}, "overall": None, "meta": {}}
