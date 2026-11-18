"""`run --suite` and `prune-artifacts --suite`, end to end through main().

Every test runs in a temporary working directory holding its own
cases/challenge and cases/v2 stores, so the relative suite dirs resolve
there and nothing touches the committed ledgers. No network: run_cases is
faked and no case carries ground truth.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from goldset import cli
from goldset.benchmark import QUERY_TYPES, SCHEMA_VERSION
from goldset.ledger import partial_path, read_run, write_partial_header
from goldset.store import (
    Case,
    build_manifest,
    read_manifest,
    write_case,
    write_manifest,
)

CHALLENGE = [
    Case(id="ch-aoi-001", status="ready", group="direct", set="aoi",
         query="where is place 1", expected={"aoi_ids": "P1"}),
    Case(id="ch-aoi-002", status="todo", group="direct", set="aoi",
         query="where is place 2", expected={"aoi_ids": "P2"}),
]
GOLD = [
    Case(id="1-001", status="ready", group="direct", query="q one",
         expected={"dataset_id": "4"}),
    Case(id="1-002", status="todo", group="direct", query="q two",
         expected={"dataset_id": "11"}),
]
RUN_ID = "20261117T100000Z_prod"


def write_store(cases_dir: Path, cases: list[Case]) -> None:
    for case in cases:
        write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest(cases, "test"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_store(tmp_path / "cases" / "challenge", CHALLENGE)
    write_store(tmp_path / "cases" / "v2", GOLD)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "_harness_sha", lambda: "test")
    monkeypatch.setenv("API_TOKEN", "test-token")

    async def fake_run_cases(args, cases, entry_sink=None):
        entries = [{"uid": c.uid, "id": c.id, "checks": {"aoi_id_match": 1.0}}
                   for c in cases]
        for entry in entries:
            entry_sink(entry)
        return entries

    monkeypatch.setattr(cli, "run_cases", fake_run_cases)
    return tmp_path


def main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["gold", *argv])
    return cli.main()


def make_bench(root: Path) -> Path:
    path = root / "bench.json"
    path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "version": "t-draft", "status": "draft",
        "frozen": None, "source": {"cases_dir": "cases/challenge"},
        "sampling": {}, "types": list(QUERY_TYPES),
        "members": [{"uid": CHALLENGE[0].uid, "id": CHALLENGE[0].id,
                     "type": "geospatial", "set": "aoi", "cohort": "direct",
                     "difficulty": "easy", "stages": ["retrieval"]}],
        "errata": [],
    }))
    return path


def only_run(root: Path, ledger: str) -> dict:
    runs = list((root / "results" / ledger / "runs").glob("*.json"))
    assert len(runs) == 1, runs
    return read_run(runs[0])


# --- run: what lands where -----------------------------------------------------

def test_no_suite_is_refused_and_lists_the_suites(repo, monkeypatch, capsys):
    assert main(monkeypatch, "run", "--dry-run") == 1
    out = capsys.readouterr().out
    assert "--suite challenge" in out and "--suite gold" in out
    assert "--benchmark MANIFEST" in out


def test_suite_challenge_files_in_the_challenge_ledger(repo, monkeypatch, capsys):
    assert main(monkeypatch, "run", "--suite", "challenge", "--env", "prod",
                "--status-exclude", "not doing") == 0
    record = only_run(repo, "challenge")
    assert record["caseset"] == "challenge"
    assert not (repo / "results" / "gold").exists()
    out = capsys.readouterr().out
    assert f"--resume {record['run_id']} --suite challenge" in out


@pytest.mark.parametrize("argv0", ["/repo/.venv/bin/evals", "/repo/.venv/bin/gold"])
def test_resume_hint_uses_the_invoked_name(repo, monkeypatch, capsys, argv0):
    monkeypatch.setattr(sys, "argv", [argv0, "run", "--suite", "gold", "--env", "prod"])
    assert cli.main() == 0
    run_id = only_run(repo, "gold")["run_id"]
    name = Path(argv0).name
    assert f"(if killed: {name} run --resume {run_id} --suite gold)" in \
        capsys.readouterr().out


def test_suite_gold_files_in_the_gold_ledger(repo, monkeypatch):
    assert main(monkeypatch, "run", "--suite", "gold", "--env", "prod") == 0
    assert only_run(repo, "gold")["caseset"] == "v2"


@pytest.mark.parametrize("store, ledger", [("cases/challenge", "challenge"),
                                           ("cases/v2", "gold")])
def test_known_store_alone_picks_its_ledger(repo, monkeypatch, store, ledger):
    assert main(monkeypatch, "run", "--cases-dir", store, "--env", "prod",
                "--status-exclude", "not doing") == 0
    only_run(repo, ledger)


def test_benchmark_files_in_the_benchmark_ledger(repo, monkeypatch):
    bench = make_bench(repo)
    assert main(monkeypatch, "run", "--benchmark", str(bench), "--env", "prod") == 0
    assert only_run(repo, "benchmark")["benchmark"]["version"] == "t-draft"


def test_explicit_results_dir_for_an_unknown_store(repo, monkeypatch, capsys):
    write_store(repo / "elsewhere", GOLD)
    assert main(monkeypatch, "run", "--cases-dir", "elsewhere",
                "--results-dir", "out", "--env", "prod") == 0
    assert len(list((repo / "out" / "runs").glob("*.json"))) == 1
    assert "--results-dir out" in capsys.readouterr().out


@pytest.mark.parametrize("argv, message", [
    (["--suite", "benchmark"], "--suite benchmark needs --benchmark MANIFEST"),
    (["--cases-dir", "elsewhere"], "pass --results-dir"),
    (["--cases-dir", "cases/challenge", "--results-dir", "results/gold"],
     "is the challenge store but results/gold is the gold ledger"),
    (["--cases-dir", "cases/challenge", "--results-dir", "results/benchmark"],
     "only a --benchmark MANIFEST run is filed there"),
    (["--suite", "gold", "--results-dir", "results/challenge"],
     "is the gold store but results/challenge is the challenge ledger"),
])
def test_refusals_happen_before_anything_is_written(repo, monkeypatch, capsys,
                                                    argv, message):
    assert main(monkeypatch, "run", *argv, "--env", "prod") == 1
    assert message in capsys.readouterr().out
    assert not (repo / "results").exists()


def test_benchmark_refuses_another_suite_or_store(repo, monkeypatch, capsys):
    bench = str(make_bench(repo))
    assert main(monkeypatch, "run", "--benchmark", bench, "--suite", "gold") == 1
    assert "drop --suite gold" in capsys.readouterr().out
    assert main(monkeypatch, "run", "--benchmark", bench,
                "--cases-dir", "cases/v2") == 1
    assert "not the manifest's source store" in capsys.readouterr().out
    assert main(monkeypatch, "run", "--benchmark", bench,
                "--results-dir", "results/challenge") == 1
    assert "filed in results/benchmark" in capsys.readouterr().out


# --- status exclusion -------------------------------------------------------------

def selected(capsys) -> list[str]:
    return sorted(line.split()[0] for line in capsys.readouterr().out.splitlines()
                  if line.startswith(("ch-", "1-")))


@pytest.mark.parametrize("argv", [["--suite", "challenge"],
                                  ["--cases-dir", "cases/challenge"]])
def test_challenge_store_holds_back_todo_rows(repo, monkeypatch, capsys, argv):
    assert main(monkeypatch, "run", *argv, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "suite challenge: cases/challenge -> results/challenge; " \
           "status excluded: not doing,todo" in out
    assert "ch-aoi-001" in out and "ch-aoi-002" not in out


def test_explicit_status_exclude_wins(repo, monkeypatch, capsys):
    assert main(monkeypatch, "run", "--suite", "challenge",
                "--status-exclude", "not doing", "--dry-run") == 0
    assert selected(capsys) == ["ch-aoi-001", "ch-aoi-002"]


def test_gold_keeps_todo_rows(repo, monkeypatch, capsys):
    assert main(monkeypatch, "run", "--suite", "gold", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "status excluded: not doing\n" in out
    assert "1-001" in out and "1-002" in out


def test_benchmark_selection_ignores_status(repo, monkeypatch, capsys):
    assert main(monkeypatch, "run", "--benchmark", str(make_bench(repo)),
                "--dry-run") == 0
    assert "suite benchmark: cases/challenge -> results/benchmark; " \
           "members of t-draft" in capsys.readouterr().out


# --- resume ---------------------------------------------------------------------

def leave_partial(root: Path, ledger: str) -> Path:
    header = {
        "run_id": RUN_ID, "started": "2026-11-17T10:00:00Z", "environment": "prod",
        "resolved_url": "https://example.test", "ff": None, "build": "b",
        "trials": 1, "workers": 1, "trial_timeout": 900.0, "slow_threshold": 180.0,
        "cases_dir": "cases/challenge",
        "caseset_version": read_manifest(root / "cases" / "challenge")["caseset_version"],
        "status_exclude": "not doing", "id": None, "group": None, "set": None,
        "note": None,
    }
    return write_partial_header(root / "results" / ledger, header)


def test_resume_finds_the_partial_without_a_suite(repo, monkeypatch, capsys):
    partial = leave_partial(repo, "challenge")
    assert main(monkeypatch, "run", "--resume", RUN_ID) == 0
    assert not partial.exists()
    assert only_run(repo, "challenge")["resumed"] is True


def test_resume_with_no_partial_names_the_ledgers(repo, monkeypatch, capsys):
    assert main(monkeypatch, "run", "--resume", RUN_ID) == 1
    out = capsys.readouterr().out
    assert "results/challenge/runs" in out and "results/gold/runs" in out


def test_resume_with_two_partials_asks_for_the_ledger(repo, monkeypatch, capsys):
    leave_partial(repo, "challenge")
    leave_partial(repo, "gold")
    assert main(monkeypatch, "run", "--resume", RUN_ID) == 1
    assert "pass --suite or --results-dir" in capsys.readouterr().out
    # naming the ledger settles it
    assert main(monkeypatch, "run", "--resume", RUN_ID, "--suite", "gold") == 0
    assert not partial_path(repo / "results" / "gold", RUN_ID).exists()
    assert partial_path(repo / "results" / "challenge", RUN_ID).exists()


# --- prune-artifacts ---------------------------------------------------------------

def test_prune_needs_a_ledger(repo, monkeypatch, capsys):
    assert main(monkeypatch, "prune-artifacts") == 1
    assert "choose a ledger" in capsys.readouterr().out


def test_prune_the_suites_ledger(repo, monkeypatch):
    for ledger in ("challenge", "gold"):
        for run in ("20261101T000000Z_prod", "20261102T000000Z_prod"):
            (repo / "results" / ledger / "artifacts" / run).mkdir(parents=True)
    assert main(monkeypatch, "prune-artifacts", "--suite", "challenge",
                "--keep-runs", "1") == 0
    assert [d.name for d in (repo / "results/challenge/artifacts").iterdir()] == [
        "20261102T000000Z_prod"]
    assert len(list((repo / "results/gold/artifacts").iterdir())) == 2
