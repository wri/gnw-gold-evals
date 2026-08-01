"""Audit-tool semantics (PR-11): each rule catches its violation class."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from audit_cases import audit, depth_violation, dont_violations, render

from goldset.store import Case

DEEP = Case(
    id="ok-1", status="done", group="direct",
    query="Loss in Brazil between 2020 and 2022?",
    expected={"aoi_ids": "BRA", "dataset_id": "4",
              "answer": "2.9 Mha", "scope": "analyse"},
)


def test_deep_case_is_clean():
    assert depth_violation(DEEP) is None
    assert dont_violations(DEEP) == []


def test_depth_violation_single_bucket():
    shallow = Case(id="x", status="done", group="direct", query="q",
                   expected={"aoi_ids": "BRA", "dataset_id": "4"})
    # aoi + dataset are both Retrieval: 2 checks, 1 bucket
    assert "1 bucket" in depth_violation(shallow)


def test_metadata_group_is_exempt():
    meta = Case(id="m", status="done", group="metadata", query="resolution?",
                expected={"text": "30 x 30 meters"})
    assert depth_violation(meta) is None
    assert dont_violations(meta) == []


def test_relative_dates_flagged_only_with_pinned_expectations():
    pinned = Case(id="r1", status="done", group="direct",
                  query="change in the past decade?",
                  expected={"answer": "42 ha", "dataset_id": "0", "scope": "analyse"})
    assert any("relative-date" in v for v in dont_violations(pinned))
    routing_only = Case(id="r2", status="done", group="direct",
                        query="most recent year of loss data?",
                        expected={"dataset_id": "4", "scope": "analyse"})
    assert not any("relative-date" in v for v in dont_violations(routing_only))


def test_annual_dataset_dates_flagged_alert_datasets_pass():
    annual = Case(id="a", status="done", group="temporal", query="q",
                  expected={"dataset_id": "4", "start_date": "2022-01-01",
                            "end_date": "2022-12-31"})
    assert any("non-date-scoped" in v for v in dont_violations(annual))
    alert = Case(id="b", status="done", group="temporal", query="q",
                 expected={"dataset_id": "11", "start_date": "2024-07-01",
                           "end_date": "2024-12-31"})
    assert dont_violations(alert) == []
    alternatives = Case(id="c", status="done", group="temporal", query="q",
                        expected={"dataset_id": "0;11", "start_date": "2025-01-01",
                                  "end_date": "2025-04-30"})
    assert dont_violations(alternatives) == []


def test_multiturn_delta_turns_are_not_judged_only():
    mt = Case(id="mt", status="ready", group="multiturn", turns=(
        {"query": "q1", "expected": {"dataset_id": "4", "scope": "analyse"}},
        {"query": "are you sure?", "expected": {"text": "holds firm"},
         "deltas": {"retain": ["dataset_id"]}},
    ))
    assert not any("judged-only" in v for v in dont_violations(mt))


def test_audit_rollup_and_floors():
    cases = [DEEP,
             Case(id="p", status="not doing", group="direct", query="parked",
                  expected={"aoi_ids": "x"})]
    report = audit(cases)
    assert report["active"] == 1 and report["parked"] == 1
    assert report["thin_groups"] == {"direct": 1}
    assert report["thin_datasets"] == {"4": 1}
    text = render(report)
    assert "Active cases: 1 (+1 parked)" in text
    assert "- direct: 1" in text
