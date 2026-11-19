"""tools/pairs_from_sheet.py: the cases of a reviewed language pair sheet."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pairs_from_sheet as pfs  # noqa: E402
from check import twin_problems  # noqa: E402

from goldset.store import Case, load_store, write_case  # noqa: E402

LOSS = {"aoi_ids": "BRA.14", "dataset_id": "4", "data_pull": "TRUE"}
COLUMNS = ["pair_id", "kind", "use_case", "type", "set", "cohort", "english_id",
           "english_uid", "english_query", "portuguese_query", "source", "notes",
           "expected_verified", "still_unverified", "verify_precedent"]
MEMBER = Case(id="ch-quant-001", status="ready", group="tcl", set="quantification",
              query="How much tree cover did Pará lose in 2024?", expected=LOSS,
              notes={"use_cases": "UC4;UC5", "synthetic": "TRUE"})
OTHER = Case(id="ch-quant-002", status="ready", group="tcl", set="quantification",
             query="How much tree cover did Acre lose in 2023?",
             expected={**LOSS, "aoi_ids": "BRA.1"})
REFUSAL = Case(id="ch-refusal-001", status="ready", group="should_decline",
               set="refusal", query="Write my thesis", expected={"text": "Declines."})


def translated(**fields):
    return {"pair_id": "pt-t-001", "kind": "translated", "use_case": "UC4",
            "type": "quantification", "set": "quantification", "cohort": "tcl",
            "english_id": MEMBER.id, "english_uid": MEMBER.uid,
            "english_query": MEMBER.query,
            "portuguese_query": "Quanta cobertura arbórea o Pará perdeu em 2024?",
            "source": MEMBER.id, **fields}


def native(**fields):
    return {"pair_id": "pt-n-001", "kind": "native", "use_case": "UC1",
            "type": "quantification", "set": "quantification", "cohort": "tcl",
            "english_query": "how much forest did maranhão lose in 2022",
            "portuguese_query": "quanta floresta o maranhão perdeu em 2022",
            "source": "trace 2026-03",
            "expected_verified": "{aoi_name: Maranhão (state), aoi_source: gadm, "
                                 "aoi_ids: BRA.10, dataset_id: '4', data_pull: 'TRUE'}",
            "verify_precedent": "ch-quant-002", **fields}


def store(tmp_path):
    root = tmp_path / "cases"
    for case in (MEMBER, OTHER, REFUSAL):
        write_case(root, case)
    return root


def sheet(tmp_path, *rows, columns=COLUMNS):
    path = tmp_path / "pt-pairs-reviewed.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def run(root, path, *extra, language="pt", column="portuguese_query"):
    return pfs.main(["--sheet", str(path), "--language", language,
                     "--query-column", column, "--date", "2026-11-25",
                     "--cases-dir", str(root), *extra])


def cases_in(root):
    return {case.id: case for _p, case, _u in load_store(root)}


def test_writes_a_translated_pair_and_a_native_pair(tmp_path, capsys):
    root = store(tmp_path)
    assert run(root, sheet(tmp_path, translated(), native())) == 0
    assert "wrote 2 rows: 2 cases in pt, 1 English twins" in capsys.readouterr().out
    made = cases_in(root)
    # A translated row: the member's set, cohort and expected; the member is
    # its twin.
    question = made["ch-quant-001-pt"]
    assert (question.language, question.twin, question.set, question.group) == (
        "pt", MEMBER.id, MEMBER.set, MEMBER.group)
    assert question.expected == MEMBER.expected
    assert question.query == "Quanta cobertura arbórea o Pará perdeu em 2024?"
    assert question.notes == {
        "lineage": "multilingual BENCHMARK 2026-11-25: translation of ch-quant-001"
                   " (pt-t-001)",
        "pair_id": "pt-t-001", "use_cases": "UC4;UC5",
        "language_review": "subagent review 2026-11-25; native speaker not yet",
        "synthetic": "TRUE",
    }
    # A native row: an English twin at the next free id of its set, and the
    # question beside it, with one expected and no helper keys in it.
    twin, prompt = made["ch-quant-003"], made["ch-quant-003-pt"]
    assert twin.language == "en" and twin.query == "how much forest did maranhão lose in 2022"
    assert (prompt.language, prompt.twin) == ("pt", "ch-quant-003")
    assert twin.expected == prompt.expected == {
        "aoi_ids": "BRA.10", "dataset_id": "4", "data_pull": "TRUE"}
    assert twin.notes == {
        "lineage": "multilingual BENCHMARK 2026-11-25: English twin written for"
                   " ch-quant-003-pt (pt-n-001); real pt user prompt, trace 2026-03",
        "pair_id": "pt-n-001", "benchmark_type": "quantification", "use_cases": "UC1",
        "synthetic": "FALSE",
        "verified": "expectations checked 2026-11-25 against 2026 members, the"
                    " catalog, local GADM and prod /api/aois; no agent run yet",
        "aoi_name": "Maranhão (state)", "precedent": "ch-quant-002",
    }
    assert prompt.notes == {
        **twin.notes,
        "lineage": "multilingual BENCHMARK 2026-11-25: prompt as typed (pt-n-001);"
                   " real pt user prompt, trace 2026-03",
        "language_review": "subagent review 2026-11-25; native speaker not yet",
    }
    assert twin_problems(list(made.values())) == []


def test_a_dry_run_checks_and_writes_nothing(tmp_path, capsys):
    root = store(tmp_path)
    assert run(root, sheet(tmp_path, translated(), native()), "--dry-run") == 0
    assert "would write 2 rows: 2 cases in pt" in capsys.readouterr().out
    assert sorted(cases_in(root)) == [MEMBER.id, OTHER.id, REFUSAL.id]


def test_one_bad_row_stops_every_row(tmp_path, capsys):
    root = store(tmp_path)
    bad = native(pair_id="pt-n-002",
                 expected_verified="{aoi_ids: UNVERIFIED (Tocantins, state)}")
    assert run(root, sheet(tmp_path, translated(), native(), bad)) == 1
    out = capsys.readouterr().out
    assert "pt-n-002: an expected value is still UNVERIFIED" in out
    assert "nothing written" in out
    assert sorted(cases_in(root)) == [MEMBER.id, OTHER.id, REFUSAL.id]


@pytest.mark.parametrize(("row", "needle"), [
    (translated(english_uid="0000000000000000"), "uid is not 0000000000000000"),
    (translated(english_id="ch-quant-404"), "member ch-quant-404 is not in the store"),
    (translated(english_id=REFUSAL.id, english_uid=REFUSAL.uid, set="refusal"),
     None),
    (native(cohort="fires"), "the store has no quantification/fires"),
    (native(expected_verified="{aoi_ids: [BRA"), "expected_verified is not YAML"),
    (native(expected_verified="{aoi_name: Pará}"), "holds no expectation"),
    (native(english_query=" "), "empty english_query"),
    (native(portuguese_query=""), "empty portuguese_query"),
    (native(kind="adapted"), "kind 'adapted' is neither translated nor native"),
    (native(use_case="UC9"), "use case 'UC9'"),
    (native(type="spatial"), "type 'spatial'"),
    (native(pair_id=""), "no pair_id"),
])
def test_each_row_problem_is_reported(tmp_path, capsys, row, needle):
    root = store(tmp_path)
    before = sorted(cases_in(root))
    code = run(root, sheet(tmp_path, row))
    out = capsys.readouterr().out
    if needle is None:  # a valid row in another set
        assert code == 0, out
        return
    assert code == 1
    assert needle in out
    assert sorted(cases_in(root)) == before


def expected_row(body):
    return native(expected_verified="{aoi_name: Maranhão, dataset_id: '4', "
                                    "data_pull: TRUE, " + body + "}")


@pytest.mark.parametrize(("body", "needle"), [
    ("aoi_ids: [BRA.10, BRA.11]", "aoi_ids is a list"),
    ("aoi_ids: BRA.10, start_date: {run-30d}", "start_date is a mapping"),
])
def test_a_list_or_mapping_value_is_a_row_problem(tmp_path, capsys, body, needle):
    root = store(tmp_path)
    assert run(root, sheet(tmp_path, expected_row(body))) == 1
    out = capsys.readouterr().out
    assert needle in out and "nothing written" in out
    assert sorted(cases_in(root)) == [MEMBER.id, OTHER.id, REFUSAL.id]


@pytest.mark.parametrize(("body", "key", "value"), [
    # YAML 1.1 reads these as a bool and a float; the sheet holds the text.
    ("aoi_ids: NO", "aoi_ids", "NO"),
    ("aoi_ids: BRA.10, canopy: 0.10", "canopy", "0.10"),
    ("aoi_ids: BRA.10, start_date: '{run-30d}'", "start_date", "{run-30d}"),
    ("aoi_ids: BRA.10", "data_pull", "TRUE"),
])
def test_a_scalar_stays_the_text_the_sheet_holds(tmp_path, body, key, value):
    root = store(tmp_path)
    assert run(root, sheet(tmp_path, expected_row(body))) == 0
    twin = next(c for c in cases_in(root).values() if c.language == "en"
                and c.id not in (MEMBER.id, OTHER.id, REFUSAL.id))
    assert twin.expected[key] == value


def test_a_native_type_must_be_the_type_its_set_measures(tmp_path, capsys):
    # "trend" is a valid type, but the quantification set measures
    # quantification (benchmark_languages.SET_TYPES).
    root = store(tmp_path)
    assert run(root, sheet(tmp_path, native(type="trend"))) == 1
    out = capsys.readouterr().out
    assert "type 'trend' does not fit the set quantification" in out
    assert "nothing written" in out


def nothing_written(root, capsys, row, needle, *extra):
    """Run one row over a store with ``extra`` cases; it must stop with
    ``needle`` and leave the store as it was."""
    for case in extra:
        write_case(root, case)
    before = sorted(cases_in(root))
    assert run(root, sheet(root.parent, row)) == 1
    out = capsys.readouterr().out
    assert needle in out and "nothing written" in out
    assert sorted(cases_in(root)) == before


def test_an_id_the_store_already_holds_is_a_problem(tmp_path, capsys):
    root = store(tmp_path)
    taken = Case(id=f"{MEMBER.id}-pt", status="ready", set=MEMBER.set,
                 group=MEMBER.group, language="pt", twin=MEMBER.id,
                 query="Quanta cobertura arbórea o Pará perdeu?",
                 expected=dict(LOSS))
    nothing_written(root, capsys, translated(),
                    "ch-quant-001-pt: the store or the sheet already has this id",
                    taken)


def test_a_translated_member_must_be_a_single_turn_english_case(tmp_path, capsys):
    root = store(tmp_path)
    spanish = Case(id="ch-quant-003-es", status="ready", set="quantification",
                   group="tcl", language="es", twin=MEMBER.id,
                   query="¿Cuánta cobertura arbórea perdió Pará en 2024?",
                   expected=dict(LOSS))
    nothing_written(root, capsys,
                    translated(english_id=spanish.id, english_uid=spanish.uid),
                    "member ch-quant-003-es is not a single-turn English case",
                    spanish)


def test_a_multi_turn_member_is_not_a_single_turn_english_case(tmp_path, capsys):
    root = store(tmp_path)
    thread = Case(id="ch-quant-003", status="ready", set="quantification",
                  group="tcl", turns=(
                      {"query": "How much tree cover did Pará lose in 2024?",
                       "expected": dict(LOSS)},
                      {"query": "And Acre?", "expected": {**LOSS, "aoi_ids": "BRA.1"}},
                  ))
    nothing_written(root, capsys,
                    translated(english_id=thread.id, english_uid=thread.uid),
                    "member ch-quant-003 is not a single-turn English case", thread)


def test_a_set_with_two_id_prefixes_cannot_number_a_native_twin(tmp_path, capsys):
    root = store(tmp_path)
    stray = Case(id="other-quant-001", status="ready", set="quantification",
                 group="tcl", query="How much did Pará lose?", expected=dict(LOSS))
    nothing_written(root, capsys, native(),
                    "no single id prefix among the numbered cases of the set "
                    "quantification", stray)


def test_a_case_that_fails_validation_is_a_problem():
    # write_case refuses an invalid case, so such a member cannot be on disk:
    # plan() is called on an in-memory store, as main() would call it.
    odd = Case(id="ch-quant-003", status="ready", set="quantification", group="tcl",
               query="How much did Pará lose?", expected=dict(LOSS),
               notes={"use_cases": 5})
    _cases, problems = pfs.plan(
        [translated(english_id=odd.id, english_uid=odd.uid)], "pt",
        "portuguese_query", "2026-11-25", [MEMBER, OTHER, odd])
    assert "ch-quant-003-pt: notes.use_cases is int, expected string" in problems


def test_a_pair_id_twice_in_the_sheet_is_a_problem(tmp_path, capsys):
    root = store(tmp_path)
    assert run(root, sheet(tmp_path, native(), native(english_query="other"))) == 1
    assert "pt-n-001: appears 2 times in the sheet" in capsys.readouterr().out


def test_a_second_run_over_written_pairs_is_refused(tmp_path, capsys):
    root = store(tmp_path)
    path = sheet(tmp_path, translated(), native())
    assert run(root, path) == 0
    written = sorted(cases_in(root))
    capsys.readouterr()
    # The native pair would otherwise be written again under new ids.
    assert run(root, path) == 1
    out = capsys.readouterr().out
    assert "pt-n-001: already in the store (ch-quant-003, ch-quant-003-pt)" in out
    assert "pt-t-001: already in the store (ch-quant-001-pt)" in out
    assert sorted(cases_in(root)) == written


def test_the_sheet_must_hold_the_query_column(tmp_path, capsys):
    root = store(tmp_path)
    path = sheet(tmp_path, native())
    assert run(root, path, column="french_query") == 1
    assert "no column french_query" in capsys.readouterr().out


def test_an_empty_sheet_is_a_problem(tmp_path, capsys):
    root = store(tmp_path)
    assert run(root, sheet(tmp_path)) == 1
    assert "no rows" in capsys.readouterr().out


@pytest.mark.parametrize("language", ["en", "de"])
def test_only_another_case_language_is_accepted(tmp_path, language):
    with pytest.raises(SystemExit) as exit_:
        run(store(tmp_path), sheet(tmp_path, native()), language=language)
    assert exit_.value.code == 2


def test_the_date_must_be_a_day(tmp_path):
    with pytest.raises(SystemExit):
        pfs.main(["--sheet", "x.csv", "--language", "pt", "--query-column", "q",
                  "--date", "25 Nov"])
