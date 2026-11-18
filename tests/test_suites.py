"""goldset.suites: suite -> case store and ledger, and every refusal."""

from __future__ import annotations

from pathlib import Path

import pytest

from goldset.suites import (
    SUITE_NAMES,
    SuiteError,
    cases_dir_for,
    ledger_suite,
    locate_resume_dir,
    resolve_results_dir,
    resolve_run_dirs,
    store_suite,
)

P = Path


def resolve(suite=None, manifest=None, cases=None, results=None):
    return resolve_run_dirs(
        suite=suite,
        manifest_cases_dir=P(manifest) if manifest else None,
        cases_dir=P(cases) if cases else None,
        results_dir=P(results) if results else None,
    )


def test_suite_names():
    assert SUITE_NAMES == ("challenge", "benchmark", "gold")


@pytest.mark.parametrize("path, suite", [
    ("cases/challenge", "challenge"),
    ("cases/v2", "gold"),
    ("cases/v1", None),
    ("somewhere/else", None),
])
def test_store_suite(path, suite):
    assert store_suite(P(path)) == suite


def test_store_and_ledger_recognised_by_absolute_path(tmp_path):
    assert store_suite(tmp_path / "cases" / "challenge") == "challenge"
    assert ledger_suite(tmp_path / "results" / "benchmark") == "benchmark"


@pytest.mark.parametrize("path, suite", [
    ("results/challenge", "challenge"),
    ("results/benchmark", "benchmark"),
    ("results/gold", "gold"),
    ("results/plain", None),
])
def test_ledger_suite(path, suite):
    assert ledger_suite(P(path)) == suite


# --- fresh runs: what each choice resolves to -------------------------------

def test_suite_challenge():
    dirs = resolve(suite="challenge")
    assert (dirs.suite, dirs.cases_dir, dirs.results_dir) == (
        "challenge", P("cases/challenge"), P("results/challenge"))
    assert dirs.status_exclude == "not doing,todo"


def test_suite_gold():
    dirs = resolve(suite="gold")
    assert (dirs.suite, dirs.cases_dir, dirs.results_dir) == (
        "gold", P("cases/v2"), P("results/gold"))
    assert dirs.status_exclude == "not doing"


@pytest.mark.parametrize("suite", [None, "benchmark"])
def test_benchmark_manifest_implies_the_benchmark_suite(suite):
    dirs = resolve(suite=suite, manifest="cases/challenge")
    assert (dirs.suite, dirs.cases_dir, dirs.results_dir) == (
        "benchmark", P("cases/challenge"), P("results/benchmark"))
    assert dirs.status_exclude == "not doing"


def test_benchmark_accepts_its_own_source_as_cases_dir():
    dirs = resolve(manifest="cases/challenge", cases="cases/challenge")
    assert dirs.cases_dir == P("cases/challenge")


def test_benchmark_from_an_unknown_store_still_files_in_results_benchmark(tmp_path):
    dirs = resolve(manifest=tmp_path / "cases")
    assert (dirs.cases_dir, dirs.results_dir) == (tmp_path / "cases", P("results/benchmark"))


@pytest.mark.parametrize("cases, results, suite, status", [
    ("cases/challenge", "results/challenge", "challenge", "not doing,todo"),
    ("cases/v2", "results/gold", "gold", "not doing"),
])
def test_known_store_infers_its_ledger(cases, results, suite, status):
    dirs = resolve(cases=cases)
    assert (dirs.suite, dirs.results_dir) == (suite, P(results))
    assert dirs.status_exclude == status


def test_unknown_store_with_explicit_ledger(tmp_path):
    dirs = resolve(cases="cases/v1", results=tmp_path / "out")
    assert (dirs.suite, dirs.results_dir) == (None, tmp_path / "out")
    assert dirs.status_exclude == "not doing"


def test_explicit_dirs_override_the_suite(tmp_path):
    dirs = resolve(suite="challenge", cases=tmp_path / "store",
                   results=tmp_path / "out")
    assert (dirs.cases_dir, dirs.results_dir) == (tmp_path / "store", tmp_path / "out")
    assert dirs.status_exclude == "not doing,todo"


# --- fresh runs: refusals ----------------------------------------------------

def test_nothing_chosen_lists_the_suites():
    with pytest.raises(SuiteError) as error:
        resolve()
    message = str(error.value)
    for flag in ("--suite challenge", "--benchmark MANIFEST", "--suite gold"):
        assert flag in message


def test_suite_benchmark_needs_a_manifest():
    with pytest.raises(SuiteError, match="--suite benchmark needs --benchmark MANIFEST"):
        resolve(suite="benchmark")


@pytest.mark.parametrize("suite", ["challenge", "gold"])
def test_benchmark_with_another_suite(suite):
    with pytest.raises(SuiteError, match=f"drop --suite {suite}"):
        resolve(suite=suite, manifest="cases/challenge")


def test_benchmark_with_a_different_cases_dir():
    with pytest.raises(SuiteError, match="not the manifest's source store"):
        resolve(manifest="cases/challenge", cases="cases/v2")


