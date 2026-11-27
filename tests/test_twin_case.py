"""tools/twin_case.py: one case of a language pair takes the other's expected."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import twin_case as tc  # noqa: E402
from check import twin_problems  # noqa: E402

from goldset.store import Case, load_store, write_case  # noqa: E402


def make_store(root: Path, **spanish_fields) -> Path:
    cases = [
        Case(id="en-1", status="ready", group="tcl", set="quantification",
             query="How much forest was lost?",
             expected={"dataset_id": "4", "figure": "sum(area_ha)"},
             notes={"difficulty": "easy"}),
        Case(id="es-1", status="todo", group="tcl", set="quantification",
             query="¿Cuánto bosque se perdió?", expected={"dataset_id": "9"},
             notes={"reviewer": "pending"},
             **{"language": "es", "twin": "en-1", **spanish_fields}),
        Case(id="en-2", status="ready", group="tcl", set="quantification",
             query="Another question", expected={"dataset_id": "1"}),
    ]
    for case in cases:
        write_case(root, case)
    return root


def by_id(root: Path) -> dict[str, tuple[Case, str]]:
    return {case.id: (case, stored) for _p, case, stored in load_store(root)}


def test_copies_expected_to_the_other_language_and_rewrites_the_uid(tmp_path):
    root = make_store(tmp_path)
    before = by_id(root)
    differing, old_uid, new_uid = tc.twin_case(root, "en-1", "es-1")
    assert differing == ["dataset_id", "figure"]
    after, stored_uid = by_id(root)["es-1"]
    assert after.expected == before["en-1"][0].expected
    assert old_uid == before["es-1"][1] and new_uid == stored_uid == after.uid
    assert new_uid != old_uid
    # Only expected moves: the rest of the target is its own.
    assert (after.query, after.status, after.notes, after.language, after.twin) == (
        "¿Cuánto bosque se perdió?", "todo", {"reviewer": "pending"}, "es", "en-1")
    assert by_id(root)["en-1"] == before["en-1"]
    assert twin_problems([case for case, _uid in by_id(root).values()]) == []


@pytest.mark.parametrize("language", ["pt", "fr"])
def test_any_case_language_pairs_the_same_way(tmp_path, language):
    root = make_store(tmp_path, language=language)
    differing, _old, _new = tc.twin_case(root, "en-1", "es-1")
    assert differing == ["dataset_id", "figure"]
    after, _stored = by_id(root)["es-1"]
    assert (after.language, after.expected) == (language, by_id(root)["en-1"][0].expected)


def test_copies_in_the_other_direction_too(tmp_path):
    root = make_store(tmp_path)
    tc.twin_case(root, "es-1", "en-1")
    english, stored_uid = by_id(root)["en-1"]
    assert english.expected == {"dataset_id": "9"} and stored_uid == english.uid


def test_check_reports_the_difference_and_writes_nothing(tmp_path):
    root = make_store(tmp_path)
    before = by_id(root)
    differing, old_uid, new_uid = tc.twin_case(root, "en-1", "es-1", check_only=True)
    assert differing == ["dataset_id", "figure"] and old_uid == new_uid
    assert by_id(root) == before
    tc.twin_case(root, "en-1", "es-1")
    assert tc.twin_case(root, "en-1", "es-1", check_only=True)[0] == []


@pytest.mark.parametrize("source, target, fields, needle", [
    ("en-1", "nope", {}, "missing"),
    ("en-1", "en-1", {}, "two different cases"),
    ("en-1", "en-2", {}, "exactly one case"),
    ("en-2", "es-1", {}, "names en-1 as its twin, not en-2"),
    ("en-1", "es-1", {"twin": ""}, "names no case as its twin"),
])
def test_anything_but_a_pair_fails_loudly(tmp_path, source, target, fields, needle):
    root = make_store(tmp_path, **fields)
    before = by_id(root)
    with pytest.raises(SystemExit, match=needle):
        tc.twin_case(root, source, target)
    assert by_id(root) == before


def test_a_target_outside_its_store_path_is_refused(tmp_path):
    root = make_store(tmp_path)
    path = next(root.rglob("es-1.yaml"))
    moved = root / "elsewhere" / path.name
    moved.parent.mkdir()
    path.rename(moved)
    with pytest.raises(SystemExit, match="not where the store writes"):
        tc.twin_case(root, "en-1", "es-1")
