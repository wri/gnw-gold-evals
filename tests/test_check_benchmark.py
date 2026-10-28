"""tools/check_benchmark.py: manifest vs source-store integrity."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_sample as bs  # noqa: E402
import check_benchmark as cb  # noqa: E402
from test_benchmark_sample import make_store  # noqa: E402

from goldset.store import Case, write_case  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def write(tmp_path, data, status="draft"):
    data = {**data, "status": status, "frozen": "2026-11-01" if status == "frozen" else None}
    path = tmp_path / "benchmarks" / "t.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def build_in(tmp_path, monkeypatch):
    # build() records cases_dir relative to cwd and the check resolves it
    # against --repo-root, so build from inside tmp_path.
    make_store(tmp_path / "cases")
    monkeypatch.chdir(tmp_path)
    return bs.build(Path("cases"), "t", 4, 1, "2026-09-29")


def test_clean_manifest_passes(tmp_path, monkeypatch):
    data = build_in(tmp_path, monkeypatch)
    for status in ("draft", "frozen"):
        assert cb.check(write(tmp_path, data, status), tmp_path) == ([], [])


def edit_first_member(tmp_path, data):
    first = data["members"][0]
    path = next((tmp_path / "cases").rglob(f"{first['id']}.yaml"))
    path.unlink()
    write_case(tmp_path / "cases", Case(
        id=first["id"], status="ready", group=first["cohort"], set=first["set"],
        query="edited wording", expected={"dataset_id": "1"},
        notes={"difficulty": first["difficulty"]} if first["difficulty"] else {}))
    return first


def test_edited_member_errors_when_frozen_warns_when_draft(tmp_path, monkeypatch):
    data = build_in(tmp_path, monkeypatch)
    first = edit_first_member(tmp_path, data)
    errors, warnings = cb.check(write(tmp_path, data, "frozen"), tmp_path)
    assert warnings == [] and any(first["id"] in e and "uid not in" in e for e in errors)
    errors, warnings = cb.check(write(tmp_path, data, "draft"), tmp_path)
    assert errors == [] and any("uid not in" in w for w in warnings)


def test_erratum_silences_a_voided_member(tmp_path, monkeypatch):
    data = build_in(tmp_path, monkeypatch)
    first = edit_first_member(tmp_path, data)
    data["errata"] = [{"uid": first["uid"], "date": "2026-12-01", "reason": "reworded"}]
    assert cb.check(write(tmp_path, data, "frozen"), tmp_path) == ([], [])


def test_facet_drift_is_reported(tmp_path, monkeypatch):
    data = build_in(tmp_path, monkeypatch)
    data["members"][0] = {**data["members"][0], "cohort": "renamed"}
    errors, _ = cb.check(write(tmp_path, data, "frozen"), tmp_path)
    assert any("['cohort']" in e for e in errors)


def test_committed_manifests_are_clean():
    for path in sorted((REPO / "benchmarks").glob("*.json")):
        assert cb.check(path, REPO) == ([], []), path
