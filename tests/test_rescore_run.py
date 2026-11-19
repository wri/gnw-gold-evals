"""tools/rescore_run.py: recompute one check on an uncommitted run."""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import rescore_run  # noqa: E402

from goldset.buckets import summarize_buckets  # noqa: E402
from goldset.cli import merge_trials  # noqa: E402
from goldset.runner.artifacts import artifact_name  # noqa: E402

GOOD = [{"type": "bar", "xAxis": "x", "yAxis": "y", "data": [{"x": 1, "y": 2}]}]
BAD = [{"type": "bar", "xAxis": "x", "yAxis": "y", "data": []}]  # empty data


def _entry(uid, charts_ok, **extra):
    score = 1.0 if charts_ok else 0.0
    entry = {"uid": uid, "id": f"id-{uid}",
             "checks": {"chart_well_formed": score, "data_pull_exists": 1.0},
             "latency_s": 5.0, "trace_url": "http://t", **extra}
    if not charts_ok:
        entry["reasons"] = {"chart_well_formed": "old reason"}
    return entry


def _make_run(tmp_path, scored, saved):
    """scored/saved: per question, a list of (recorded ok, saved charts) per trial."""
    run_id = "20261119T000000Z_prod"
    art = tmp_path / "artifacts" / run_id
    art.mkdir(parents=True)
    results = []
    for uid, trials in scored.items():
        entries = [_entry(uid, ok) for ok in trials]
        for n, charts in enumerate(saved[uid], start=1):
            with gzip.open(art / artifact_name(uid, n), "wt") as handle:
                json.dump({"charts_data": charts}, handle)
        results.append(merge_trials(entries))
    record = {"run_id": run_id, "started": "2026-11-19T00:00:00Z", "environment": "prod",
              "build": None, "ff": None, "harness": {"repo": "x", "sha": "old"},
              "judge_model": "m", "num_trials": 3, "caseset_version": "v",
              "results": results, "buckets": summarize_buckets(results)}
    path = tmp_path / "runs" / f"{run_id}.json"
    path.parent.mkdir()
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path, record


@pytest.fixture
def argv(monkeypatch):
    def call(path, *extra):
        monkeypatch.setattr(sys, "argv", ["rescore_run", str(path), *extra])
        return rescore_run.main()
    return call


def test_changed_trials_flip_the_question_and_others_stay_equal(tmp_path, argv):
    # q1: recorded pass x3, but two saved states are really broken -> flips to fail.
    # q2: untouched.
    path, before = _make_run(
        tmp_path,
        {"a1": [True, True, True], "b2": [True, True, True]},
        {"a1": [BAD, BAD, GOOD], "b2": [GOOD, GOOD, GOOD]},
    )
    assert argv(path, "--check", "chart_well_formed", "--note", "wide ok.") == 0
    after = json.loads(path.read_text())
    a_before, a_after = before["results"][0], after["results"][0]
    assert a_after["checks"]["chart_well_formed"] == 0.0
    assert [t["checks"]["chart_well_formed"] for t in a_after["trials"]] == [0.0, 0.0, 1.0]
    assert a_after["trials"][0]["latency_s"] == a_before["trials"][0]["latency_s"]
    assert a_after["trace_url"] == a_before["trace_url"]
    assert a_after["checks"]["data_pull_exists"] == 1.0
    assert after["results"][1] == before["results"][1]
    assert after["buckets"]["verdicts"]["pass"] == before["buckets"]["verdicts"]["pass"] - 1
    assert after["harness"] == before["harness"]
    entry = after["rescored"][0]
    assert entry["check"] == "chart_well_formed"
    assert (entry["trials_changed"], entry["check_verdicts_changed"],
            entry["overall_verdicts_changed"]) == (2, 1, 1)
    assert after["methodology_note"].endswith("from the saved agent states: wide ok.")
    assert entry["note"] == "wide ok."


def test_existing_methodology_note_is_kept(tmp_path, argv):
    path, record = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [GOOD] * 3})
    record["methodology_note"] = "earlier note"
    path.write_text(json.dumps(record))
    assert argv(path, "--check", "chart_well_formed", "--note", "wide ok.") == 0
    assert json.loads(path.read_text())["methodology_note"].startswith("earlier note ")


def test_dry_run_writes_nothing(tmp_path, argv, capsys):
    path, _ = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [BAD] * 3})
    text = path.read_text()
    assert argv(path, "--check", "chart_well_formed", "--dry-run") == 0
    assert path.read_text() == text
    assert "id-a1: pass -> fail" in capsys.readouterr().out


def test_unknown_check_is_refused(tmp_path, argv, capsys):
    path, _ = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [GOOD] * 3})
    text = path.read_text()
    assert argv(path, "--check", "agent_answer") == 2
    assert path.read_text() == text
    assert "cannot be rescored" in capsys.readouterr().err


def test_missing_artifact_is_a_hard_error(tmp_path, argv, capsys):
    path, _ = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [GOOD] * 3})
    (tmp_path / "artifacts" / "20261119T000000Z_prod" / "a1_t2.json.gz").unlink()
    text = path.read_text()
    assert argv(path, "--check", "chart_well_formed", "--note", "wide ok.") == 1
    assert "a1_t2.json.gz" in capsys.readouterr().err
    assert path.read_text() == text


def test_unevaluated_trial_is_left_alone_without_an_artifact(tmp_path, argv):
    path, record = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [GOOD] * 3})
    record["results"][0]["trials"][1]["checks"]["chart_well_formed"] = None
    record["results"][0] = merge_trials(rescore_run.trial_entries(record["results"][0]))
    record["buckets"] = summarize_buckets(record["results"])
    path.write_text(json.dumps(record))
    (tmp_path / "artifacts" / "20261119T000000Z_prod" / "a1_t2.json.gz").unlink()
    assert argv(path, "--check", "chart_well_formed", "--note", "wide ok.") == 0


def test_tracked_run_file_is_refused(tmp_path, argv, capsys):
    path, _ = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [BAD] * 3})
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(tmp_path)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "runs"], check=True)
    # Staged only: still rewritable.
    assert argv(path, "--check", "chart_well_formed", "--note", "wide ok.") == 0
    subprocess.run([*git, "add", "runs"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "run"], check=True)
    text = path.read_text()
    assert argv(path, "--check", "chart_well_formed", "--note", "wide ok.") == 2
    assert path.read_text() == text
    assert "tracked at HEAD" in capsys.readouterr().err


def test_note_is_required_for_a_write(tmp_path, argv, capsys):
    path, _ = _make_run(tmp_path, {"a1": [True] * 3}, {"a1": [BAD] * 3})
    text = path.read_text()
    assert argv(path, "--check", "chart_well_formed") == 2
    assert path.read_text() == text
    assert "--note is required" in capsys.readouterr().err
