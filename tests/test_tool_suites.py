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
