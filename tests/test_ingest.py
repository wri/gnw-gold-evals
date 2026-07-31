"""Ingest semantics: joining, staleness, idempotence."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from goldset.store import Case, build_manifest, write_case, write_manifest

from ingest_run import build_entry, started_from_filename  # noqa: E402

CASE = Case(
    id="1-002",
    status="todo",
    group="direct",
    query="Sao Paulo disturbance in H2 2024?",
    expected={"aoi_ids": "BRA.25", "answer": "1,319,600 ha"},
)

ROW = {
    "test_id": "1-002",
    "query": "Sao Paulo disturbance in H2 2024?",
    "aoi_id_match_score": "1.0",
    "agent_answer_score": "0.0",
    "agent_answer_score_reason": "expected 1,319,600 ha; actual 1,299,278 ha",
    "chart_answer_score_reason": "pie shows all three tiers",
    "charts_answer_score": "0.0",
    "nudge_match_score": "",
    "overall_score": "0.67",
    "duration_seconds": "49.94",
    "trace_url": "https://langfuse.example/t/abc",
}


def test_join_by_uid_column():
    row = {**ROW, "uid": CASE.uid}
    entry = build_entry(row, {}, {CASE.uid})
    assert entry["uid"] == CASE.uid
    assert "joined_by" not in entry and "stale_case" not in entry


def test_fallback_join_by_test_id_and_query():
    entry = build_entry(ROW, {"1-002": CASE}, set())
    assert entry["uid"] == CASE.uid
    assert entry["joined_by"] == "test_id"


def test_query_mismatch_is_stale_not_rekeyed():
    edited = Case(**{**CASE.__dict__, "query": "Sao Paulo alerts in H2 2024?"})
    entry = build_entry(ROW, {"1-002": edited}, set())
    assert entry["uid"] is None
    assert entry["stale_case"] is True


def test_checks_reasons_and_metadata_mapping():
    entry = build_entry(ROW, {"1-002": CASE}, set())
    assert entry["checks"] == {
        "aoi_id_match": 1.0,
        "agent_answer": 0.0,
        "charts_answer": 0.0,
        "nudge_match": None,
    }
    assert entry["reasons"]["charts_answer"] == "pie shows all three tiers"
    assert entry["latency_s"] == 49.9
    assert entry["trace_url"] == "https://langfuse.example/t/abc"
    assert "overall" not in str(entry["checks"])


def test_started_from_filename():
    path = Path("gold_run6_staging_20260731_120022_detailed.csv")
    assert started_from_filename(path) == "2026-07-31T12:00:22Z"
    assert started_from_filename(Path("nodate.csv")) is None


def test_end_to_end_idempotent(tmp_path):
    import csv
    import subprocess

    cases_dir = tmp_path / "cases"
    write_case(cases_dir, CASE)
    write_manifest(cases_dir, build_manifest([CASE], "test"))
    detailed = tmp_path / "run_20260731_120022_detailed.csv"
    with detailed.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROW))
        writer.writeheader()
        writer.writerow(ROW)

    tool = Path(__file__).resolve().parents[1] / "tools" / "ingest_run.py"
    command = [
        sys.executable, str(tool),
        "--detailed", str(detailed),
        "--cases-dir", str(cases_dir),
        "--results-dir", str(tmp_path / "results"),
        "--environment", "staging",
        "--build", "GNW test",
        "--harness-sha", "unknown",
    ]
    assert subprocess.run(command, check=False).returncode == 0
    out = tmp_path / "results" / "runs" / "20260731T120022Z_staging.json"
    first = out.read_text()
    assert subprocess.run(command, check=False).returncode == 0
    assert out.read_text() == first
