"""Regression-diff semantics over synthetic run pairs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from diff_runs import classify, diff


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
    import json
    import subprocess

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(RUN_A))
    b.write_text(json.dumps(run_fixture(RUN_B["results"], caseset="cs2",
                                        run_id="20260731T010000Z_staging")))
    tool = Path(__file__).resolve().parents[1] / "tools" / "diff_runs.py"
    strict = subprocess.run([sys.executable, str(tool), str(a), str(b), "--strict"],
                            capture_output=True, text=True)
    assert strict.returncode == 2
    loose = subprocess.run([sys.executable, str(tool), str(a), str(b)],
                           capture_output=True, text=True)
    assert loose.returncode == 0
    assert "comparing uid intersection only" in loose.stdout