def test_unknown_store_needs_a_ledger():
    with pytest.raises(SuiteError, match="pass --results-dir"):
        resolve(cases="cases/v1")


def test_unknown_suite_name():
    with pytest.raises(SuiteError, match="unknown suite 'golden'"):
        resolve(suite="golden")


@pytest.mark.parametrize("kwargs, message", [
    ({"cases": "cases/challenge", "results": "results/gold"},
     "is the challenge store but results/gold is the gold ledger"),
    ({"cases": "cases/challenge", "results": "results/benchmark"},
     "only a --benchmark MANIFEST run is filed there"),
    ({"cases": "cases/v2", "results": "results/challenge"},
     "is the gold store but results/challenge is the challenge ledger"),
    ({"cases": "cases/v2", "results": "results/benchmark"},
     "only a --benchmark MANIFEST run is filed there"),
    ({"suite": "challenge", "results": "results/gold"},
     "is the challenge store but results/gold"),
    ({"suite": "gold", "cases": "cases/challenge"},
     "is the challenge store but results/gold"),
    ({"suite": "gold", "results": "results/benchmark"},
     "only a --benchmark MANIFEST run is filed there"),
    ({"manifest": "cases/challenge", "results": "results/challenge"},
     "a --benchmark run is filed in results/benchmark"),
    ({"manifest": "cases/challenge", "results": "results/gold"},
     "a --benchmark run is filed in results/benchmark"),
])
def test_store_and_ledger_of_different_suites_are_refused(kwargs, message):
    with pytest.raises(SuiteError, match=message):
        resolve(**kwargs)


# --- prune-artifacts and resume ----------------------------------------------

def test_prune_ledger():
    assert resolve_results_dir("benchmark", None) == P("results/benchmark")
    assert resolve_results_dir("gold", P("elsewhere")) == P("elsewhere")
    with pytest.raises(SuiteError, match="choose a ledger"):
        resolve_results_dir(None, None)


RUN_ID = "20261117T100000Z_prod"


def leave(tmp_path: Path, ledger: str, suffix: str = ".partial.jsonl") -> None:
    runs = tmp_path / "results" / ledger / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{RUN_ID}{suffix}").write_text("{}\n")


def test_resume_explicit_location_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    leave(tmp_path, "challenge")
    assert locate_resume_dir(RUN_ID, suite="gold", results_dir=None) == P("results/gold")
    assert locate_resume_dir(RUN_ID, suite=None, results_dir=P("x")) == P("x")
    # --suite benchmark only locates the ledger here: the partial's header
    # carries the manifest.
    assert locate_resume_dir(RUN_ID, suite="benchmark", results_dir=None) == P(
        "results/benchmark")


@pytest.mark.parametrize("ledger", ["challenge", "benchmark", "gold"])
def test_resume_finds_the_one_ledger_with_the_partial(tmp_path, monkeypatch, ledger):
    monkeypatch.chdir(tmp_path)
    leave(tmp_path, ledger)
    assert locate_resume_dir(RUN_ID, suite=None, results_dir=None) == P(f"results/{ledger}")


def test_resume_finds_a_finalised_run_too(tmp_path, monkeypatch):
    # resume_run then says the run is already finalised, instead of "not found"
    monkeypatch.chdir(tmp_path)
    leave(tmp_path, "challenge", ".json")
    assert locate_resume_dir(RUN_ID, suite=None, results_dir=None) == P("results/challenge")


def test_resume_without_a_match_names_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SuiteError) as error:
        locate_resume_dir(RUN_ID, suite=None, results_dir=None)
    message = str(error.value)
    for runs in ("results/challenge/runs", "results/benchmark/runs", "results/gold/runs"):
        assert runs in message


def test_resume_with_two_matches_never_picks_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    leave(tmp_path, "challenge")
    leave(tmp_path, "gold")
    with pytest.raises(SuiteError, match="more than one ledger") as error:
        locate_resume_dir(RUN_ID, suite=None, results_dir=None)
    assert "results/challenge" in str(error.value) and "results/gold" in str(error.value)
    assert "--suite or --results-dir" in str(error.value)


# --- tools that read one run --------------------------------------------------

def test_cases_dir_for_a_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cases" / "challenge").mkdir(parents=True)
    run = {"run_id": RUN_ID, "caseset": "challenge"}
    assert cases_dir_for(run) == P("cases/challenge")
    assert cases_dir_for(run, suite="gold") == P("cases/v2")
    assert cases_dir_for(run, suite="gold", cases_dir=P("mine")) == P("mine")


def test_cases_dir_for_a_run_without_caseset():
    with pytest.raises(SuiteError, match="pass --cases-dir or --suite"):
        cases_dir_for({"run_id": RUN_ID})


def test_cases_dir_for_a_run_whose_store_is_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SuiteError, match="cases/v9 does not exist"):
        cases_dir_for({"run_id": RUN_ID, "caseset": "v9"})
