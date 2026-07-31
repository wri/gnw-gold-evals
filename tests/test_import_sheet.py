"""Importer semantics: header scan, column routing, idempotence, dupes."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from import_sheet import find_header, parse_cases, run_import  # noqa: E402

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
    cases, skipped = parse_cases(SHEET)
    assert skipped == 1  # 1-003 has an empty query
    assert [c.id for c in cases] == ["1-001", "1-002"]
    second = cases[1]
    assert second.status == "todo"  # normalised to lowercase
    assert second.expected == {"aoi_ids": "BRA.25", "answer": "1,319,600 ha"}
    assert second.notes == {
        "status_reason": "Chart shows all levels",
        "aoi_type": "gadm",
        "value_1": "679.17",
    }


def test_duplicate_ids_abort():
    bad = SHEET.replace("1-002", "1-001")
    with pytest.raises(ValueError, match="duplicate test_ids"):
        parse_cases(bad)


def test_missing_required_column_aborts():
    with pytest.raises(ValueError, match="missing required columns"):
        parse_cases("a,b,query\n1,2,hello\n")


def test_run_import_idempotent_and_prunes(tmp_path):
    assert run_import(SHEET, tmp_path, "test", prune=False) == 0
    snapshot = {p: p.read_text() for p in tmp_path.rglob("*")  if p.is_file()}
    assert run_import(SHEET, tmp_path, "test", prune=False) == 0
    assert snapshot == {p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()}

    shrunk = "\n".join(
        line for line in SHEET.splitlines() if not line.startswith("1-002")
    )
    assert run_import(shrunk, tmp_path, "test", prune=True) == 0
    assert not (tmp_path / "direct" / "1-002.yaml").exists()
    assert (tmp_path / "temporal" / "1-001.yaml").exists()
