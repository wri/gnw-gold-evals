"""Store runs select English cases unless --language says otherwise."""

import argparse
import sys

from test_resume import RUN_ID, make_header

from goldset import cli
from goldset.ledger import partial_path, write_partial_header
from goldset.store import Case, build_manifest, write_case, write_manifest

ENGLISH = Case(id="1-001", status="ready", group="direct", query="q one",
               expected={"dataset_id": "4"})
SPANISH = Case(id="1-002", status="ready", group="direct", query="q uno",
               expected={"dataset_id": "4"}, language="es", twin="1-001")
INDONESIAN = Case(id="1-003", status="ready", group="direct", query="q satu",
                  expected={"dataset_id": "4"}, language="id", twin="1-001")
CASES = (ENGLISH, SPANISH, INDONESIAN)


def make_store(tmp_path):
    cases_dir = tmp_path / "cases" / "v2"
    for case in CASES:
        write_case(cases_dir, case)
    manifest = build_manifest(list(CASES), source="test")
    write_manifest(cases_dir, manifest)
    return cases_dir, manifest


def selection(cases_dir, **overrides):
    args = argparse.Namespace(
        cases_dir=cases_dir, status_exclude="not doing", id=None, group=None,
        set=None, benchmark=None, **overrides)
    return [c.id for c in cli.select_cases(args)]


def test_a_store_run_selects_english_cases_by_default(tmp_path):
    cases_dir, _ = make_store(tmp_path)
    assert selection(cases_dir) == ["1-001"]
    assert selection(cases_dir, language="en") == ["1-001"]


def test_language_picks_one_language_or_all(tmp_path):
    cases_dir, _ = make_store(tmp_path)
    assert selection(cases_dir, language="es") == ["1-002"]
    assert selection(cases_dir, language="id") == ["1-003"]
    assert selection(cases_dir, language="all") == ["1-001", "1-002", "1-003"]


def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["gold", "run", *argv])
    return cli.main()


def test_dry_run_lists_only_english_cases(tmp_path, monkeypatch, capsys):
    cases_dir, _ = make_store(tmp_path)
    assert run_main(monkeypatch, "--cases-dir", str(cases_dir), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "1-001" in out and "1-002" not in out and "1 cases selected" in out
    run_main(monkeypatch, "--cases-dir", str(cases_dir), "--dry-run",
             "--language", "all")
    assert "3 cases selected" in capsys.readouterr().out


def test_benchmark_runs_refuse_a_language(tmp_path, monkeypatch, capsys):
    assert run_main(monkeypatch, "--benchmark", str(tmp_path / "b.json"),
                    "--language", "es") == 1
    assert "drop --group/--set/--language" in capsys.readouterr().out


def test_the_run_header_records_the_language(tmp_path, monkeypatch):
    cases_dir, _ = make_store(tmp_path)
    headers = []

    def capture(results_dir, header):
        headers.append(header)
        return write_partial_header(results_dir, header)

    async def fake_run_cases(args, cases, entry_sink=None):
        return []

    monkeypatch.setattr(cli, "write_partial_header", capture)
    monkeypatch.setattr(cli, "run_cases", fake_run_cases)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "require_api_token", lambda environment: "tok")
    monkeypatch.setattr(cli, "prefetch_ground_truth", lambda args, cases: True)
    monkeypatch.setattr(cli, "_finalise", lambda *a, **k: 0)
    results = tmp_path / "results"
    for extra, want in (([], "en"), (["--language", "es"], "es")):
        assert run_main(monkeypatch, "--cases-dir", str(cases_dir),
                        "--results-dir", str(results), *extra) == 0
        assert headers[-1]["language"] == want
        partial_path(results, headers[-1]["run_id"]).unlink()


def resume_ids(tmp_path, monkeypatch, **header):
    cases_dir, manifest = make_store(tmp_path)
    write_partial_header(tmp_path / "results", make_header(
        run_id=RUN_ID, trials=1, cases_dir=str(cases_dir),
        caseset_version=manifest["caseset_version"], **header))
    seen = []

    async def fake_run_cases(args, cases, entry_sink=None):
        seen.extend(c.id for c in cases)
        return []

    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setattr(cli, "run_cases", fake_run_cases)
    monkeypatch.setattr(cli, "_finalise", lambda *a, **k: 0)
    cli.resume_run(argparse.Namespace(resume=RUN_ID,
                                      results_dir=tmp_path / "results"))
    return seen


def test_resume_keeps_the_headers_language(tmp_path, monkeypatch):
    assert resume_ids(tmp_path, monkeypatch, language="en") == ["1-001"]


def test_resume_of_an_older_partial_runs_every_case(tmp_path, monkeypatch):
    # make_header has no language, as before the option existed.
    assert "language" not in make_header()
    assert resume_ids(tmp_path, monkeypatch) == ["1-001", "1-002", "1-003"]
