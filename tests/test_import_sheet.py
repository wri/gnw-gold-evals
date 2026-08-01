"""Importer semantics: header scan, column routing, idempotence, dupes,
and the PR-10 sheet-pull hardening (source_tab scoping, collisions,
sheet-uid drift)."""

import codecs
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import import_sheet
from import_sheet import fetch, find_header, main, parse_cases, run_import

from goldset.store import Case, load_store, read_case, read_manifest, write_case

SHEET = """\
GOLD set,,do not edit row,,,
test_id,status,status_reason,test_group,query,AOI type,expected_aoi_ids,expected_answer,note_value_1
1-001,done,,temporal,Alerts in Mount Hakusan in 2024?,kba,15665,TRUE,
1-002,Todo,Chart shows all levels,direct,Sao Paulo disturbance in H2 2024?,gadm,BRA.25,"1,319,600 ha",679.17
1-003,not doing,,direct,,gadm,XYZ,should be skipped,
"""


def test_find_header_tolerates_preamble():
    import csv
    import io

    rows = list(csv.reader(io.StringIO(SHEET)))
    assert find_header(rows) == 1


def test_parse_routes_columns():
    cases, skipped, edited = parse_cases(SHEET, source_tab="gid:0")
    assert skipped == 1  # 1-003 has an empty query
    assert edited == []
    assert [c.id for c in cases] == ["1-001", "1-002"]
    second = cases[1]
    assert second.status == "todo"  # normalised to lowercase
    assert second.expected == {"aoi_ids": "BRA.25", "answer": "1,319,600 ha"}
    assert second.notes == {
        "status_reason": "Chart shows all levels",
        "aoi_type": "gadm",
        "value_1": "679.17",
        "source_tab": "gid:0",  # P2: provenance recorded, never hashed
    }


def test_source_tab_does_not_change_uid():
    with_tab, _, _ = parse_cases(SHEET, source_tab="gid:0")
    without, _, _ = parse_cases(SHEET)
    assert [c.uid for c in with_tab] == [c.uid for c in without]


def test_duplicate_ids_abort():
    bad = SHEET.replace("1-002", "1-001")
    with pytest.raises(ValueError, match="duplicate test_ids"):
        parse_cases(bad)


def test_missing_required_column_aborts():
    with pytest.raises(ValueError, match="missing required columns"):
        parse_cases("a,b,query\n1,2,hello\n")


def test_sheet_uid_drift_reported_not_trusted(tmp_path):
    """P5: a uid column on the sheet is advisory — recomputed uids win,
    mismatches are reported as sheet-side edits."""
    cases, _, _ = parse_cases(SHEET)
    real_uid = cases[0].uid
    with_uid_col = SHEET.replace(
        "test_group,query,AOI type",
        "test_group,query,uid,AOI type",
    ).replace(
        "temporal,Alerts in Mount Hakusan in 2024?,kba",
        f"temporal,Alerts in Mount Hakusan in 2024?,{real_uid},kba",
    ).replace(
        "direct,Sao Paulo disturbance in H2 2024?,gadm",
        "direct,Sao Paulo disturbance in H2 2024?,deadbeefdeadbeef,gadm",
    )
    parsed, _, edited = parse_cases(with_uid_col)
    assert edited == ["1-002"]  # stale sheet uid
    assert parsed[0].uid == real_uid  # recomputed, not read
    assert "uid" not in parsed[0].notes  # sync columns never become notes


