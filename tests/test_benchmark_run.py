"""`gold run --benchmark`: member selection, run header/record, resume guard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from goldset import cli
from goldset.benchmark import QUERY_TYPES, SCHEMA_VERSION
from goldset.ledger import read_run, write_partial_header
from goldset.store import (
    Case,
    build_manifest,
    read_manifest,
    write_case,
    write_manifest,
)

CASES = [
    Case(id=f"ch-aoi-00{i}", status="ready", group="direct", set="aoi",
         query=f"where is place {i}", expected={"aoi_ids": f"P{i}"},
         notes={"difficulty": "easy"})
    for i in range(1, 4)
]


def make_bench(tmp_path: Path, members: list[Case], errata=()) -> Path:
    cases_dir = tmp_path / "cases"
    for case in CASES:
        write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest(CASES, "test"))
    data = {
        "schema_version": SCHEMA_VERSION, "version": "t-draft", "status": "draft",
        "frozen": None, "source": {"cases_dir": cases_dir.as_posix()},
        "sampling": {}, "types": list(QUERY_TYPES),
        "members": [{"uid": c.uid, "id": c.id, "type": "geospatial", "set": "aoi",
                     "cohort": "direct", "difficulty": "easy", "stages": ["retrieval"]}
                    for c in members],
        "errata": list(errata),
    }
    path = tmp_path / "bench.json"
    path.write_text(json.dumps(data))
    return path


def test_selects_active_members_only(tmp_path):
    path = make_bench(tmp_path, CASES[:2], errata=[
        {"uid": CASES[1].uid, "date": "2026-10-01", "reason": "broken"}])
    args = argparse.Namespace(benchmark=cli.benchmark_meta(path),
                              cases_dir=tmp_path / "cases")
    assert [c.id for c in cli.select_cases(args)] == ["ch-aoi-001"]
    assert args.benchmark["members"] == 1
    assert args.benchmark["version"] == "t-draft"


def test_missing_member_is_warned(tmp_path, capsys):
    ghost = Case(id="ch-aoi-009", status="ready", group="direct", set="aoi",
                 query="gone", expected={"aoi_ids": "G"})
    path = make_bench(tmp_path, [CASES[0], ghost])
    args = argparse.Namespace(benchmark=cli.benchmark_meta(path),
                              cases_dir=tmp_path / "cases")
    assert len(cli.select_cases(args)) == 1
    assert "1 benchmark member(s) not in" in capsys.readouterr().out


def run_main(monkeypatch, *argv) -> int:
    monkeypatch.setattr(sys, "argv", ["gold", "run", *argv])
    return cli.main()


def test_main_dry_run_and_selector_conflict(tmp_path, monkeypatch, capsys):
    path = make_bench(tmp_path, CASES)
    assert run_main(monkeypatch, "--benchmark", str(path), "--dry-run") == 0
    assert "3 cases selected" in capsys.readouterr().out
    assert run_main(monkeypatch, "--benchmark", str(path), "--set", "aoi") == 1
    assert "drop --id/--group/--set" in capsys.readouterr().out


def test_run_record_and_results_dir(tmp_path, monkeypatch):
    path = make_bench(tmp_path, CASES[:1])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_TOKEN", "test-token")

    async def fake_run_cases(args, cases, entry_sink=None):
        entries = [{"uid": c.uid, "id": c.id, "checks": {"aoi_id_match": 1.0}}
                   for c in cases]
        for entry in entries:
            entry_sink(entry)
        return entries

    monkeypatch.setattr(cli, "run_cases", fake_run_cases)
    assert run_main(monkeypatch, "--benchmark", str(path), "--env", "prod",
                    "--trials", "3") == 0
    runs = list((tmp_path / "results" / "benchmark" / "runs").glob("*.json"))
    assert len(runs) == 1
    record = read_run(runs[0])
    assert record["benchmark"]["version"] == "t-draft"
    assert record["benchmark"]["members"] == 1
    assert record["caseset"] == "cases"
    assert [e["id"] for e in record["results"]] == ["ch-aoi-001"]


def test_resume_refuses_changed_manifest(tmp_path, monkeypatch, capsys):
    path = make_bench(tmp_path, CASES)
    meta = cli.benchmark_meta(path)
    results = tmp_path / "results"
    header = {
        "run_id": "20260929T100000Z_prod", "started": "2026-09-29T10:00:00Z",
        "environment": "prod", "resolved_url": "https://example.test", "ff": None,
        "build": "b", "trials": 3, "workers": 1, "trial_timeout": 900.0,
        "slow_threshold": 180.0, "cases_dir": str(tmp_path / "cases"),
        "caseset_version": read_manifest(tmp_path / "cases")["caseset_version"],
        "status_exclude": "not doing", "id": None, "group": None, "set": None,
        "benchmark": meta, "note": None,
    }
    write_partial_header(results, header)
    data = json.loads(path.read_text())
    data["errata"] = [{"uid": CASES[0].uid, "date": "2026-10-01", "reason": "x"}]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    args = argparse.Namespace(results_dir=results, resume="20260929T100000Z_prod")
    assert cli.resume_run(args) == 1
    assert "has changed since the run started" in capsys.readouterr().out


@pytest.fixture(autouse=True)
def _no_git(monkeypatch):
    monkeypatch.setattr(cli, "_harness_sha", lambda: "test")
