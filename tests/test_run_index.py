"""Run index generation: committed-only enumeration, projection, freshness."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_run_index import build_index, render

TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_run_index.py"

BUCKETS = {
    "retrieval": {"dedicated": {"passed": 4, "evaluated": 5},
                  "shared": {"passed": 0, "evaluated": 0}, "rows_covered": 5},
    "rows_total": 5,
    "verdicts": {"pass": 4, "fail": 1, "error": 0, "uncovered": 0},
}


def make_run(run_id: str, caseset: str, **overrides) -> dict:
    run = {
        "run_id": run_id,
        "started": "2026-09-01T13:15:19Z",
        "environment": "prod",
        "build": "baseline",
        "ff": None,
        "harness": {"repo": "gnw-gold-evals", "sha": "28941a8"},
        "judge_model": "claude-haiku-4-5",
        "num_trials": 1,
        "caseset": caseset,
        "caseset_version": "202cff8c19f9c579",
        "results": [{"uid": "0" * 16, "id": "x-001", "checks": {}}],
        "buckets": BUCKETS,
    }
    run.update(overrides)
    return run


def write_run(results_dir: Path, set_name: str, run: dict) -> Path:
    path = results_dir / set_name / "runs" / f"{run['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run), encoding="utf-8")
    return path


def make_results_tree(tmp_path: Path) -> Path:
    results_dir = tmp_path / "results"
    write_run(results_dir, "gold",
              make_run("20260831T163347Z_prod", "v2", num_trials=3,
                       workers=10, trial_timeout=900.0))
    write_run(results_dir, "challenge",
              make_run("20260901T131519Z_prod", "challenge", build="Test AOI"))
    return results_dir


def test_index_projects_headers_and_buckets_verbatim(tmp_path):
    index = build_index(make_results_tree(tmp_path), use_glob=True)
    assert index["schema_version"] == 1
    gold = index["sets"]["gold"]
    challenge = index["sets"]["challenge"]
    assert [e["run_id"] for e in gold] == ["20260831T163347Z_prod"]
    assert [e["run_id"] for e in challenge] == ["20260901T131519Z_prod"]
    entry = gold[0]
    assert entry["path"] == "results/gold/runs/20260831T163347Z_prod.json"
    assert entry["num_trials"] == 3
    assert entry["workers"] == 10 and entry["trial_timeout"] == 900.0
    assert entry["buckets"] == BUCKETS
    # optional fields absent from the run stay absent from the entry
    assert "resumed" not in entry and "workers" not in challenge[0]
    # projection only: per-case results never enter the index
    assert "results" not in entry


def test_index_sorts_runs_and_is_deterministic(tmp_path):
    results_dir = make_results_tree(tmp_path)
    write_run(results_dir, "gold", make_run("20260801T093002Z_staging", "v2",
                                            environment="staging"))
    first = render(results_dir, use_glob=True)
    ids = [e["run_id"] for e in json.loads(first)["sets"]["gold"]]
    assert ids == sorted(ids)
    assert render(results_dir, use_glob=True) == first
    assert first.endswith("\n")


def test_empty_set_is_tolerated(tmp_path):
    results_dir = tmp_path / "results"
    write_run(results_dir, "gold", make_run("20260801T093002Z_staging", "v2"))
    index = build_index(results_dir, use_glob=True)
    assert index["sets"]["challenge"] == []


def test_run_id_filename_mismatch_fails_loudly(tmp_path):
    results_dir = tmp_path / "results"
    path = write_run(results_dir, "gold", make_run("20260801T093002Z_staging", "v2"))
    path.rename(path.with_name("renamed.json"))
    try:
        build_index(results_dir, use_glob=True)
    except SystemExit as exc:
        assert "does not match the filename" in str(exc)
    else:
        raise AssertionError("expected SystemExit on run_id/filename mismatch")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True,
    )


def test_git_mode_excludes_untracked_runs(tmp_path):
    results_dir = make_results_tree(tmp_path)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "results")
    git(tmp_path, "commit", "-q", "-m", "runs")
    write_run(results_dir, "gold",
              make_run("20260825T000000Z_local", "v2", environment="local"))
    index = build_index(results_dir)
    assert [e["run_id"] for e in index["sets"]["gold"]] == ["20260831T163347Z_prod"]


def test_check_mode_gates_freshness(tmp_path):
    results_dir = make_results_tree(tmp_path)
    base = [sys.executable, str(TOOL), "--results-dir", str(results_dir), "--glob"]
    assert subprocess.run(base, check=False).returncode == 0
    assert subprocess.run([*base, "--check"], check=False).returncode == 0
    # a new run not yet reflected in the index is drift
    write_run(results_dir, "challenge",
              make_run("20260902T074443Z_staging", "challenge",
                       environment="staging"))
    proc = subprocess.run([*base, "--check"], check=False, capture_output=True,
                          text=True)
    assert proc.returncode == 1
    assert "stale" in proc.stdout
    # regenerating clears the drift
    assert subprocess.run(base, check=False).returncode == 0
    assert subprocess.run([*base, "--check"], check=False).returncode == 0


def write_bench(repo: Path, uids: list[str], errata=()) -> None:
    from goldset.benchmark import QUERY_TYPES, SCHEMA_VERSION
    path = repo / "benchmarks" / "t-draft.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "version": "t-draft", "status": "draft",
        "frozen": None, "source": {"cases_dir": "cases/challenge"}, "sampling": {},
        "types": list(QUERY_TYPES),
        "members": [{"uid": u, "id": f"ch-aoi-{i:03d}", "type": "geospatial",
                     "set": "aoi", "cohort": "direct", "difficulty": "easy",
                     "stages": ["retrieval"]} for i, u in enumerate(uids)],
        "errata": list(errata),
    }), encoding="utf-8")


BENCH_BLOCK = {"path": "benchmarks/t-draft.json", "version": "t-draft",
               "status": "draft", "manifest_sha": "0" * 16, "members": 2}


def bench_run(run_id, uids, **overrides):
    fields = {"num_trials": 3, "benchmark": BENCH_BLOCK,
              "results": [{"uid": u, "id": "x", "checks": {}} for u in uids]}
    return make_run(run_id, "challenge", **{**fields, **overrides})


def test_benchmark_runs_are_flagged_canonical_or_not(tmp_path):
    results_dir = make_results_tree(tmp_path)
    write_bench(tmp_path, ["a" * 16, "b" * 16])
    write_run(results_dir, "benchmark", bench_run("20260929T100000Z_prod", ["a" * 16, "b" * 16]))
    write_run(results_dir, "benchmark", bench_run("20260929T110000Z_prod", ["a" * 16]))
    write_run(results_dir, "benchmark", bench_run(
        "20260929T120000Z_staging", ["a" * 16, "b" * 16],
        environment="staging", num_trials=1))
    index = build_index(results_dir, use_glob=True)
    runs = {e["run_id"]: e for e in index["sets"]["benchmark"]}
    assert runs["20260929T100000Z_prod"]["canonical"] is True
    assert runs["20260929T110000Z_prod"]["canonical_reasons"] == [
        "1 active member(s) not in the run"]
    staging = runs["20260929T120000Z_staging"]["canonical_reasons"]
    assert any("environment" in r for r in staging) and any("num_trials" in r for r in staging)
    version = index["benchmarks"]["t-draft"]
    assert version["runs"] == sorted(runs)
    assert version["canonical_runs"] == ["20260929T100000Z_prod"]
    assert "benchmark" not in index["sets"]["gold"][0]


def test_erratum_after_a_run_does_not_uncanonicalise_it(tmp_path):
    results_dir = make_results_tree(tmp_path)
    write_bench(tmp_path, ["a" * 16, "b" * 16],
                errata=[{"uid": "b" * 16, "date": "2026-10-01", "reason": "x"}])
    write_run(results_dir, "benchmark", bench_run("20260929T100000Z_prod", ["a" * 16]))
    index = build_index(results_dir, use_glob=True)
    assert index["sets"]["benchmark"][0]["canonical"] is True
    assert index["benchmarks"]["t-draft"]["voided"] == 1