def test_run_import_idempotent(tmp_path):
    assert run_import(SHEET, tmp_path, "test", prune=False, source_tab="gid:0") == 0
    snapshot = {p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    assert run_import(SHEET, tmp_path, "test", prune=False, source_tab="gid:0") == 0
    assert snapshot == {p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()}


def test_prune_is_scoped_to_the_importing_tab(tmp_path):
    """P3: --prune deletes only this tab's own orphans; cases from other
    sources (or with no source_tab) are reported and left alone."""
    foreign = Case(id="9-001", status="ready", group="direct", query="other tab",
                   notes={"source_tab": "gid:999"})
    legacy = Case(id="9-002", status="ready", group="direct", query="pre-P2 case")
    write_case(tmp_path, foreign)
    write_case(tmp_path, legacy)

    assert run_import(SHEET, tmp_path, "test", prune=True, source_tab="gid:0") == 0
    assert (tmp_path / "direct" / "9-001.yaml").exists()   # other tab: untouched
    assert (tmp_path / "direct" / "9-002.yaml").exists()   # unmanaged: untouched

    # a row this tab imported earlier, now gone from the sheet -> pruned
    shrunk = "\n".join(
        line for line in SHEET.splitlines() if not line.startswith("1-002")
    )
    assert run_import(shrunk, tmp_path, "test", prune=True, source_tab="gid:0") == 0
    assert not (tmp_path / "direct" / "1-002.yaml").exists()
    assert (tmp_path / "temporal" / "1-001.yaml").exists()


def test_collision_with_other_source_errors_without_update(tmp_path):
    """P4: taking over another source's test_id must be explicit."""
    theirs = Case(id="1-001", status="ready", group="temporal", query="theirs",
                  notes={"source_tab": "gid:999"})
    write_case(tmp_path, theirs)
    assert run_import(SHEET, tmp_path, "test", prune=False, source_tab="gid:0") == 1
    # unchanged
    kept, _ = read_case(tmp_path / "temporal" / "1-001.yaml")
    assert kept.query == "theirs"

    assert run_import(SHEET, tmp_path, "test", prune=False,
                      source_tab="gid:0", update=True) == 0
    taken, _ = read_case(tmp_path / "temporal" / "1-001.yaml")
    assert taken.notes["source_tab"] == "gid:0"


def test_update_takeover_with_group_change_leaves_single_file(tmp_path):
    """A takeover whose winning row also changes test_group moves the case
    file; the loser's old file must be deleted, or the store holds two
    files with the same test_id forever (its stale source_tab means no
    later prune would ever touch it) and check.py fails."""
    theirs = Case(id="1-001", status="ready", group="legacy group",
                  query="theirs", notes={"source_tab": "gid:999"})
    old_path = write_case(tmp_path, theirs)
    assert old_path == tmp_path / "legacy-group" / "1-001.yaml"

    # SHEET puts 1-001 in group "temporal" -> different path than theirs.
    assert run_import(SHEET, tmp_path, "test", prune=False,
                      source_tab="gid:0", update=True) == 0
    assert not old_path.exists()
    assert list(tmp_path.rglob("1-001.yaml")) == [
        tmp_path / "temporal" / "1-001.yaml"
    ]
    ids = [case.id for _p, case, _u in load_store(tmp_path)]
    assert ids.count("1-001") == 1
    manifest_ids = [c["id"] for c in read_manifest(tmp_path)["cases"]]
    assert manifest_ids.count("1-001") == 1

    # idempotent: a re-run changes nothing on disk
    snapshot = {p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    assert run_import(SHEET, tmp_path, "test", prune=False,
                      source_tab="gid:0", update=True) == 0
    assert snapshot == {
        p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()
    }


def test_group_change_within_same_tab_moves_the_file(tmp_path):
    """Same leak, no takeover involved: re-importing one's own tab after a
    test_group edit must relocate the file, not duplicate the id."""
    assert run_import(SHEET, tmp_path, "test", prune=False,
                      source_tab="gid:0") == 0
    regrouped = SHEET.replace("1-001,done,,temporal,", "1-001,done,,direct,")
    assert run_import(regrouped, tmp_path, "test", prune=False,
                      source_tab="gid:0") == 0
    assert list(tmp_path.rglob("1-001.yaml")) == [
        tmp_path / "direct" / "1-001.yaml"
    ]


def test_empty_source_tab_rejected_at_cli(tmp_path, monkeypatch, capsys):
    """An explicit --source-tab '' would silently disable the collision
    guard and prune scoping; the CLI must refuse it outright."""
    sheet_csv = tmp_path / "tab.csv"
    sheet_csv.write_text(SHEET, encoding="utf-8")
    for empty in ("", "   "):
        monkeypatch.setattr(sys, "argv", [
            "import_sheet.py", "--csv", str(sheet_csv),
            "--cases-dir", str(tmp_path / "cases"), "--source-tab", empty,
        ])
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 2
        assert "--source-tab must not be empty" in capsys.readouterr().err
    assert not (tmp_path / "cases").exists()  # nothing was imported


def test_bom_prefixed_csv_imports(tmp_path, monkeypatch):
    """A BOM-prefixed export whose header is the first row must parse; with
    plain utf-8 the BOM glues onto 'test_id' and the import aborts with a
    misleading 'missing required columns' error."""
    no_preamble = SHEET.split("\n", 1)[1]  # header row first, no preamble
    sheet_csv = tmp_path / "tab.csv"
    sheet_csv.write_bytes(codecs.BOM_UTF8 + no_preamble.encode("utf-8"))
    monkeypatch.setattr(sys, "argv", [
        "import_sheet.py", "--csv", str(sheet_csv),
        "--cases-dir", str(tmp_path / "cases"),
    ])
    assert main() == 0
    imported, _ = read_case(tmp_path / "cases" / "temporal" / "1-001.yaml")
    assert imported.id == "1-001"  # no BOM residue in the id column


def test_fetch_decodes_bom(monkeypatch):
    payload = codecs.BOM_UTF8 + "test_id,query\n1-001,héllo\n".encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return payload

    monkeypatch.setattr(
        import_sheet.urllib.request,
        "urlopen",
        lambda url, timeout: FakeResponse(),
    )
    assert fetch("https://example.test/export") == "test_id,query\n1-001,héllo\n"
