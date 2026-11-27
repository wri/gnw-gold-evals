"""Round-trip and validation semantics of the on-disk store."""

import pytest

from goldset.store import (
    Case,
    build_manifest,
    group_slug,
    load_store,
    read_case,
    write_case,
)

CASE = Case(
    id="1-002",
    status="todo",
    group="direct",
    query="How much of Sao Paulo was impacted by disturbance alerts?",
    expected={"aoi_ids": "BRA.25", "dataset_id": "11", "answer": "1,319,600 ha"},
    notes={"status_reason": "Chart shows all confidence levels"},
)


def test_write_read_round_trip(tmp_path):
    path = write_case(tmp_path, CASE)
    assert path == tmp_path / "direct" / "1-002.yaml"
    loaded, stored_uid = read_case(path)
    assert loaded == CASE
    assert stored_uid == CASE.uid


def test_write_is_idempotent(tmp_path):
    first = write_case(tmp_path, CASE).read_text()
    second = write_case(tmp_path, CASE).read_text()
    assert first == second


def test_stored_uid_reflects_content_edits(tmp_path):
    path = write_case(tmp_path, CASE)
    tampered = path.read_text().replace("1,319,600 ha", "9,999,999 ha")
    path.write_text(tampered)
    loaded, stored_uid = read_case(path)
    assert stored_uid == CASE.uid  # the file still claims the old uid
    assert loaded.uid != stored_uid  # the content no longer matches it


def test_refuses_to_write_invalid_case(tmp_path):
    with pytest.raises(ValueError, match="empty query"):
        write_case(tmp_path, Case(id="x", status="ready", group="g", query="  "))


def test_read_rejects_unknown_top_level_keys(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("id: x\nquery: q\nstatus: s\ngroup: g\nsurprise: 1\n")
    with pytest.raises(ValueError, match="unknown top-level keys"):
        read_case(path)


def test_set_field_round_trips_and_nests_path(tmp_path):
    case = Case(
        id="ch-x-001", status="ready", set="aoi", group="acronyms",
        query="Go to the USA", expected={"aoi_ids": "USA"},
    )
    path = write_case(tmp_path, case)
    assert path == tmp_path / "aoi" / "acronyms" / "ch-x-001.yaml"
    loaded, stored_uid = read_case(path)
    assert loaded == case
    assert stored_uid == case.uid
    # set is organisational, never hashed: same content without it -> same uid
    assert case.uid == Case(
        id="ch-x-001", status="ready", group="acronyms",
        query="Go to the USA", expected={"aoi_ids": "USA"},
    ).uid


def test_manifest_omits_set_when_absent(tmp_path):
    with_set = Case(id="a", status="ready", set="aoi", group="g", query="q")
    without = Case(id="b", status="ready", group="g", query="q")
    manifest = build_manifest([with_set, without], "test")
    assert manifest["cases"][0]["set"] == "aoi"
    assert "set" not in manifest["cases"][1]


def test_group_slug():
    assert group_slug("Parent-Child") == "parent-child"
    assert group_slug("class comparison") == "class-comparison"
    assert group_slug("") == "ungrouped"
    assert group_slug("  Déjà vu! ") == "d-j-vu"


def test_load_store_sorted_and_manifest_deterministic(tmp_path):
    other = Case(id="1-001", status="done", group="temporal", query="q1")
    write_case(tmp_path, CASE)
    write_case(tmp_path, other)
    entries = load_store(tmp_path)
    assert [case.id for _p, case, _u in entries] == ["1-002", "1-001"] or [
        case.id for _p, case, _u in entries
    ] == ["1-001", "1-002"]  # path-sorted; both groups present
    manifest = build_manifest([case for _p, case, _u in entries], "test")
    assert manifest["case_count"] == 2
    assert [c["id"] for c in manifest["cases"]] == ["1-001", "1-002"]
    again = build_manifest([CASE, other], "test")
    assert manifest == again


# ------------------------------------------------------- language and twin


def test_english_is_the_default_and_leaves_the_uid_and_file_unchanged():
    from goldset.canonical import case_uid
    from goldset.store import case_to_dict

    case = Case(id="a", status="ready", group="g", query="q", expected={"x": "1"})
    assert case.language == "en"
    assert case.uid == case_uid("q", {"x": "1"}) == "caaa67cd293dfec6"
    assert "language" not in case_to_dict(case)
    assert "twin" not in case_to_dict(case)


def test_another_language_is_part_of_the_uid_and_round_trips(tmp_path):
    from goldset.store import read_case, write_case

    english = Case(id="a", status="ready", group="g", query="q", expected={"x": "1"})
    spanish = Case(id="a-es", status="ready", group="g", query="q",
                   expected={"x": "1"}, language="es", twin="a")
    assert spanish.uid != english.uid
    # The twin is a pointer, not content.
    assert spanish.uid == Case(id="b", status="ready", group="g", query="q",
                               expected={"x": "1"}, language="es").uid
    loaded, stored_uid = read_case(write_case(tmp_path, spanish))
    assert (loaded.language, loaded.twin, stored_uid) == ("es", "a", spanish.uid)


def test_language_and_twin_are_validated():
    def problems(**fields):
        base = {"id": "a", "status": "ready", "group": "g", "query": "q"}
        return Case(**{**base, **fields}).validate()

    assert problems(language="es", twin="b") == []
    assert problems(language="pt", twin="b") == []
    assert problems(language="fr", twin="b") == []
    assert "language" in problems(language="de")[0]
    assert "names a twin" in problems(twin="b")[0]
    assert "its own twin" in problems(language="id", twin="a")[0]
    turns = ({"query": "q1"}, {"query": "q2"})
    assert "must be in English" in problems(query="", turns=turns, language="es")[0]


def test_a_twin_must_be_an_english_case_with_the_same_expectations():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from check import twin_problems

    def case(id, expected, language="en", twin=""):
        return Case(id=id, status="ready", group="g", query=id, expected=expected,
                    language=language, twin=twin)

    english = case("a", {"aoi_id": "BRA", "figure": "sum(area_ha)"})
    same = case("a-es", {"figure": "sum(area_ha) ", "aoi_id": "BRA"}, "es", "a")
    assert twin_problems([english, same]) == []
    differs = case("a-id", {"aoi_id": "BRA", "figure": "mean(area_ha)"}, "id", "a")
    assert "['figure']" in twin_problems([english, differs])[0]
    assert "not in the store" in twin_problems([same])[0]
    untwinned = case("a-id", english.expected, "id")
    assert twin_problems([english, untwinned]) == ["a-id: names no twin"]
    chained = case("a-id", same.expected, "id", "a-es")
    assert "must be an English case" in twin_problems([english, same, chained])[0]


def test_the_case_language_reaches_figure_match(monkeypatch):
    from types import SimpleNamespace

    from goldset import registry
    from goldset.adapter import case_to_expected
    from goldset.evaluators import figures

    # Dot-grouped "1.209" is 1209 only when the case's language is read.
    monkeypatch.setattr(
        figures, "_fetch", lambda url: (("area_ha",), ((1209.0,),))
    )
    state = {
        "messages": [SimpleNamespace(content="Kehilangan tutupan pohon 1.209 hektar.")],
        "statistics": [{"source_url": "https://analytics/0", "data": {}}],
    }
    case = Case(id="a-id", status="ready", group="g", query="q",
                expected={"figure": "sum(area_ha)"}, language="id", twin="a")
    spec = next(s for s in registry.EVALUATORS if s.name == "figures")
    result = spec.run(state, case_to_expected(case), "q", None)
    assert result["figure_match_score"] == 1.0
