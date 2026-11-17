"""tools/benchmark_page.py: the page data behind the FE accuracy-benchmarks page."""

import gzip
import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_page as bp  # noqa: E402

from goldset.benchmark import QUERY_TYPES, SCHEMA_VERSION, from_dict  # noqa: E402
from goldset.buckets import row_verdict  # noqa: E402
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


# --- failure modes by accuracy standard --------------------------------------

TEXT_PASS = {"aoi_id_match": 1.0, "expected_text_match": 1.0, "agent_answer": 1.0}
TEXT_FAIL_EXPLANATION = {"aoi_id_match": 1.0, "expected_text_match": 0.0, "agent_answer": 1.0}
TEXT_FAIL_RETRIEVAL = {"aoi_id_match": 0.0, "expected_text_match": 1.0, "agent_answer": 1.0}
TEXT_FAIL_SHARED = {"aoi_id_match": 1.0, "expected_text_match": 1.0, "agent_answer": 0.0}


def by_standard(*entries):
    return bp.group_stats(list(entries))["failure_modes_by_standard"]


def test_verdict_pass_with_one_wrong_trial_counts_under_every_time_only():
    c = case("ch-mon-010", "q10")
    modes = by_standard(entry(c, [TEXT_PASS, TEXT_PASS, TEXT_FAIL_RETRIEVAL]))
    assert modes == {"every_time": {"retrieval": 1}, "majority": {}, "any_time": {}}


def test_verdict_fail_keeps_its_primary_failure_under_every_standard():
    # Explanation fails on two trials, retrieval on the other, so no trial is
    # right and the verdict fails at explanation.
    c = case("ch-mon-011", "q11")
    e = entry(c, [TEXT_FAIL_EXPLANATION, TEXT_FAIL_EXPLANATION, TEXT_FAIL_RETRIEVAL])
    assert row_verdict(e) == "fail"
    assert by_standard(e) == {s: {"explanation": 1} for s in ("every_time", "majority", "any_time")}


def test_only_a_shared_check_failing_is_unattributed():
    c = case("ch-mon-012", "q12")
    modes = by_standard(entry(c, [TEXT_FAIL_SHARED, TEXT_FAIL_SHARED, TEXT_PASS]))
    assert modes == {s: {"unattributed": 1} for s in ("every_time", "majority")} | {"any_time": {}}
    passing = by_standard(entry(c, [TEXT_PASS, TEXT_PASS, TEXT_FAIL_SHARED]))
    assert passing["every_time"] == {"unattributed": 1} and passing["majority"] == {}


def mixed_entries():
    trials = [TEXT_PASS, TEXT_FAIL_EXPLANATION, TEXT_FAIL_RETRIEVAL, TEXT_FAIL_SHARED]
    out = []
    for i, combo in enumerate(itertools.product(trials, repeat=3)):
        out.append(entry(case(f"ch-mon-{100 + i}", f"q{i}"), list(combo)))
    # One errored row, which must stay out of every count.
    out.append({**entry(case("ch-mon-999", "err"), [TEXT_PASS] * 3), "error": "ReadTimeout"})
    return out


def test_majority_standard_equals_failure_modes():
    stats = bp.group_stats(mixed_entries())
    assert stats["failure_modes_by_standard"]["majority"] == stats["failure_modes"]


def test_each_standard_counts_every_wrong_scored_question_once():
    entries = mixed_entries()
    stats = bp.group_stats(entries)
    scored = [e for e in entries if row_verdict(e) in ("pass", "fail")]
    accurate = {
        "every_time": sum(all(bp.trial_ok(t) for t in e["trials"]) for e in scored),
        "majority": stats["passed"],
        "any_time": sum(any(bp.trial_ok(t) for t in e["trials"]) for e in scored),
    }
    for standard, counts in stats["failure_modes_by_standard"].items():
        assert sum(counts.values()) == stats["scored"] - accurate[standard], standard
        assert all(counts.values()), "zero counts are left out"


def test_every_time_is_at_least_majority_at_every_stage():
    modes = bp.group_stats(mixed_entries())["failure_modes_by_standard"]
    for stage in bp.ATTRIBUTION:
        assert modes["every_time"].get(stage, 0) >= modes["majority"].get(stage, 0), stage


def test_page_groups_carry_failure_modes_by_standard(tmp_path):
    run, bench, cases, art = setup(tmp_path)
    page = bp.build_page(run, bench, cases, art)
    assert page["schema_version"] == 1
    assert page["summary"]["failure_modes_by_standard"] == {
        "every_time": {"retrieval": 2}, "majority": {"retrieval": 1}, "any_time": {}}
    assert all("failure_modes_by_standard" in g for g in page["types"] if g["measured"])
    assert all("failure_modes_by_standard" in g for g in page["use_cases"])


