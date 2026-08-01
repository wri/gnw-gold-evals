"""PR-08 campaign tooling: parity comparison and flakiness tables."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import flakiness
from flakiness import collect
from parity import LEGACY_CHECKS, compare, exit_code, render


def run_fixture(results, run_id="20260801T000000Z_staging", trials=1):
    return {
        "run_id": run_id, "started": "2026-08-01T00:00:00Z",
        "environment": "staging", "build": "GNW test", "ff": None,
        "harness": {"repo": "x", "sha": "y"}, "judge_model": "claude-haiku-4-5",
        "num_trials": trials, "caseset_version": "cs", "results": results,
    }


def test_legacy_check_surface_is_the_port_surface():
    # exactly the PR-03 checks, no PR-04/06 additions, no info-only
    assert "answered_without_data" not in LEGACY_CHECKS
    assert "scope_match" not in LEGACY_CHECKS
    assert "date_coverage" not in LEGACY_CHECKS
    assert "aoi_id_match" in LEGACY_CHECKS and "agent_answer" in LEGACY_CHECKS


def test_parity_ignores_new_checks_and_flags_deterministic_breaks():
    run_a = run_fixture([
        {"uid": "u1", "id": "1-001",
         "checks": {"aoi_id_match": 1.0, "agent_answer": 1.0}},
    ])
    run_b = run_fixture([
        {"uid": "u1", "id": "1-001",
         "checks": {"aoi_id_match": 0.0, "agent_answer": 0.0,
                    "answered_without_data": 0.0},   # new check: ignored
         "reasons": {"agent_answer": "judge saw it differently"}},
    ], run_id="20260801T010000Z_staging")
    report = compare(run_a, run_b)
    assert report["comparable_checks"] == 2
    kinds = {d["check"]: d["judged"] for d in report["disagreements"]}
    assert kinds == {"aoi_id_match": False, "agent_answer": True}
    text = render(run_a, run_b, report)
    assert "PARITY BROKEN" in text and "DETERMINISTIC" in text


def test_parity_holds_when_only_judges_disagree():
    run_a = run_fixture([{"uid": "u1", "id": "1", "checks": {"agent_answer": 1.0}}])
    run_b = run_fixture([{"uid": "u1", "id": "1", "checks": {"agent_answer": 0.0}}],
                        run_id="20260801T010000Z_staging")
    report = compare(run_a, run_b)
    assert "PARITY HOLDS" in render(run_a, run_b, report)
    assert exit_code(report) == 0


def test_parity_nothing_comparable_is_an_explicit_gate_failure():
    # No shared uids at all: the gate must fail, and the verdict must say
    # "nothing compared", not "parity broken" (nothing disagreed) and
    # certainly not "parity holds".
    run_a = run_fixture([{"uid": "u1", "id": "1", "checks": {"agent_answer": 1.0}}])
    run_b = run_fixture([{"uid": "u2", "id": "2", "checks": {"agent_answer": 1.0}}],
                        run_id="20260801T010000Z_staging")
    report = compare(run_a, run_b)
    assert report["comparable_checks"] == 0 and report["disagreements"] == []
    text = render(run_a, run_b, report)
    assert "NOTHING COMPARABLE" in text and "0 shared legacy checks" in text
    assert "PARITY HOLDS" not in text and "PARITY BROKEN" not in text
    assert exit_code(report) == 1


def test_parity_handles_turn_prefixed_checks():
    # Mirrors test_flakiness_handles_turn_prefixed_checks: a multiturn row
    # stores its checks as t<N>.<name>; the legacy side stores bare names.
    # Without base-name normalization this reads as a spurious
    # DETERMINISTIC disagreement (A=1.0 B=None).
    run_a = run_fixture([
        {"uid": "u1", "id": "mt-001", "checks": {"aoi_id_match": 1.0}},
    ])
    run_b = run_fixture([
        {"uid": "u1", "id": "mt-001",
         "checks": {"t1.aoi_id_match": 1.0, "t2.state_delta": 1.0}},
    ], run_id="20260801T010000Z_staging")
    report = compare(run_a, run_b)
    assert report["comparable_checks"] == 1  # t2.state_delta is not legacy
    assert report["disagreements"] == []
    assert exit_code(report) == 0


def test_parity_turn_prefix_collision_collapses_any_fail():
    # Two turns carry the same base check: the collapse keeps the worst
    # turn's value (any-fail) and that turn's reason.
    run_a = run_fixture([{"uid": "u1", "id": "mt-002", "checks": {"aoi_id_match": 1.0}}])
    run_b = run_fixture([
        {"uid": "u1", "id": "mt-002",
         "checks": {"t1.aoi_id_match": 1.0, "t2.aoi_id_match": 0.0},
         "reasons": {"t1.aoi_id_match": "turn 1 ok", "t2.aoi_id_match": "turn 2 wrong AOI"}},
    ], run_id="20260801T010000Z_staging")
    report = compare(run_a, run_b)
    (item,) = report["disagreements"]
    assert item["check"] == "aoi_id_match" and item["judged"] is False
    assert item["a"] == 1.0 and item["b"] == 0.0
    assert item["reason_b"] == "turn 2 wrong AOI"
    assert exit_code(report) == 1


def test_flakiness_stats_and_flap_detection():
    run = run_fixture([
        {"uid": "u1", "id": "1-001",
         "checks": {"aoi_id_match": 1.0, "charts_answer": 1.0},
         "trials": [
             {"checks": {"aoi_id_match": 1.0, "charts_answer": 1.0}},
             {"checks": {"aoi_id_match": 1.0, "charts_answer": 0.0}},
             {"checks": {"aoi_id_match": 1.0, "charts_answer": 1.0}},
         ]},
        {"uid": None, "id": "stale", "stale_case": True,
         "checks": {"aoi_id_match": 0.0}},
    ], trials=3)
    stats, flappy = collect(run)
    assert stats["aoi_id_match"]["std"] == 0.0
    assert stats["aoi_id_match"]["within_gate"] is True
    assert stats["charts_answer"]["kind"] == "judged"
    assert stats["charts_answer"]["std"] > 0.4  # 2/3 pass flaps hard
    assert stats["charts_answer"]["flapping_cases"] == 1
    assert flappy == [{"id": "1-001", "checks": ["charts_answer"]}]
    # stale rows excluded entirely; n counts CASES, not pooled values
    assert stats["aoi_id_match"]["n"] == 1


def test_flakiness_is_within_case_not_pooled():
    """A check that consistently fails on one case and passes on nine is
    NOT flaky — the first live run misread exactly this as OVER GATE."""
    entries = [{"uid": f"u{i}", "id": f"c{i}",
                "checks": {"dataset_id_match": 1.0 if i else 0.0},
                "trials": [{"checks": {"dataset_id_match": 1.0 if i else 0.0}}] * 3}
               for i in range(10)]
    stats, flappy = collect(run_fixture(entries, trials=3))
    assert stats["dataset_id_match"]["mean"] == 0.9   # the pass rate
    assert stats["dataset_id_match"]["std"] == 0.0    # zero flakiness
    assert stats["dataset_id_match"]["within_gate"] is True
    assert flappy == []


def test_flakiness_flags_insufficient_verdicts():
    """1 real verdict out of 3 trials is 'mostly errored', not 'stable' —
    std over the partial sample must never count as within the gate."""
    run = run_fixture([
        {"uid": "u1", "id": "1-001",
         "checks": {"charts_answer": 1.0, "aoi_id_match": 1.0},
         "trials": [
             {"checks": {"charts_answer": 1.0, "aoi_id_match": 1.0}},
             {"checks": {"charts_answer": None, "aoi_id_match": 1.0}},
             {"checks": {"charts_answer": None, "aoi_id_match": 1.0}},
         ]},
    ], trials=3)
    stats, _flappy = collect(run)
    row = stats["charts_answer"]
    assert row["std"] == 0.0                      # looks calm...
    assert row["insufficient_data"] is True       # ...but is mostly missing
    assert row["observed_verdicts"] == 1 and row["expected_verdicts"] == 3
    assert row["within_gate"] is False
    # the fully-measured check on the same row is untouched
    assert stats["aoi_id_match"]["insufficient_data"] is False
    assert stats["aoi_id_match"]["within_gate"] is True
    text = flakiness.render(run, stats, [], per_case=False)
    assert "INSUFFICIENT DATA" in text and "1/3 verdicts" in text
    assert "missing verdicts" in text


def test_flakiness_insufficient_data_exits_nonzero(tmp_path, monkeypatch):
    run = run_fixture([
        {"uid": "u1", "id": "1-001", "checks": {"charts_answer": 1.0},
         "trials": [{"checks": {"charts_answer": 1.0}},
                    {"checks": {"charts_answer": None}},
                    {"checks": {"charts_answer": None}}]},
    ], trials=3)
    path = tmp_path / "20260801T000000Z_staging.json"
    path.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["flakiness.py", str(path)])
    assert flakiness.main() == 1


def test_flakiness_nothing_measured_exits_nonzero(tmp_path, monkeypatch, capsys):
    """An all-stale run must say so explicitly, not print an empty all-clear
    table and exit 0."""
    run = run_fixture([
        {"uid": None, "id": "stale-1", "stale_case": True,
         "checks": {"aoi_id_match": 0.0}},
        {"uid": None, "id": "stale-2", "stale_case": True,
         "checks": {"aoi_id_match": 1.0}},
    ], trials=3)
    path = tmp_path / "20260801T000000Z_staging.json"
    path.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["flakiness.py", str(path)])
    assert flakiness.main() == 1
    out = capsys.readouterr().out
    assert "nothing measured" in out
    assert "| check |" not in out  # no all-clear-looking empty table


def test_flakiness_handles_turn_prefixed_checks():
    run = run_fixture([
        {"uid": "u1", "id": "mt-001",
         "checks": {"t1.aoi_id_match": 1.0, "t2.state_delta": 1.0}},
    ])
    stats, _ = collect(run)
    assert "aoi_id_match" in stats and "state_delta" in stats
