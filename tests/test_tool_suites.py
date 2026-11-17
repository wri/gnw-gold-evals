"""Which store or ledger each tool reads when no dir is passed.

The tools run as subprocesses in a temporary working directory holding a
small cases/challenge and cases/v2, so their relative defaults resolve
there and the committed stores and ledgers are never touched.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from goldset.ledger import write_run
from goldset.store import Case, build_manifest, write_case, write_manifest

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"

CHALLENGE = [
    Case(id="ch-aoi-001", status="ready", group="direct", set="aoi",
         query="where is place 1", expected={"aoi_ids": "P1"}),
    Case(id="ch-aoi-002", status="ready", group="direct", set="aoi",
         query="where is place 2", expected={"aoi_ids": "P2"}),
]
GOLD = [
    Case(id="1-001", status="ready", group="direct", query="q one",
         expected={"dataset_id": "4"}),
]


def write_store(cases_dir: Path, cases: list[Case]) -> None:
    for case in cases:
        write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest(cases, "test"))


@pytest.fixture
def repo(tmp_path):
    write_store(tmp_path / "cases" / "challenge", CHALLENGE)
    write_store(tmp_path / "cases" / "v2", GOLD)
    shutil.copy(REPO / "cases" / "zeno_catalog.json", tmp_path / "cases")
    return tmp_path


def tool(cwd: Path, name: str, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOLS / f"{name}.py"), *argv],
                          cwd=cwd, capture_output=True, text=True, check=False)


# --- case-store tools: default challenge ----------------------------------------

@pytest.mark.parametrize("argv, count", [
    ([], 2),
    (["--suite", "benchmark"], 2),
    (["--suite", "gold"], 1),
    (["--suite", "gold", "--cases-dir", "cases/challenge"], 2),
])
def test_check_store(repo, argv, count):
    proc = tool(repo, "check", *argv)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"ok: {count} cases" in proc.stdout


def test_coverage_doc_store(repo):
    assert tool(repo, "coverage_doc").returncode == 0
    assert (repo / "cases" / "challenge" / "COVERAGE.md").exists()
    assert not (repo / "cases" / "v2" / "COVERAGE.md").exists()
    assert tool(repo, "coverage_doc", "--suite", "gold").returncode == 0
    assert (repo / "cases" / "v2" / "COVERAGE.md").exists()
    proc = tool(repo, "coverage_doc", "--check", "--cases-dir", "cases/v2")
    assert proc.returncode == 0, proc.stdout


def test_unknown_suite_is_refused(repo):
    proc = tool(repo, "check", "--suite", "golden")
    assert proc.returncode == 2 and "invalid choice" in proc.stderr


# --- ledger tools ------------------------------------------------------------------

def write_ledger_run(root: Path, ledger: str, run_id: str, cases: list[Case],
                     caseset: str | None, **extra) -> Path:
    run = {
        "run_id": run_id, "started": "2026-11-17T10:00:00Z", "environment": "prod",
        "build": "b", "ff": None, "harness": {"repo": "gnw-gold-evals", "sha": "t"},
        "judge_model": "j", "num_trials": 3, "caseset_version": "cs",
        "results": [{"uid": c.uid, "id": c.id, "checks": {"aoi_id_match": 0.0}}
                    for c in cases],
        **extra,
    }
    if caseset is not None:
        run["caseset"] = caseset
    return write_run(root / "results" / ledger, run)


@pytest.fixture
def ledgers(repo):
    write_ledger_run(repo, "challenge", "20261101T000000Z_prod", CHALLENGE, "challenge")
    write_ledger_run(repo, "gold", "20261101T000000Z_prod", GOLD, "v2")
    return repo


@pytest.mark.parametrize("argv, ledger", [([], "challenge"),
                                          (["--suite", "gold"], "gold")])
def test_render_trends_ledger(ledgers, argv, ledger):
    assert tool(ledgers, "render_trends", *argv).returncode == 0
    assert (ledgers / "results" / ledger / "reports" / "trends.html").exists()
    other = {"challenge": "gold", "gold": "challenge"}[ledger]
    assert not (ledgers / "results" / other / "reports").exists()


@pytest.mark.parametrize("name, page", [("render_html", "all-runs.html"),
                                        ("render_inspector", "all-runs_inspector.html")])
@pytest.mark.parametrize("argv, ledger, query", [
    ([], "challenge", "where is place 1"),
    (["--suite", "gold"], "gold", "q one"),
])
def test_render_all_reads_the_suites_ledger_and_store(ledgers, name, page, argv,
                                                      ledger, query):
    proc = tool(ledgers, name, "--all", *argv)
    assert proc.returncode == 0, proc.stderr
    assert query in (ledgers / "results" / ledger / "reports" / page).read_text()


@pytest.mark.parametrize("name, suffix", [("render_html", ".html"),
                                          ("render_inspector", "_inspector.html")])
def test_render_one_run_reads_the_store_it_records(ledgers, name, suffix):
    run = ledgers / "results" / "challenge" / "runs" / "20261101T000000Z_prod.json"
    assert tool(ledgers, name, str(run)).returncode == 0
    page = ledgers / "results" / "challenge" / "reports" / f"20261101T000000Z_prod{suffix}"
    assert "where is place 1" in page.read_text()


@pytest.mark.parametrize("name", ["render_html", "render_inspector"])
def test_render_one_run_without_caseset_needs_a_store(ledgers, name):
    old = write_ledger_run(ledgers, "gold", "20260801T000000Z_prod", GOLD, None)
    proc = tool(ledgers, name, str(old))
    assert proc.returncode == 2 and "pass --cases-dir or --suite" in proc.stderr
    assert tool(ledgers, name, str(old), "--suite", "gold").returncode == 0
