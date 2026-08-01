"""Regression-diff semantics over synthetic run pairs."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from diff_runs import classify, diff  # noqa: E402

TOOL = Path(__file__).resolve().parents[1] / "tools" / "diff_runs.py"


def run_fixture(results, caseset="cs1", run_id="20260731T000000Z_staging"):
    return {
        "run_id": run_id,
        "started": "2026-07-31T00:00:00Z",
        "environment": "staging",
        "build": "GNW test",
        "ff": None,
        "harness": {"repo": "gnw-evals", "sha": "x"},
        "judge_model": "claude-haiku-4-5",
        "num_trials": 1,
        "caseset_version": caseset,
        "results": results,
    }


def run_tool(tmp_path, run_a, run_b, *flags):
    """Invoke tools/diff_runs.py as CI would, on two serialized runs."""
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(run_a))
    b.write_text(json.dumps(run_b))
    return subprocess.run(
        [sys.executable, str(TOOL), str(a), str(b), *flags],
        capture_output=True,
        text=True,
    )


RUN_A = run_fixture(
    [
        {"uid": "u1", "id": "1-001", "checks": {"aoi_id_match": 1.0, "agent_answer": 1.0}},
        {"uid": "u2", "id": "1-002", "checks": {"aoi_id_match": 0.0, "charts_answer": None}},
        {"uid": "u3", "id": "1-003", "checks": {"aoi_id_match": 1.0}},
        {"uid": None, "id": "1-009", "stale_case": True, "checks": {"aoi_id_match": 1.0}},
    ]
)
RUN_B = run_fixture(
    [
        {
            "uid": "u1",
            "id": "1-001",
            "checks": {"aoi_id_match": 1.0, "agent_answer": 0.0},
            "reasons": {"agent_answer": "figure off by 12%"},
        },
        {"uid": "u2", "id": "1-002", "checks": {"aoi_id_match": 1.0, "charts_answer": 1.0}},
        {"uid": "u4", "id": "1-004", "checks": {"aoi_id_match": 1.0}},
    ],
    run_id="20260731T010000Z_staging",
)


def test_classify_covers_all_transitions():
    assert classify(1.0, 0.0) == "regressions"
    assert classify(0.0, 1.0) == "recoveries"
    assert classify(None, 1.0) == "coverage_gained"
    assert classify(None, 0.0) == "coverage_gained"
    assert classify(1.0, None) == "coverage_lost"
    assert classify(1.0, 1.0) is None
    assert classify(None, None) is None


def test_diff_over_intersection_only():
    report = diff(RUN_A, RUN_B)
    assert report["shared_cases"] == 2  # u1, u2 — u3/u4 are churn, stale excluded
    assert report["only_in_a"] == 1 and report["only_in_b"] == 1
    assert report["stale_a"] == 1 and report["stale_b"] == 0

    assert [r["check"] for r in report["regressions"]] == ["agent_answer"]
    assert report["regressions"][0]["reason"] == "figure off by 12%"
    assert [r["check"] for r in report["recoveries"]] == ["aoi_id_match"]
    assert [r["check"] for r in report["coverage_gained"]] == ["charts_answer"]
    assert report["coverage_lost"] == []


def test_stale_rows_never_counted_as_regression():
    # the stale 1-009 in RUN_A passes aoi; absent in RUN_B — must not appear
    report = diff(RUN_A, RUN_B)
    ids = [r["id"] for kind in ("regressions", "recoveries") for r in report[kind]]
    assert "1-009" not in ids


def test_strict_refuses_cross_caseset_comparison(tmp_path):
    run_b_cs2 = run_fixture(
        RUN_B["results"], caseset="cs2", run_id="20260731T010000Z_staging"
    )
    strict = run_tool(tmp_path, RUN_A, run_b_cs2, "--strict")
    assert strict.returncode == 2
    loose = run_tool(tmp_path, RUN_A, run_b_cs2)
    assert loose.returncode == 0
    assert "comparing uid intersection only" in loose.stdout


# ---------------------------------------------------------------------------
# Release gate: INFO_ONLY exclusion, regressions_by_bucket, coverage loss.

GATE_A = run_fixture(
    [
        {
            "uid": "u1",
            "id": "1-001",
            "checks": {"aoi_id_match": 1.0, "agent_answer": 1.0, "date_coverage": 1.0},
        },
    ]
)
# date_coverage (info-only) regresses alongside two real checks — one
# dedicated (aoi_id_match -> retrieval), one shared (agent_answer ->
# analysis + explanation).
GATE_B_REAL_AND_INFO = run_fixture(
    [
        {
            "uid": "u1",
            "id": "1-001",
            "checks": {"aoi_id_match": 0.0, "agent_answer": 0.0, "date_coverage": 0.0},
        },
    ],
    run_id="20260731T010000Z_staging",
)
# ONLY date_coverage regresses; the real checks hold.
GATE_B_INFO_ONLY = run_fixture(
    [
        {
            "uid": "u1",
            "id": "1-001",
            "checks": {"aoi_id_match": 1.0, "agent_answer": 1.0, "date_coverage": 0.0},
        },
    ],
    run_id="20260731T010000Z_staging",
)
# A real check silently stops being evaluated (1.0 -> None).
COV_B_REAL_LOST = run_fixture(
    [
        {
            "uid": "u1",
            "id": "1-001",
            "checks": {"aoi_id_match": None, "agent_answer": 1.0, "date_coverage": 1.0},
        },
    ],
    run_id="20260731T010000Z_staging",
)
# Only the info-only check stops being evaluated.
COV_B_INFO_LOST = run_fixture(
    [
        {
            "uid": "u1",
            "id": "1-001",
            "checks": {"aoi_id_match": 1.0, "agent_answer": 1.0, "date_coverage": None},
        },
    ],
    run_id="20260731T010000Z_staging",
)


def test_gate_fails_on_real_regression_despite_info_only_noise(tmp_path):
    result = run_tool(tmp_path, GATE_A, GATE_B_REAL_AND_INFO, "--fail-on-regression")
    assert result.returncode == 1

    report = diff(GATE_A, GATE_B_REAL_AND_INFO)
    assert sorted(r["check"] for r in report["regressions"]) == [
        "agent_answer",
        "aoi_id_match",
        "date_coverage",
    ]
    # info-only regressions never enter the bucket counts
    assert report["regressions_by_bucket"] == {
        "retrieval": 1,
        "analysis": 1,
        "explanation": 1,
        "output": 0,
        "scope": 0,
    }


def test_gate_passes_when_only_info_only_regresses(tmp_path):
    result = run_tool(tmp_path, GATE_A, GATE_B_INFO_ONLY, "--fail-on-regression")
    assert result.returncode == 0

    report = diff(GATE_A, GATE_B_INFO_ONLY)
    assert [r["check"] for r in report["regressions"]] == ["date_coverage"]
    assert report["regressions"][0]["info_only"] is True
    assert report["regressions_by_bucket"] == {
        "retrieval": 0,
        "analysis": 0,
        "explanation": 0,
        "output": 0,
        "scope": 0,
    }


def test_fail_on_coverage_loss_gates_real_check(tmp_path):
    result = run_tool(tmp_path, GATE_A, COV_B_REAL_LOST, "--fail-on-coverage-loss")
    assert result.returncode == 1

    report = diff(GATE_A, COV_B_REAL_LOST)
    assert [c["check"] for c in report["coverage_lost"]] == ["aoi_id_match"]
    assert report["coverage_lost"][0]["info_only"] is False


def test_coverage_loss_passes_without_flag(tmp_path):
    # default OFF: current CI behaviour is preserved
    result = run_tool(tmp_path, GATE_A, COV_B_REAL_LOST)
    assert result.returncode == 0
    gated = run_tool(tmp_path, GATE_A, COV_B_REAL_LOST, "--fail-on-regression")
    assert gated.returncode == 0  # coverage loss is not a regression


def test_fail_on_coverage_loss_ignores_info_only(tmp_path):
    result = run_tool(tmp_path, GATE_A, COV_B_INFO_LOST, "--fail-on-coverage-loss")
    assert result.returncode == 0

    report = diff(GATE_A, COV_B_INFO_LOST)
    assert [c["check"] for c in report["coverage_lost"]] == ["date_coverage"]
    assert report["coverage_lost"][0]["info_only"] is True
