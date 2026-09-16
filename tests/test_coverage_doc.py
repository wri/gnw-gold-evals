"""COVERAGE.md generation: derived content, freshness gate."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from coverage_doc import collect, collect_cases_index, render

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


ALL_INSTRUCTIONS = [
    "prompt_instructions", "selection_hints",
    "code_instructions", "presentation_instructions",
]

CATALOG = {
    "source": {"repo": "git@github.com:wri/project-zeno.git", "ref": "origin/main",
               "sha": "abc1234def5678", "path": "src/agent/datasets/catalog",
               "synced": "2026-08-04"},
    "datasets": [
        {"dataset_id": "0", "dataset_name": "DIST-ALERT", "parameters": [],
         "context_layers": ["driver", "natural_lands"],
         "instructions": ALL_INSTRUCTIONS},
        {"dataset_id": "4", "dataset_name": "Tree cover loss",
         "parameters": [{"name": "canopy_cover", "values": [10, 30]}],
         "context_layers": ["primary_forest", "intact_forest"],
         "instructions": ALL_INSTRUCTIONS},
        {"dataset_id": "11", "dataset_name": "Integrated alerts", "parameters": [],
         "context_layers": [], "instructions": ["selection_hints"]},
    ],
}

DATASET_CASES = [
    Case(id="d-001", status="done", group="direct", query="loss at 10%?",
         expected={"dataset_id": "4", "answer": "1 ha",
                   "context_layer": "primary_forest",
                   "dataset_parameters": '[{"name": "canopy_cover", "values": [10]}]',
                   "scope": "analyse"}),
    Case(id="d-002", status="done", group="direct", query="alerts or loss?",
         expected={"dataset_id": "0;4", "scope": "analyse"}),
    Case(id="d-003", status="done", group="direct", query="off catalog",
         expected={"dataset_id": "99", "answer": "2 ha", "scope": "analyse"}),
    Case(id="d-004", status="not doing", group="direct", query="parked",
         expected={"dataset_id": "11", "answer": "3 ha"},
         notes={"status_reason": "parked"}),
    Case(id="mt-d01", status="ready", group="multiturn",
         turns=({"query": "alerts in Puri", "expected": {"dataset_id": "0",
                                                         "clarification": "TRUE"}},
                {"query": "for Odisha", "expected": {"dataset_id": "0",
                                                     "answer": "2 ha"},
                 "deltas": {"changed": ["aoi_ids"]}})),
]


def make_dataset_store(tmp_path: Path) -> Path:
    cases_dir = tmp_path / "v2"
    for case in DATASET_CASES:
        write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest(DATASET_CASES, "test"))
    (tmp_path / "zeno_catalog.json").write_text(
        json.dumps(CATALOG), encoding="utf-8")
    return cases_dir


def test_dataset_coverage_section(tmp_path):
    text = render(make_dataset_store(tmp_path))
    assert "## Dataset coverage (project-zeno catalog)" in text
    assert "project-zeno@abc1234" in text
    # d-002 pairs with both alternatives; only d-001 is answer-graded on 4
    assert ("| 4 | Tree cover loss | 2 | 1 | canopy_cover ×1 "
            "| primary_forest ×1, intact_forest ×0 ← gap |") in text
    # mt-d01 counts once, answer-graded via turn 2; layers untouched
    assert ("| 0 | DIST-ALERT | 2 | 1 | — "
            "| driver ×0 ← gap, natural_lands ×0 ← gap |") in text
    # d-004 is inactive, so 11 has no coverage; missing instructions surface
    assert ("| 11 | Integrated alerts (missing: code_instructions, "
            "presentation_instructions, prompt_instructions) | 0 ← gap | 0 | — | — |"
            ) in text
    # ids the catalog does not know are flagged, not silently counted
    assert "not in the catalog: 99" in text
    # known gaps summarise unexercised catalog features and empty datasets
    assert "- Catalog datasets with no active case: 11." in text
    assert ("- Catalog features no active case exercises — context layers: "
            "driver (0), natural_lands (0), intact_forest (4).") in text


def test_render_derives_content_and_coverage(tmp_path):
    text = render(make_store(tmp_path))
    # no snapshot in this store: the section points at the sync tool
    assert "No catalog snapshot found" in text
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


def test_collect_matches_render(tmp_path):
    cases_dir = make_dataset_store(tmp_path)
    text = render(cases_dir)
    data = collect(cases_dir)
    # headline counts match the rendered doc
    assert f"{data['case_count']} cases" in text
    assert f"**{data['active_count']} active**" in text
    assert data["caseset_version"] in text
    # bucket rows equal the MD table cells
    for bucket, cov in data["bucket_coverage"].items():
        total = cov["dedicated"] + cov["shared_only"]
        assert (f"| {bucket} | {cov['dedicated']} | {cov['shared_only']} "
                f"| {total} |") in text
    # dataset section as data mirrors the rendered table
    ds = {row["dataset_id"]: row for row in data["dataset_coverage"]["datasets"]}
    assert ds["4"]["cases"] == 2 and ds["4"]["answer_graded"] == 1
    assert ds["4"]["parameters"] == [{"name": "canopy_cover", "cases": 1}]
    assert ds["11"]["missing_instructions"] == [
        "code_instructions", "presentation_instructions", "prompt_instructions"]
    assert data["dataset_coverage"]["unknown_dataset_ids"] == [
        {"dataset_id": "99", "cases": 1}]
    assert data["known_gaps"]["catalog_datasets_no_case"] == ["11"]
    assert data["known_gaps"]["uncovered_context_layers"] == {
        "driver": ["0"], "natural_lands": ["0"], "intact_forest": ["4"]}
    # no TARGETS.yml next to this store
    assert data["targets"] is None


def test_collect_embeds_targets(tmp_path):
    cases_dir = make_store(tmp_path)
    (cases_dir / "TARGETS.yml").write_text(
        "meta: {status: provisional}\n"
        "overall: 0.7\n"
        "sets:\n  aoi:\n    overall: 0.7\n    targets: {acronyms: 0.8}\n",
        encoding="utf-8")
    data = collect(cases_dir)
    assert data["targets"]["overall"] == 0.7
    assert data["targets"]["meta"] == {"status": "provisional"}
    assert data["targets"]["sets"]["aoi"]["targets"] == {"acronyms": 0.8}


def test_cases_index_rows(tmp_path):
    cases_dir = make_store(tmp_path)
    data = collect_cases_index(cases_dir)
    assert data["case_count"] == 3
    rows = {row["id"]: row for row in data["cases"]}
    one = rows["1-001"]
    assert one["query"] == "How much loss in X in 2022?"
    assert one["expected_fields"] == ["answer", "aoi_ids", "dataset_id", "scope"]
    # implied gating checks: base names, info-only stripped, harness recipe
    assert one["implied_checks"] == [
        "agent_answer", "answered_without_data", "aoi_id_match",
        "chart_produced", "data_pull_exists", "dataset_id_match",
        "scope_match",
    ]
    mt = rows["mt-001"]
    assert mt["turns"] == ["alerts in Puri", "Odisha one"]
    assert "query" not in mt
    assert mt["expected_fields"] == ["clarification", "scope"]
    assert mt["implied_checks"] == [
        "clarification_requested", "scope_match", "state_delta",
    ]
    assert rows["1-002"]["status"] == "not doing"
    # uids agree with the manifest, so run rows join by uid
    manifest = json.loads((cases_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c["uid"] for c in manifest["cases"]}
    assert all(row["uid"] == by_id[row["id"]] for row in data["cases"])


def test_cases_index_set_and_difficulty_notes(tmp_path):
    cases_dir = tmp_path / "challenge"
    case = Case(id="ch-aoi-001", status="ready", set="aoi", group="direct",
                query="Go to X", expected={"aoi_ids": "X"},
                notes={"difficulty": "hard", "behaviour": "select"})
    write_case(cases_dir, case)
    write_manifest(cases_dir, build_manifest([case], "test"))
    row = collect_cases_index(cases_dir)["cases"][0]
    assert row["set"] == "aoi"
    assert row["difficulty"] == "hard" and row["behaviour"] == "select"


def test_check_gates_stale_json_siblings(tmp_path):
    cases_dir = make_store(tmp_path)
    tool = Path(__file__).resolve().parents[1] / "tools" / "coverage_doc.py"
    base = [sys.executable, str(tool), "--cases-dir", str(cases_dir)]
    assert subprocess.run(base, check=False).returncode == 0
    assert subprocess.run([*base, "--check"], check=False).returncode == 0
    cov = cases_dir / "coverage.json"
    cov.write_text(cov.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    proc = subprocess.run([*base, "--check"], check=False, capture_output=True,
                          text=True)
    assert proc.returncode == 1 and "coverage.json is stale" in proc.stdout


def test_check_mode_gates_freshness(tmp_path):
    cases_dir = make_store(tmp_path)
    tool = Path(__file__).resolve().parents[1] / "tools" / "coverage_doc.py"
    base = [sys.executable, str(tool), "--cases-dir", str(cases_dir)]
    assert subprocess.run(base, check=False).returncode == 0
    assert subprocess.run([*base, "--check"], check=False).returncode == 0
    doc = cases_dir / "COVERAGE.md"
    # the Last-updated stamp exists, and a date-only difference is not drift
    text = doc.read_text(encoding="utf-8")
    assert "_Last updated: " in text
    import re
    doc.write_text(re.sub(r"_Last updated: \d{4}-\d{2}-\d{2}_",
                          "_Last updated: 2000-01-01_", text), encoding="utf-8")
    assert subprocess.run([*base, "--check"], check=False).returncode == 0
    # any real content change is drift
    doc.write_text(doc.read_text() + "\ndrift\n", encoding="utf-8")
    assert subprocess.run([*base, "--check"], check=False).returncode == 1
