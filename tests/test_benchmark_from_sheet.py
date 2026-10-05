"""tools/benchmark_from_sheet.py: curated manifest + case tagging."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_from_sheet as bfs  # noqa: E402

from goldset.benchmark import from_dict  # noqa: E402
from goldset.store import (  # noqa: E402
    Case,
    build_manifest,
    load_store,
    write_case,
    write_manifest,
)

COLS = ["benchmark_id", "source", "synthetic", "challenge_id", "benchmark_query_type", "query",
        "jtbd", "user_groups", "impact_pathway", "user_story_refs", "refresh_risk"]


def setup(tmp_path):
    cases = [
        Case(id="ch-aoi-001", status="ready", group="direct", set="aoi", query="Show Acre",
             expected={"aoi_ids": "BRA.1"}, notes={"difficulty": "easy"}),
        Case(id="ch-dataset-001", status="ready", group="tcl", set="dataset", query="Map loss",
             expected={"dataset_id": "4"}),
        Case(id="ch-quant-001", status="ready", group="tcl", set="quantification", query="How much?",
             expected={"dataset_id": "4", "data_pull": "TRUE"}),
        Case(id="ch-mon-001", status="todo", group="portfolio", set="monitoring", query="My areas?",
             expected={"dataset_id": "11"}, notes={"benchmark_id": "bm-4", "status_reason": "needs fixture"}),
    ]
    root = tmp_path / "cases"
    for c in cases:
        write_case(root, c)
    write_manifest(root, build_manifest(cases, "t"))
    seed = tmp_path / "seed.csv"
    rows = [
        ["bm-1", "existing", "FALSE", "ch-aoi-001", "spatial", "Show Acre", "7", "GIS analysts; Journalists", "1 Local stewardship", "USY-1", "low"],
        ["bm-2", "existing", "FALSE", "ch-dataset-001", "scope", "Map loss", "10,11", "Public/educators", "Cross-cutting: trust", "", ""],
        ["bm-3", "existing", "FALSE", "ch-quant-001", "quantification", "How much?", "1,5,9", "Policy/planning", "3 Policy & planning; 5 Finance", "", "medium"],
        ["bm-4", "NEW", "TRUE", "", "monitoring", "My areas?", "3,5", "Field staff", "1 Local stewardship", "", ""],
    ]
    with seed.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    return root, seed


def test_builds_members_maps_types_and_excludes_non_ready(tmp_path):
    root, seed = setup(tmp_path)
    data = bfs.build(seed, root, "t-draft", "2026-10-01", write_tags=True)
    assert from_dict(data).validate() == []
    by_id = {m["id"]: m for m in data["members"]}
    assert by_id["ch-aoi-001"]["type"] == "geospatial"
    assert by_id["ch-dataset-001"]["type"] == "refusal"        # scope -> refusal
    assert by_id["ch-quant-001"]["pathways"] == ["3", "5"]
    assert by_id["ch-dataset-001"]["pathways"] == ["x"]
    assert by_id["ch-quant-001"]["jobs"] == ["1", "5", "9"]
    assert by_id["ch-aoi-001"]["user_groups"] == ["GIS analysts", "Journalists"]
    assert [e["id"] for e in data["sampling"]["excluded"]] == ["ch-mon-001"]


def test_tagging_writes_notes_without_changing_uids(tmp_path):
    root, seed = setup(tmp_path)
    before = {c.id: u for _p, c, u in load_store(root)}
    bfs.build(seed, root, "t-draft", "2026-10-01", write_tags=True)
    after = {c.id: (u, c) for _p, c, u in load_store(root)}
    assert {k: v[0] for k, v in after.items()} == before
    notes = after["ch-quant-001"][1].notes
    assert notes["benchmark_id"] == "bm-3" and notes["jtbd"] == "1,5,9" and notes["refresh_risk"] == "medium"


@pytest.mark.parametrize("text, want", [
    ("1 Local stewardship; 4 Commitments (EUDR)", ["1", "4"]),
    ("4 Commitments & accountability; 5 Finance for nature", ["4", "5"]),
    ("Cross-cutting: trust (no misleading answers)", ["x"]),
])
def test_parse_pathways(text, want):
    assert bfs.parse_pathways(text) == want
