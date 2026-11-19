"""tools/benchmark_languages.py: the languages companion manifest."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_languages as bl  # noqa: E402
import check_benchmark as cb  # noqa: E402
from benchmark_sample import stages_for  # noqa: E402

from goldset.benchmark import QUERY_TYPES, from_dict, render  # noqa: E402
from goldset.store import (  # noqa: E402
    Case,
    build_manifest,
    write_case,
    write_manifest,
)


def case(id, query, expected, language="en", twin="", **fields):
    return Case(id=id, query=query, expected=expected, language=language,
                twin=twin, **{"status": "ready", "group": "tcl",
                              "set": "quantification", **fields})


LOSS = {"dataset_id": "4", "data_pull": "TRUE"}
REFUSE = {"text": "Declines."}


def cases(**overrides):
    """en-1 is a member of the English version and has a Spanish and an
    Indonesian case; en-2 was written for es-2 and is in no version."""
    made = {
        "en-1": case("en-1", "How much forest was lost?", LOSS,
                     notes={"difficulty": "easy"}),
        "es-1": case("es-1", "¿Cuánto bosque se perdió?", LOSS, "es", "en-1"),
        "id-1": case("id-1", "Berapa hutan yang hilang?", LOSS, "id", "en-1",
                     group="tcl-id"),
        "en-2": case("en-2", "Write my essay", REFUSE, set="aoi", group="direct",
                     notes={"benchmark_type": "scope"}),
        "es-2": case("es-2", "Escribe mi ensayo", REFUSE, "es", "en-2", set="aoi",
                     group="direct"),
        "en-3": case("en-3", "Unpaired question", {"dataset_id": "1"}),
    }
    made.update(overrides)
    return made


def english_version(members, **keys):
    return from_dict({
        "schema_version": 1, "version": "t", "status": "draft", "frozen": None,
        "source": {"cases_dir": "cases"}, "sampling": {},
        "types": list(QUERY_TYPES), "members": members, "errata": [], **keys,
    })


def english_member(made):
    one = made["en-1"]
    return {"uid": one.uid, "id": "en-1", "type": "trend", "set": one.set,
            "cohort": one.group, "difficulty": "easy", "stages": stages_for(one),
            "benchmark_id": "bm26-001", "use_cases": ["UC3", "UC4"],
            "synthetic": True}


def setup(tmp_path, made=None, members=None):
    made = made or cases()
    root = tmp_path / "cases"
    for one in made.values():
        write_case(root, one)
    write_manifest(root, build_manifest(list(made.values()), "t"))
    paired = english_version([english_member(made)] if members is None else members)
    return root, made, paired


def test_members_are_the_other_languages_and_their_new_english_twins(tmp_path):
    root, made, paired = setup(tmp_path)
    data = bl.build(root, "t-languages", paired, "2026-11-18")
    assert from_dict(data).validate() == []
    assert (data["pairs_with"], data["status"]) == ("t", "draft")
    by_id = {m["id"]: m for m in data["members"]}
    # en-1 stays in the English version only; en-3 has no pair.
    assert sorted(by_id) == ["en-2", "es-1", "es-2", "id-1"]
    assert by_id["es-1"] == {
        "uid": made["es-1"].uid, "id": "es-1", "type": "trend",
        "set": "quantification", "cohort": "tcl", "difficulty": "",
        "stages": stages_for(made["es-1"]), "use_cases": ["UC3", "UC4"],
        "synthetic": True, "language": "es", "twin_uid": made["en-1"].uid,
    }
    assert (by_id["id-1"]["language"], by_id["id-1"]["cohort"]) == ("id", "tcl-id")
    assert by_id["id-1"]["twin_uid"] == made["en-1"].uid
    # A twin outside the English version joins in English, typed from its
    # own notes, and its pair takes the same type.
    assert by_id["en-2"] == {
        "uid": made["en-2"].uid, "id": "en-2", "type": "refusal", "set": "aoi",
        "cohort": "direct", "difficulty": "", "stages": stages_for(made["en-2"]),
    }
    assert by_id["es-2"]["type"] == "refusal" and "use_cases" not in by_id["es-2"]
    assert by_id["es-2"]["twin_uid"] == made["en-2"].uid
    measured = {t["key"] for t in data["types"] if t["measured"]}
    assert measured == {"trend", "refusal"}
    assert bl.build(root, "t-languages", paired, "2026-11-18") == data


def test_portuguese_and_french_questions_join_the_companion(tmp_path):
    # Nothing in the tool is per language: any case language pairs the same way.
    made = cases(**{
        "pt-1": case("pt-1", "Quanta floresta foi perdida?", LOSS, "pt", "en-1"),
        "fr-1": case("fr-1", "Combien de forêt a été perdue ?", LOSS, "fr", "en-1"),
    })
    root, made, paired = setup(tmp_path, made)
    data = bl.build(root, "t-languages", paired, "2026-11-19")
    assert from_dict(data).validate() == []
    by_id = {m["id"]: m for m in data["members"]}
    for code in ("pt", "fr"):
        member = by_id[f"{code}-1"]
        assert (member["language"], member["twin_uid"], member["type"]) == (
            code, made["en-1"].uid, "trend")


def test_without_a_paired_version_every_twin_is_a_member(tmp_path):
    root, made, _paired = setup(tmp_path)
    data = bl.build(root, "t-languages", None, "2026-11-18")
    assert "pairs_with" not in data
    by_id = {m["id"]: m for m in data["members"]}
    assert sorted(by_id) == ["en-1", "en-2", "es-1", "es-2", "id-1"]
    # No sheet type is known, so the set gives the type.
    assert by_id["en-1"]["type"] == by_id["es-1"]["type"] == "quantification"
    assert by_id["en-1"]["difficulty"] == "easy"


def test_a_voided_twin_is_not_a_member_of_the_paired_version(tmp_path):
    root, made, _paired = setup(tmp_path)
    voided = english_version(
        [english_member(made)],
        errata=[{"uid": made["en-1"].uid, "date": "2026-12-01", "reason": "r"}])
    ids = [m["id"] for m in bl.build(root, "t-languages", voided, "d")["members"]]
    assert "en-1" in ids


def test_a_pair_that_is_not_ready_is_excluded(tmp_path):
    made = cases()
    made["es-1"] = case("es-1", "¿Cuánto bosque se perdió?", LOSS, "es", "en-1",
                        status="todo", notes={"status_reason": "needs review"})
    made["en-2"] = case("en-2", "Write my essay", REFUSE, set="aoi",
                        group="direct", status="todo")
    root, made, paired = setup(tmp_path, made)
    data = bl.build(root, "t-languages", paired, "2026-11-18")
    assert [m["id"] for m in data["members"]] == ["id-1"]
    assert data["sampling"]["excluded"] == [
        {"id": "es-1", "twin": "en-1", "status": "todo", "reason": "needs review"},
        {"id": "es-2", "twin": "en-2", "status": "todo", "reason": ""},
    ]


@pytest.mark.parametrize("override, needle", [
    ({"es-1": case("es-1", "¿Cuánto?", LOSS, "es", "gone")}, "twin 'gone' is not in"),
    ({"es-1": case("es-1", "¿Cuánto?", LOSS, "es", "id-1")}, "must be an English"),
    ({"es-1": case("es-1", "¿Cuánto?", {"dataset_id": "9"}, "es", "en-1")},
     "expected differs from its twin en-1"),
    ({"en-2": case("en-2", "Write my essay", REFUSE, set="novel")},
     "no query type measures the set 'novel'"),
    ({key: case(key, key, LOSS) for key in ("es-1", "id-1", "es-2")},
     "no case is in another language"),
])
def test_bad_pairs_stop_the_build(tmp_path, override, needle):
    root, _made, paired = setup(tmp_path, cases(**override))
    with pytest.raises(SystemExit, match=needle):
        bl.build(root, "t-languages", paired, "2026-11-18")


def test_a_case_without_a_twin_is_excluded_not_fatal(tmp_path):
    made = cases(**{"es-1": case("es-1", "¿Cuánto?", LOSS, "es")})
    root, made, paired = setup(tmp_path, made)
    data = bl.build(root, "t-languages", paired, "2026-11-18")
    assert {"id": "es-1", "twin": "", "status": "ready",
            "reason": "names no twin"} in data["sampling"]["excluded"]
    assert "es-1" not in [m["id"] for m in data["members"]]
    assert "es-2" in [m["id"] for m in data["members"]]


def run_main(tmp_path, *extra):
    return bl.main(["--version", "t-languages", "--cases-dir", "cases",
                    "--out-dir", "benchmarks", *extra])


def test_the_written_companion_passes_the_benchmark_check(tmp_path, monkeypatch):
    _root, made, paired = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    Path("benchmarks").mkdir()
    Path("benchmarks/t.json").write_text(render(paired.raw), encoding="utf-8")
    assert run_main(tmp_path, "--pairs-with", "t") == 0
    out = Path("benchmarks/t-languages.json")
    assert cb.check(out, tmp_path) == ([], [])
    assert cb.check(Path("benchmarks/t.json"), tmp_path) == ([], [])
    # A second build keeps the creation date and the errata.
    data = json.loads(out.read_text(encoding="utf-8"))
    erratum = {"uid": made["id-1"].uid, "date": "2026-12-01", "reason": "r"}
    out.write_text(render({**data, "created": "2026-01-01", "errata": [erratum]}),
                   encoding="utf-8")
    assert run_main(tmp_path, "--pairs-with", "t") == 0
    again = json.loads(out.read_text(encoding="utf-8"))
    assert (again["created"], again["errata"]) == ("2026-01-01", [erratum])
    assert again["members"] == data["members"]


def test_a_frozen_companion_is_never_rewritten(tmp_path, monkeypatch, capsys):
    setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_main(tmp_path) == 0
    out = Path("benchmarks/t-languages.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    frozen = render({**data, "status": "frozen", "frozen": "2026-11-18"})
    out.write_text(frozen, encoding="utf-8")
    assert run_main(tmp_path) == 1
    assert "never rewritten" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8") == frozen


def test_a_missing_paired_version_stops_the_build(tmp_path, monkeypatch):
    setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="--pairs-with t: .*does not exist"):
        run_main(tmp_path, "--pairs-with", "t")
    assert not Path("benchmarks/t-languages.json").exists()


def test_a_rerun_keeps_the_drafts_pairing(tmp_path, monkeypatch):
    _root, made, paired = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    Path("benchmarks").mkdir()
    Path("benchmarks/t.json").write_text(render(paired.raw), encoding="utf-8")
    assert run_main(tmp_path, "--pairs-with", "t") == 0
    out = Path("benchmarks/t-languages.json")
    first = out.read_text(encoding="utf-8")
    assert run_main(tmp_path) == 0  # no flag: the draft's own is used
    assert out.read_text(encoding="utf-8") == first
    assert json.loads(first)["pairs_with"] == "t"


def test_a_rerun_with_another_pairing_stops(tmp_path, monkeypatch):
    _root, made, paired = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    Path("benchmarks").mkdir()
    Path("benchmarks/t.json").write_text(render(paired.raw), encoding="utf-8")
    assert run_main(tmp_path, "--pairs-with", "t") == 0
    before = Path("benchmarks/t-languages.json").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="pairs with 't', not 'u'"):
        run_main(tmp_path, "--pairs-with", "u")
    assert Path("benchmarks/t-languages.json").read_text(encoding="utf-8") == before
