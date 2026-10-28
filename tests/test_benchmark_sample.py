"""tools/benchmark_sample.py: deterministic stratified BENCHMARK sampling."""

import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_sample as bs  # noqa: E402

from goldset.benchmark import from_dict  # noqa: E402
from goldset.store import Case, build_manifest, write_case, write_manifest  # noqa: E402


def make_store(root: Path, per_set: int = 30) -> Path:
    cases = []
    for set_name in ("aoi", "dataset", "quantification", "comparison", "trend"):
        for i in range(per_set):
            notes = {}
            if set_name in ("aoi", "dataset"):
                notes["difficulty"] = ("easy", "medium", "hard")[i % 3]
            expected = {"dataset_id": "1", "aoi_ids": f"X{i}"}
            if set_name == "dataset":
                expected = {"dataset_id": str(i % 10 + 1),
                            "forbidden_tools": "pull_data"}
            cases.append(Case(
                id=f"ch-{set_name}-{i:03d}", status="todo" if i == 0 else "ready",
                group=f"cohort-{i % 4}", set=set_name,
                query=f"{set_name} question {i}", expected=expected, notes=notes,
            ))
    for case in cases:
        write_case(root, case)
    write_manifest(root, build_manifest(cases, "test"))
    return root


def test_allocate_is_proportional_and_exact():
    alloc = bs.allocate({"a": 10, "b": 30, "c": 5}, 9)
    assert sum(alloc.values()) == 9
    assert alloc == {"a": 2, "b": 6, "c": 1}
    assert bs.allocate({"a": 2, "b": 1}, 10) == {"a": 2, "b": 1}


def test_build_is_deterministic_and_balanced(tmp_path):
    root = make_store(tmp_path / "cases")
    a = bs.build(root, "t", 8, 7, "2026-09-29")
    b = bs.build(root, "t", 8, 7, "2026-09-29")
    assert a == b
    assert Counter(m["type"] for m in a["members"]) == {
        "geospatial": 8, "dataset": 8, "quantification": 8, "comparison": 8, "trend": 8}
    assert from_dict(a).validate() == []
    assert bs.build(root, "t", 8, 8, "2026-09-29")["members"] != a["members"]


def test_hard_and_non_ready_are_never_sampled(tmp_path):
    root = make_store(tmp_path / "cases")
    data = bs.build(root, "t", 15, 1, "2026-09-29")
    spatial = [m for m in data["members"] if m["type"] in ("geospatial", "dataset")]
    assert spatial and all(m["difficulty"] in ("easy", "medium") for m in spatial)
    assert not any(m["id"].endswith("-000") for m in data["members"])  # status todo


def test_stages_are_frozen_from_implied_checks(tmp_path):
    root = make_store(tmp_path / "cases")
    data = bs.build(root, "t", 5, 1, "2026-09-29")
    by_type = {m["type"]: m["stages"] for m in data["members"]}
    assert by_type["quantification"] == ["retrieval"]
    assert by_type["dataset"] == ["scope", "retrieval"]  # forbidden_tools is scope


def test_too_few_eligible_cases_fails_loudly(tmp_path):
    root = make_store(tmp_path / "cases", per_set=6)
    with pytest.raises(SystemExit, match="eligible"):
        bs.build(root, "t", 20, 1, "2026-09-29")
