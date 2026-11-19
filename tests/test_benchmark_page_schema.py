"""Every committed BENCHMARK page must conform to schema/benchmark_page.schema.json.

The frontend parses these files strictly at a pinned commit, so the schema is
the cross-repo contract; tools/benchmark_page.py must keep producing it.
"""

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import benchmark_page as bp  # noqa: E402
from test_benchmark_page import setup  # noqa: E402

SCHEMA = json.loads((ROOT / "schema" / "benchmark_page.schema.json").read_text())
PAGE_FILES = sorted((ROOT / "results" / "benchmark" / "pages").glob("*.json"))
VALIDATOR = Draft202012Validator(SCHEMA)


def errors(page):
    return list(VALIDATOR.iter_errors(page))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", PAGE_FILES, ids=lambda p: p.stem)
def test_committed_page_conforms(path):
    errs = errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errs, "\n".join(e.message[:300] for e in errs)


@pytest.mark.parametrize("path", PAGE_FILES, ids=lambda p: p.stem)
def test_committed_page_cross_references_resolve(path):
    """The frontend throws on a question type or composition type that is
    not in types[]; JSON Schema cannot express that."""
    page = json.loads(path.read_text(encoding="utf-8"))
    keys = {t["key"] for t in page["types"]}
    assert {q["type"] for q in page["questions"]} <= keys
    for uc in page["use_cases"]:
        assert {k for k, _ in uc["composition"]["types"]} <= keys


def test_store_has_pages():
    assert PAGE_FILES, "results/benchmark/pages/ is empty"


@pytest.fixture
def built(tmp_path):
    run, bench, cases, art = setup(tmp_path)
    # The tool writes JSON, so tuples (Counter.most_common) become arrays.
    return json.loads(json.dumps(bp.build_page(run, bench, cases, art), ensure_ascii=False))


def test_page_built_by_the_tool_validates(built):
    assert not errors(built)
    # The tool writes the current generation, which the root branch must hold
    # to the attempt keys; guards against the branch silently selecting legacy.
    assert "attempts" in built["summary"]
    assert all("attempt_errors" in q and "run_id" in q for q in built["questions"])


def test_combined_page_with_sources_validates(built):
    built["run"]["sources"] = [{"run_id": "a", "started": "2026-10-22T09:00:00Z", "questions": 1},
                               {"run_id": "r", "started": "2026-10-23T09:00:00Z", "questions": 1}]
    assert not errors(built)


@pytest.mark.parametrize("drop", [
    lambda p: p.pop("stages"),
    lambda p: p["run"].pop("harness_sha"),
    lambda p: p["summary"].pop("every_time"),
    lambda p: p["questions"][0].pop("attempt_errors"),
    lambda p: p["questions"][0].pop("run_id"),
    lambda p: p["summary"].pop("no_answer"),
    lambda p: p["questions"][0]["attempts"][0].pop("charts"),
], ids=["stages", "harness_sha", "every_time", "attempt_errors", "q_run_id", "no_answer", "attempt_charts"])
def test_missing_required_key_is_rejected(built, drop):
    drop(built)
    assert errors(built)


@pytest.mark.parametrize("mutate", [
    lambda p: p["questions"][0].__setitem__("verdict", "inconsistent"),
    lambda p: p["questions"][0].__setitem__("primary_failure", "setup"),
    lambda p: p["questions"][0]["failed_checks"][0].__setitem__("stage", "nowhere"),
    lambda p: p["use_cases"][0].__setitem__("key", "UC9"),
    lambda p: p["stages"][0].__setitem__("key", "setup"),
    lambda p: p["summary"]["failure_modes"].__setitem__("setup", 1),
    lambda p: p["run"].__setitem__("num_trials", 1),
    lambda p: p.__setitem__("schema_version", 2),
    lambda p: p["questions"][0]["expected"].__setitem__("aoi_ids", 5),
    lambda p: p["questions"][0].__setitem__("unexpected_key", 1),
], ids=["verdict", "primary_failure", "check_stage", "use_case", "stage_key", "failure_mode",
        "num_trials", "schema_version", "expected_non_string", "extra_question_key"])
def test_wrong_value_is_rejected(built, mutate):
    page = copy.deepcopy(built)
    # ch-mon-002 fails, so its failed_checks list is not empty.
    page["questions"].sort(key=lambda q: q["id"], reverse=True)
    mutate(page)
    assert errors(page)


def test_legacy_page_without_attempt_keys_is_accepted_but_mixed_page_is_not(built):
    legacy = copy.deepcopy(built)
    for group in (legacy["summary"], *legacy["types"], *legacy["use_cases"]):
        group.pop("attempts", None)
        group.pop("no_answer", None)
    for q in legacy["questions"]:
        q.pop("attempt_errors")
        q.pop("run_id")
    assert not errors(legacy)
    legacy["summary"]["attempts"] = 1  # current marker but the rest is legacy
    assert errors(legacy)


def test_a_languages_companion_page_conforms(tmp_path):
    # The languages block and a base run's twins_drawn must stay inside the
    # contract: the frontend rejects a page the schema does not allow.
    from test_benchmark_page import languages_setup

    run, bench, cases, art, bases = languages_setup(tmp_path)
    page = bp.build_page(run, bench, cases, art, bases)
    assert page["languages"]
    errs = errors(json.loads(json.dumps(page)))
    assert not errs, "\n".join(e.message[:300] for e in errs)
