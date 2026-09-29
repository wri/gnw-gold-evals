"""challenge_rollup --benchmark: North Star, consistency, attribution, matrix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import challenge_rollup as cr  # noqa: E402

from goldset.benchmark import QUERY_TYPES, SCHEMA_VERSION, from_dict  # noqa: E402


def bench(members, errata=()):
    return from_dict({
        "schema_version": SCHEMA_VERSION, "version": "t", "status": "draft",
        "frozen": None, "source": {}, "sampling": {}, "types": list(QUERY_TYPES),
        "members": [{"uid": u, "id": u, "type": t, "set": "s", "cohort": "c",
                     "difficulty": "", "stages": stages} for u, t, stages in members],
        "errata": list(errata),
    })


def entry(uid, checks, trials=None, error=None):
    e = {"uid": uid, "id": uid, "checks": checks}
    if trials:
        e["trials"] = trials
    if error:
        e["error"] = error
    return e


def test_primary_failure_is_earliest_dedicated_stage():
    # scope outranks retrieval; shared-only failures are unattributed
    assert cr.primary_failure(entry("a", {"dataset_id_match": 0.0,
                                          "forbidden_tools_absent": 0.0})) == "scope"
    assert cr.primary_failure(entry("a", {"dataset_id_match": 0.0})) == "retrieval"
    assert cr.primary_failure(entry("a", {"agent_answer": 0.0})) == "unattributed"


def test_benchmark_rollup_rates_modes_and_matrix():
    b = bench([("p1", "geospatial", ["retrieval"]), ("p2", "geospatial", ["retrieval"]),
               ("f1", "geospatial", ["retrieval"]), ("e1", "dataset", ["scope", "retrieval"]),
               ("gone", "trend", ["retrieval"]), ("void", "trend", ["retrieval"])],
              errata=[{"uid": "void", "date": "2026-10-01", "reason": "x"}])
    flaky = [{"checks": {"aoi_id_match": 1.0}}, {"checks": {"aoi_id_match": 0.0}},
             {"checks": {"aoi_id_match": 1.0}}]
    run = {"run_id": "r", "results": [
        entry("p1", {"aoi_id_match": 1.0}),
        entry("p2", {"aoi_id_match": 1.0}, trials=flaky),
        entry("f1", {"aoi_id_match": 0.0}),
        entry("e1", {}, error="ReadTimeout"),
        entry("void", {"aoi_id_match": 0.0}),
    ]}
    r = cr.rollup_benchmark(run, b)
    ns = r["north_star"]
    assert (ns["passed"], ns["n"]) == (2, 3)          # error + voided + missing excluded
    assert ns["consistency"]["passed"] == 1            # p2 flaked on a trial
    assert ns["errors"] == 1 and r["missing"] == ["gone"] and r["voided"] == 1
    assert ns["failure_modes"]["pass"] == 2 and ns["failure_modes"]["retrieval"] == 1
    types = {t["key"]: t for t in r["types"]}
    assert types["refusal"]["measured"] is False
    assert types["geospatial"]["stages"]["retrieval"] == 3
    assert types["dataset"]["stages"]["scope"] == 1 and types["dataset"]["n"] == 0
    assert types["trend"]["members"] == 1              # voided member left out
    md = cr.render_benchmark_markdown([r])
    assert "not yet measured" in md and "North Star: **66.7%**" in md