def rerun_setup(tmp_path):
    """The base run measured both members; member b was then revised (new
    uid) and rerun alone."""
    run, bench, cases, art = setup(tmp_path)
    a, b_old = (cases[e["uid"]] for e in run["results"])
    b_new = Case(id=b_old.id, status="ready", group="g", set="monitoring", query=b_old.query,
                 expected={"aoi_ids": "BRA.14|BRA.15", "dataset_id": "11"})
    raw = {**bench.raw, "members": [bench.raw["members"][0],
                                    {**bench.raw["members"][1], "uid": b_new.uid}]}
    new_bench = from_dict(raw)
    base = {**run, "run_id": "base", "started": "2026-10-23T09:00:00Z"}
    rerun = {**run, "run_id": "rerun", "started": "2026-10-24T09:00:00Z",
             "results": [entry(b_new, [PASS, PASS, PASS])]}
    rerun_art = tmp_path / "rerun-artifacts"
    rerun_art.mkdir()
    return base, art, rerun, rerun_art, new_bench, {a.uid: a, b_new.uid: b_new}


def test_combined_page_takes_unmeasured_members_from_the_base(tmp_path):
    base, base_art, rerun, rerun_art, bench, cases = rerun_setup(tmp_path)
    page = bp.build_page(rerun, bench, cases, rerun_art, [(base, base_art)])
    qs = {q["id"]: q for q in page["questions"]}
    assert qs["ch-mon-001"]["run_id"] == "base"
    assert qs["ch-mon-001"]["attempts"][0]["aoi_ids"] == ["BRA.14_1"]  # base artifacts
    assert qs["ch-mon-002"]["run_id"] == "rerun"
    assert qs["ch-mon-002"]["trials_right"] == [True, True, True]
    assert page["run"]["run_id"] == "rerun"
    assert page["run"]["sources"] == [
        {"run_id": "base", "started": "2026-10-23T09:00:00Z", "questions": 1},
        {"run_id": "rerun", "started": "2026-10-24T09:00:00Z", "questions": 1},
    ]
    assert page["summary"]["scored"] == 2 and page["summary"]["passed"] == 2


def test_single_run_page_has_no_sources(tmp_path):
    run, bench, cases, art = setup(tmp_path)
    page = bp.build_page(run, bench, cases, art)
    assert "sources" not in page["run"]
    assert {q["run_id"] for q in page["questions"]} == {"r"}


def test_combined_page_refuses_an_uncovered_member(tmp_path):
    base, base_art, rerun, rerun_art, bench, cases = rerun_setup(tmp_path)
    rerun["results"] = []
    with pytest.raises(SystemExit, match="1 active member"):
        bp.build_page(rerun, bench, cases, rerun_art, [(base, base_art)])


@pytest.mark.parametrize(("field", "value", "message"), [
    ("ff", "experimental", "cannot be combined"),
    ("num_trials", 1, "cannot be combined"),
    ("environment", "staging", "cannot be combined"),
    ("started", "2026-10-25T00:00:00Z", "must be older"),
])
def test_base_must_match_the_rerun(field, value, message):
    rerun = {"run_id": "rerun", "started": "2026-10-24T09:00:00Z", "environment": "prod",
             "ff": None, "num_trials": 3, "benchmark": {}}
    base = {**rerun, "run_id": "base", "started": "2026-10-23T09:00:00Z", field: value}
    with pytest.raises(SystemExit, match=message):
        bp.check_base(base, rerun)


def test_combined_page_chains_bases_newest_wins(tmp_path):
    """A second rerun on top of the first: each member comes from the newest
    run that measured it, and sources list the runs oldest first."""
    base, base_art, rerun, rerun_art, bench, cases = rerun_setup(tmp_path)
    b_uid = rerun["results"][0]["uid"]
    b_case = cases[b_uid]
    second = {**rerun, "run_id": "second", "started": "2026-10-25T09:00:00Z",
              "results": [entry(b_case, [FAIL_RETRIEVAL, FAIL_RETRIEVAL, PASS])]}
    second_art = tmp_path / "second-artifacts"
    second_art.mkdir()
    # Bases given newest first still apply oldest first.
    page = bp.build_page(second, bench, cases, second_art,
                         [(rerun, rerun_art), (base, base_art)])
    qs = {q["id"]: q for q in page["questions"]}
    assert qs["ch-mon-001"]["run_id"] == "base"
    assert qs["ch-mon-002"]["run_id"] == "second"
    assert qs["ch-mon-002"]["verdict"] == "fail"
    assert [s["run_id"] for s in page["run"]["sources"]] == ["base", "rerun", "second"]
    assert [s["questions"] for s in page["run"]["sources"]] == [1, 0, 1]
