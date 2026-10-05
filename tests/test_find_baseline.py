"""Baseline selection for the CI release gate: newest comparable run only."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from find_baseline import find_baseline

TOOL = Path(__file__).resolve().parents[1] / "tools" / "find_baseline.py"


def write_run(runs_dir: Path, started: str, environment: str, ff, trials: int) -> Path:
    stamp = started.replace("-", "").replace(":", "")
    run_id = f"{stamp}_{environment}" + (f"_{ff}" if ff else "")
    record = {
        "run_id": run_id,
        "started": started,
        "environment": environment,
        "build": "test",
        "ff": ff,
        "harness": {"repo": "gnw-gold-evals", "sha": "x"},
        "judge_model": "claude-haiku-4-5",
        "num_trials": trials,
        "caseset_version": "cs1",
        "results": [{"uid": "u1", "id": "1-001", "checks": {"aoi_id_match": 1.0}}],
    }
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.json"
    path.write_text(json.dumps(record))
    return path


def run_tool(new_run: Path, runs_dir: Path):
    return subprocess.run(
        [sys.executable, str(TOOL), str(new_run), "--runs-dir", str(runs_dir)],
        capture_output=True,
        text=True,
    )


def test_picks_newest_run_matching_environment_ff_and_trials(tmp_path):
    runs = tmp_path / "runs"
    older = write_run(runs, "2026-08-01T00:00:00Z", "staging", None, 3)
    match = write_run(runs, "2026-08-02T00:00:00Z", "staging", None, 3)
    # Each newer run differs on exactly one comparability field.
    write_run(runs, "2026-08-03T00:00:00Z", "prod", None, 3)
    write_run(runs, "2026-08-04T00:00:00Z", "staging", "experimental", 3)
    write_run(runs, "2026-08-05T00:00:00Z", "staging", None, 1)
    new = write_run(runs, "2026-08-06T00:00:00Z", "staging", None, 3)

    assert find_baseline(new, runs) == match
    assert find_baseline(new, runs) != older

    result = run_tool(new, runs)
    assert result.returncode == 0
    assert result.stdout.strip() == str(match)


def test_new_run_is_never_its_own_baseline(tmp_path):
    runs = tmp_path / "runs"
    new = write_run(runs, "2026-08-06T00:00:00Z", "staging", None, 3)
    assert find_baseline(new, runs) is None

    # nor is a copy of it kept outside the runs directory
    elsewhere = tmp_path / "copy.json"
    elsewhere.write_text(new.read_text())
    assert find_baseline(elsewhere, runs) is None


def test_no_comparable_run_exits_nonzero_with_reason(tmp_path):
    # Today's ledger shape: the newest committed run is a prod run, so a
    # fresh 3-trial staging run without ff has nothing to compare against.
    runs = tmp_path / "runs"
    write_run(runs, "2026-08-31T00:00:00Z", "prod", None, 3)
    write_run(runs, "2026-08-04T00:00:00Z", "staging", "experimental", 3)
    new = write_run(tmp_path / "fresh", "2026-10-05T00:00:00Z", "staging", None, 3)

    assert find_baseline(new, runs) is None
    result = run_tool(new, runs)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "environment=staging, ff=unset, num_trials=3" in result.stderr
    assert "refusing to diff" in result.stderr
