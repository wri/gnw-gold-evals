"""Push-phase-1 exporter (PR-13): sheet CSVs + git-derived changelog."""

import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from export_sheet_csv import last_changed, main, uid_history

from goldset.store import Case, write_case


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         *args],
        check=True, capture_output=True,
    )


def _fixture_repo(tmp_path: Path) -> Path:
    """A real git repo with one case that changes uid across two commits."""
    repo = tmp_path / "repo"
    cases = repo / "cases" / "v2"
    cases.mkdir(parents=True)
    _git_init = subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert _git_init.returncode == 0

    case = Case(id="1-001", status="done", group="direct",
                query="Loss in Brazil in 2022?",
                expected={"dataset_id": "4", "answer": "2.9 Mha"})
    write_case(cases, case)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat: add 1-001")

    edited = Case(id="1-001", status="done", group="direct",
                  query="Loss in Brazil in 2022?",
                  expected={"dataset_id": "4", "answer": "3.1 Mha"},
                  notes={"status_reason": "judge flaked once",
                         "aoi_type": "gadm-country",
                         "date_scrub": "fixed 2022 window",
                         "value_1": "3.1"})
    write_case(cases, edited)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fix: corrected expected figure")

    multiturn = Case(id="mt-001", status="ready", group="multiturn", turns=(
        {"query": "q1", "expected": {"dataset_id": "4"}},
        {"query": "q2", "expected": {"scope": "analyse"}},
    ))
    write_case(cases, multiturn)
    return repo


def test_uid_history_records_transitions(tmp_path):
    repo = _fixture_repo(tmp_path)
    path = repo / "cases" / "v2" / "direct" / "1-001.yaml"
    history = uid_history(repo, path)
    assert len(history) == 2
    assert history[0]["old_uid"] == ""                      # birth
    assert history[1]["old_uid"] == history[0]["new_uid"]   # chained
    assert history[1]["subject"] == "fix: corrected expected figure"
    assert last_changed(repo, path) != "uncommitted"


def test_export_writes_both_csvs(tmp_path, monkeypatch, capsys):
    repo = _fixture_repo(tmp_path)
    out = tmp_path / "push"
    monkeypatch.setattr(sys, "argv", [
        "export_sheet_csv.py",
        "--cases-dir", str(repo / "cases" / "v2"),
        "--out", str(out),
    ])
    assert main() == 0
    printed = capsys.readouterr().out
    assert "1 multi-turn cases skipped" in printed

    rows = list(csv.DictReader((out / "cases.csv").open()))
    assert [r["test_id"] for r in rows] == ["1-001"]  # multiturn skipped
    assert rows[0]["expected_answer"] == "3.1 Mha"
    assert len(rows[0]["uid"]) == 16
    assert rows[0]["last_changed"] != "uncommitted"

    changelog = list(csv.DictReader((out / "changelog.csv").open()))
    assert len(changelog) == 2
    assert changelog[1]["new_uid"] == rows[0]["uid"]  # history ends at current


def test_uid_history_survives_group_rename(tmp_path):
    """A case regrouped (file renamed) must keep its pre-rename transitions.

    Regression: uid_history used to `git show {sha}:{current-path}` for every
    historical commit; the show failed silently for pre-rename commits, so
    routine group reclassification erased the early changelog."""
    repo = tmp_path / "repo"
    cases = repo / "cases" / "v2"
    cases.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    born = Case(id="2-001", status="done", group="direct", query="Loss where?",
                expected={"dataset_id": "4", "answer": "1.0 Mha"})
    write_case(cases, born)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat: add 2-001")

    edited = Case(id="2-001", status="done", group="direct", query="Loss where?",
                  expected={"dataset_id": "4", "answer": "1.2 Mha"})
    write_case(cases, edited)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fix: pre-rename figure correction")

    # reclassify: same content, new group -> new directory (a rename to git)
    moved = Case(id="2-001", status="done", group="comparative",
                 query="Loss where?",
                 expected={"dataset_id": "4", "answer": "1.2 Mha"})
    write_case(cases, moved)
    (cases / "direct" / "2-001.yaml").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "chore: regroup 2-001")

    final = Case(id="2-001", status="done", group="comparative",
                 query="Loss where?",
                 expected={"dataset_id": "4", "answer": "1.5 Mha"})
    write_case(cases, final)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fix: post-rename figure correction")

    history = uid_history(repo, cases / "comparative" / "2-001.yaml")
    # full lineage: birth + pre-rename edit + post-rename edit; the rename
    # itself changes no uid (group is not hashed) so it adds no transition
    assert [t["new_uid"] for t in history] == [born.uid, edited.uid, final.uid]
    assert [t["old_uid"] for t in history] == ["", born.uid, edited.uid]
    assert history[1]["subject"] == "fix: pre-rename figure correction"


def test_export_emits_every_notes_column(tmp_path, monkeypatch):
    """aoi_type/date_scrub (and friends) must survive export — the importer
    replaces notes wholesale, so any key the CSV drops is wiped on the next
    push -> sheet-edit -> re-import round trip."""
    repo = _fixture_repo(tmp_path)
    out = tmp_path / "push"
    monkeypatch.setattr(sys, "argv", [
        "export_sheet_csv.py",
        "--cases-dir", str(repo / "cases" / "v2"),
        "--out", str(out),
    ])
    assert main() == 0
    rows = list(csv.DictReader((out / "cases.csv").open()))
    assert rows[0]["status_reason"] == "judge flaked once"
    assert rows[0]["aoi_type"] == "gadm-country"
    assert rows[0]["date_scrub"] == "fixed 2022 window"
    assert rows[0]["value_1"] == "3.1"


def test_export_round_trips_through_importer(tmp_path, monkeypatch):
    """export -> import_sheet.parse_cases must reproduce the notes exactly."""
    from import_sheet import parse_cases

    repo = _fixture_repo(tmp_path)
    out = tmp_path / "push"
    monkeypatch.setattr(sys, "argv", [
        "export_sheet_csv.py",
        "--cases-dir", str(repo / "cases" / "v2"),
        "--out", str(out),
    ])
    assert main() == 0
    cases, skipped, sheet_edited = parse_cases(
        (out / "cases.csv").read_text(encoding="utf-8")
    )
    assert skipped == 0
    assert sheet_edited == []  # exported uid matches the recomputed uid
    [reimported] = cases
    assert reimported.notes == {
        "status_reason": "judge flaked once",
        "aoi_type": "gadm-country",
        "date_scrub": "fixed 2022 window",
        "value_1": "3.1",
    }
    assert reimported.expected == {"dataset_id": "4", "answer": "3.1 Mha"}


def test_uncommitted_store_degrades_gracefully(tmp_path):
    cases = tmp_path / "plain" / "cases"
    cases.mkdir(parents=True)
    case = Case(id="x", status="done", group="g", query="q",
                expected={"dataset_id": "4", "scope": "analyse"})
    path = write_case(cases, case)
    assert uid_history(None, path) == []
    assert last_changed(None, path) == "uncommitted"
