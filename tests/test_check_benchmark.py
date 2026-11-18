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


# ------------------------------------------------------------ language pairs


def pair_store(tmp_path):
    english = Case(id="ch-quant-001", status="ready", group="tcl",
                   set="quantification", query="How much forest was lost?",
                   expected={"dataset_id": "4"})
    spanish = Case(id="ch-quant-002", status="ready", group="tcl",
                   set="quantification", query="¿Cuánto bosque se perdió?",
                   expected={"dataset_id": "4"}, language="es",
                   twin="ch-quant-001")
    for case in (english, spanish):
        write_case(tmp_path / "cases", case)
    return english, spanish


def pair_member(case, **facets):
    return {"uid": case.uid, "id": case.id, "type": "quantification",
            "set": case.set, "cohort": case.group, "difficulty": "",
            "stages": bs.stages_for(case), **facets}


def pair_manifest(tmp_path, version, members, **keys):
    data = {"schema_version": 1, "version": version, "status": "draft",
            "frozen": None, "source": {"cases_dir": "cases"}, "sampling": {},
            "types": [{"key": "quantification"}], "members": members,
            "errata": [], **keys}
    path = tmp_path / "benchmarks" / f"{version}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_a_pair_inside_one_manifest_passes(tmp_path):
    english, spanish = pair_store(tmp_path)
    members = [pair_member(english, twin_uid=spanish.uid),
               pair_member(spanish, language="es", twin_uid=english.uid)]
    path = pair_manifest(tmp_path, "t-languages", members)
    assert cb.check(path, tmp_path) == ([], [])


def test_a_twin_in_the_paired_version_passes(tmp_path):
    english, spanish = pair_store(tmp_path)
    pair_manifest(tmp_path, "t", [pair_member(english)])
    native = pair_member(spanish, language="es", twin_uid=english.uid)
    path = pair_manifest(tmp_path, "t-languages", [native], pairs_with="t")
    assert cb.check(path, tmp_path) == ([], [])


def test_a_twin_that_is_no_member_is_reported(tmp_path):
    english, spanish = pair_store(tmp_path)
    pair_manifest(tmp_path, "t", [])
    native = pair_member(spanish, language="es", twin_uid=english.uid)
    for keys, where in (({}, "of this version"),
                        ({"pairs_with": "t"}, "this version or of t")):
        path = pair_manifest(tmp_path, "t-languages", [native], **keys)
        _, warnings = cb.check(path, tmp_path)
        assert len(warnings) == 1 and where in warnings[0], warnings


def test_a_missing_paired_version_is_one_clear_problem(tmp_path):
    english, spanish = pair_store(tmp_path)
    native = pair_member(spanish, language="es", twin_uid=english.uid)
    path = pair_manifest(tmp_path, "t-languages", [native], pairs_with="t")
    errors, warnings = cb.check(path, tmp_path)
    assert errors == [] and len(warnings) == 1
    assert "pairs_with 't'" in warnings[0] and "does not exist" in warnings[0]
    data = {**json.loads(path.read_text()), "status": "frozen",
            "frozen": "2026-11-18"}
    path.write_text(json.dumps(data))
    errors, warnings = cb.check(path, tmp_path)
    assert warnings == [] and len(errors) == 1


def test_pair_facets_are_checked_against_the_cases(tmp_path):
    english, spanish = pair_store(tmp_path)

    def problems(*members):
        return cb.check(pair_manifest(tmp_path, "t-languages", list(members)),
                        tmp_path)[1]

    wrong_language = problems(
        pair_member(english),
        pair_member(spanish, language="id", twin_uid=english.uid))
    assert len(wrong_language) == 1
    assert "differs from the case's 'es'" in wrong_language[0]
    wrong_twin = problems(
        pair_member(english),
        pair_member(spanish, language="es", twin_uid="0" * 16))
    assert any("not the uid of the case's twin" in p for p in wrong_twin)
    not_named = problems(pair_member(english, twin_uid="0" * 16))
    assert any("names ch-quant-001 as its twin" in p for p in not_named)
