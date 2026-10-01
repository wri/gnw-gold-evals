"""Run-relative date tokens in expected values + date_extraction tolerance."""

from datetime import datetime

from goldset.evaluators.data_pull_evaluator import evaluate_date_extraction
from goldset.store import Case
from goldset.templates import has_templates, resolve_templates, validate_templates

NOW = datetime(2026, 10, 1, 9, 0)


def test_run_tokens_resolve_to_iso_dates():
    assert resolve_templates("{run}", NOW) == "2026-10-01"
    assert resolve_templates("{run-30d}", NOW) == "2026-09-01"
    assert resolve_templates("{run-7d}..{run}", NOW) == "2026-09-24..2026-10-01"
    assert resolve_templates("alerts in {last_month}", NOW) == "alerts in September 2026"
    assert resolve_templates("{month_start}", NOW) == "2026-10-01"
    assert resolve_templates("{last_month_start}..{last_month_end}", NOW) == "2026-09-01..2026-09-30"
    assert resolve_templates("{current_year}-01-01", NOW) == "2026-01-01"
    jan = datetime(2027, 1, 15)
    assert resolve_templates("{last_month_start}..{last_month_end}", jan) == "2026-12-01..2026-12-31"


def test_run_tokens_validate_and_count_as_templates():
    assert validate_templates("{run-90d}") == []
    assert validate_templates("{run}") == []
    assert validate_templates("{runs-3d}") != []
    assert has_templates("{run-30d}") and not has_templates("2026-09-01")


def test_uid_hashes_the_template_not_the_resolved_date():
    a = Case(id="x", status="ready", group="g", query="q", expected={"start_date": "{run-30d}"})
    b = Case(id="x", status="ready", group="g", query="q", expected={"start_date": "{run-30d}"})
    c = Case(id="x", status="ready", group="g", query="q", expected={"start_date": "2026-09-01"})
    assert a.uid == b.uid != c.uid


def state(start, end):
    return {"messages": [], "tool_calls": [{"name": "pull_data", "args": {"start_date": start, "end_date": end}}]}


def test_tolerance_accepts_near_windows_only_when_set(monkeypatch):
    import goldset.evaluators.data_pull_evaluator as dpe
    monkeypatch.setattr(dpe, "_tool_call_date_windows", lambda s: [("pull_data", s["tool_calls"][0]["args"]["start_date"], s["tool_calls"][0]["args"]["end_date"])])
    near = state("2026-08-31", "2026-09-30")
    exact = evaluate_date_extraction(near, "2026-09-01", "2026-10-01")
    loose = evaluate_date_extraction(near, "2026-09-01", "2026-10-01", tolerance_days=3)
    far = evaluate_date_extraction(state("2026-07-01", "2026-09-30"), "2026-09-01", "2026-10-01", tolerance_days=3)
    assert exact["date_extraction_score"] == 0.0
    assert loose["date_extraction_score"] == 1.0
    assert far["date_extraction_score"] == 0.0
