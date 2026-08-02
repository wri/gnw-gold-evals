"""COVERAGE.md generation: derived content, freshness gate."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from coverage_doc import render

from goldset.store import Case, build_manifest, write_case, write_manifest

CASES = [
    Case(id="1-001", status="done", group="direct",
         query="How much loss in X in 2022?",
         expected={"aoi_ids": "BRA", "dataset_id": "4", "answer": "1,000 ha",
                   "scope": "analyse"}),
    Case(id="1-002", status="not doing", group="direct", query="parked",
         expected={"answer": "n/a"},
         notes={"status_reason": "parked without a recorded reason"}),
    Case(id="mt-001", status="ready", group="multiturn",
         turns=({"query": "alerts in Puri", "expected": {"clarification": "TRUE"}},
                {"query": "Odisha one", "expected": {"scope": "analyse"},
                 "deltas": {"changed": ["aoi_ids"]}})),
]


def make_store(tmp_path: Path) -> Path:
    cases_dir = tmp_path / "v2"
    for case in CASES:
        write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest(CASES, "test"))
    return cases_dir


def test_render_derives_content_and_coverage(tmp_path):
    text = render(make_store(tmp_path))
    assert "3 cases" in text and "**2 active**" in text
    assert "| direct | 2 | 1 | done 1, not doing 1 |" in text
    # 1-001 via dataset_id_match, mt-001 via t2.state_delta — both dedicated
    assert "| retrieval | 2 | 0 | 2 | 100% |" in text
    # analysis is reachable only via shared checks (1-001's answer judges)
    assert "| analysis | 0 | 1 | 1 | 50% |" in text
    # unused fields flagged so dead checks are visible
    assert "| chart_type | 0 ← unused | chart_type_match |" in text
    # parked case surfaces with its reason
    assert "| 1-002 | not doing | direct | parked without a recorded reason |" in text
    # multiturn census
    assert "1 active conversations (2 turns)" in text
    assert "changed ×1" in text


def test_check_mode_gates_freshness(tmp_path):
    cases_dir = make_store(tmp_path)
    tool = Path(__file__).resolve().parents[1] / "tools" / "coverage_doc.py"
    base = [sys.executable, str(tool), "--cases-dir", str(cases_dir)]
    assert subprocess.run(base, check=False).returncode == 0
    assert subprocess.run([*base, "--check"], check=False).returncode == 0
    doc = cases_dir / "COVERAGE.md"
    doc.write_text(doc.read_text() + "\ndrift\n", encoding="utf-8")
    assert subprocess.run([*base, "--check"], check=False).returncode == 1
