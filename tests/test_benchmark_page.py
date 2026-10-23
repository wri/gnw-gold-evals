"""tools/benchmark_page.py: the page data behind the FE accuracy-benchmarks page."""

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_page as bp  # noqa: E402

from goldset.benchmark import QUERY_TYPES, SCHEMA_VERSION, from_dict  # noqa: E402
from goldset.store import Case  # noqa: E402

PASS = {"aoi_id_match": 1.0, "dataset_id_match": 1.0}
FAIL_RETRIEVAL = {"aoi_id_match": 0.0, "dataset_id_match": 1.0}


def case(cid, query, **notes):
    return Case(id=cid, status="ready", group="g", set="monitoring", query=query,
                expected={"aoi_ids": "BRA.14", "dataset_id": "11"}, notes=notes)


def entry(c, trials):
    final = {k: (1.0 if sum(t[k] == 1.0 for t in trials) >= 2 else 0.0) for k in trials[0]}
    return {"uid": c.uid, "id": c.id, "checks": final,
            "trials": [{"checks": t} for t in trials], "trace_url": f"https://t/{c.id}"}


def setup(tmp_path):
    a = case("ch-mon-001", "Alerts in Pará?", aoi_type="Subnational",
             expectations="draft 2026-10-23: needs review")
    b = case("ch-mon-002", "Alerts in Acre?")
    bench = from_dict({
        "schema_version": SCHEMA_VERSION, "version": "t", "status": "draft", "frozen": None,
        "source": {"cases_dir": "cases/challenge"}, "sampling": {"excluded": [{"id": "x"}]},
        "types": [{**t, "measured": t["key"] == "monitoring"} for t in QUERY_TYPES],
        "members": [
            {"uid": a.uid, "id": a.id, "type": "monitoring", "set": "monitoring", "cohort": "g",
             "difficulty": "", "stages": ["retrieval"], "use_cases": ["UC1", "UC3"], "synthetic": True},
            {"uid": b.uid, "id": b.id, "type": "monitoring", "set": "monitoring", "cohort": "g",
             "difficulty": "", "stages": ["retrieval"], "use_cases": ["UC1"]},
        ],
        "errata": [],
    })
    run = {"run_id": "r", "started": "2026-10-23T09:00:00Z", "environment": "prod", "ff": None,
           "num_trials": 3, "harness": {"sha": "abc"},
           "benchmark": {"path": "benchmarks/t.json", "manifest_sha": "f" * 16},
           "results": [entry(a, [PASS, PASS, FAIL_RETRIEVAL]),
                       entry(b, [FAIL_RETRIEVAL, FAIL_RETRIEVAL, PASS])]}
    art = tmp_path / "artifacts"
    art.mkdir()
    with gzip.open(art / f"{a.uid}.json.gz", "wt") as f:
        json.dump({"tool_calls": [{"name": "pick_aoi"}, {"name": "pull_data"}],
                   "aoi_selection": {"aois": [{"src_id": "BRA.14_1"}]},
                   "dataset": {"dataset_id": 11, "start_date": "2026-09-23", "end_date": "2026-10-23"},
                   "final_answer": "**Yes**, 120 ha of alerts."}, f)
    return run, bench, {a.uid: a, b.uid: b}, art


def test_page_summary_tiers_and_failure_modes(tmp_path):
    run, bench, cases, art = setup(tmp_path)
    page = bp.build_page(run, bench, cases, art)
    s = page["summary"]
    assert (s["scored"], s["passed"]) == (2, 1)
    assert (s["every_time"], s["majority"], s["any_time"]) == (0.0, 0.5, 1.0)
    assert s["failure_modes"] == {"retrieval": 1}
    assert s["consistency"] == {"complete": 1, "clean": 0}
    assert page["benchmark"]["excluded"] == 1


def test_page_groups_by_use_case_with_composition(tmp_path):
    run, bench, cases, art = setup(tmp_path)
    uc = {g["key"]: g for g in bp.build_page(run, bench, cases, art)["use_cases"]}
    assert set(uc) == {"UC1", "UC3"}
    assert uc["UC1"]["scored"] == 2 and uc["UC3"]["passed"] == 1
    assert [tuple(d) for d in uc["UC1"]["composition"]["datasets"]] == [("Disturbance alerts", 2)]
    assert ("Sub-national area", 2) in [tuple(p) for p in uc["UC1"]["composition"]["places"]]


def test_page_questions_carry_attempts_and_failed_checks(tmp_path):
    run, bench, cases, art = setup(tmp_path)
    qs = {q["id"]: q for q in bp.build_page(run, bench, cases, art)["questions"]}
    a, b = qs["ch-mon-001"], qs["ch-mon-002"]
    assert a["trials_right"] == [True, True, False] and a["drafted"] is True
    assert a["attempts"][0]["aoi_ids"] == ["BRA.14_1"]
    assert a["attempts"][0]["answer_excerpt"] == "Yes, 120 ha of alerts."
    assert a["attempts"][1] is None                      # no artifact for trial 2
    assert b["verdict"] == "fail" and b["primary_failure"] == "retrieval"
    [failed] = b["failed_checks"]
    assert failed["check"] == "aoi_id_match" and failed["per_trial"] == [False, False, True]
