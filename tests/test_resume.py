"""Resume flow: the in-flight partial ledger and the --resume CLI path.

A run appends one fsynced JSONL line per completed case so a killed run
loses at most the case that was mid-write; --resume reconstructs the run's
config from the partial's header line and runs only what's missing.
"""

from __future__ import annotations

import json

import pytest

from goldset.ledger import (
    append_partial_entry,
    partial_path,
    read_partial,
    write_partial_header,
)


def make_header(**overrides) -> dict:
    header = {
        "run_id": "20260831T143429Z_prod_experimental",
        "started": "2026-08-31T14:34:29Z",
        "environment": "prod",
        "resolved_url": "https://api.globalnaturewatch.org",
        "ff": "experimental",
        "build": "baseline",
        "trials": 3,
        "workers": 10,
        "trial_timeout": 900.0,
        "slow_threshold": 180.0,
        "cases_dir": "cases/v2",
        "caseset_version": "2f8b10272938527c",
        "status_exclude": "not doing",
        "id": None,
        "group": None,
        "note": None,
    }
    return {**header, **overrides}


ENTRY_A = {"uid": "a" * 16, "id": "1-001", "checks": {"aoi_id_match": 1.0}}
ENTRY_B = {"uid": "b" * 16, "id": "1-002", "checks": {"aoi_id_match": 0.0}}


def test_partial_round_trip(tmp_path):
    header = make_header()
    path = write_partial_header(tmp_path, header)
    assert path == partial_path(tmp_path, header["run_id"])
    append_partial_entry(path, ENTRY_A)
    append_partial_entry(path, ENTRY_B)
    read_header, entries = read_partial(path)
    assert read_header == header
    assert entries == [ENTRY_A, ENTRY_B]


def test_header_refuses_missing_fields(tmp_path):
    header = make_header()
    del header["caseset_version"]
    with pytest.raises(ValueError, match="missing fields"):
        write_partial_header(tmp_path, header)


def test_header_refuses_existing_partial(tmp_path):
    write_partial_header(tmp_path, make_header())
    with pytest.raises(ValueError, match="already exists"):
        write_partial_header(tmp_path, make_header())


def test_read_drops_truncated_final_line(tmp_path):
    path = write_partial_header(tmp_path, make_header())
    append_partial_entry(path, ENTRY_A)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"uid": "cccccccccccccccc", "checks": {"aoi')
    _, entries = read_partial(path)
    assert entries == [ENTRY_A]


def test_read_refuses_corrupt_middle_line(tmp_path):
    path = write_partial_header(tmp_path, make_header())
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write(json.dumps(ENTRY_A) + "\n")
    with pytest.raises(ValueError, match="corrupt line mid-file"):
        read_partial(path)


def test_read_refuses_duplicate_uids(tmp_path):
    path = write_partial_header(tmp_path, make_header())
    append_partial_entry(path, ENTRY_A)
    append_partial_entry(path, {**ENTRY_A, "checks": {"aoi_id_match": 0.0}})
    with pytest.raises(ValueError, match="duplicate entry"):
        read_partial(path)


def test_read_refuses_entry_without_uid(tmp_path):
    path = write_partial_header(tmp_path, make_header())
    append_partial_entry(path, {"id": "1-001", "checks": {}})
    with pytest.raises(ValueError, match="without uid/checks"):
        read_partial(path)


def test_read_refuses_entry_first_line(tmp_path):
    path = partial_path(tmp_path, "x")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(ENTRY_A) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a run header"):
        read_partial(path)


def test_read_refuses_empty_file(tmp_path):
    path = partial_path(tmp_path, "x")
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        read_partial(path)
