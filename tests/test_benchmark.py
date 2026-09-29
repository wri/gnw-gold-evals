"""BENCHMARK manifest contract (goldset.benchmark)."""

import json

import pytest

from goldset.benchmark import (
    QUERY_TYPES,
    SCHEMA_VERSION,
    from_dict,
    load_benchmark,
    manifest_sha,
)


def member(uid="u1", id="ch-aoi-001", type="geospatial", **kw):
    return {"uid": uid, "id": id, "type": type, "set": kw.get("set", "aoi"),
            "cohort": kw.get("cohort", "direct"),
            "difficulty": kw.get("difficulty", "easy"),
            "stages": kw.get("stages", ["retrieval"])}


def manifest(**kw):
    return {
        "schema_version": SCHEMA_VERSION,
        "version": kw.get("version", "2026-draft"),
        "status": kw.get("status", "draft"),
        "frozen": kw.get("frozen"),
        "source": {"cases_dir": "cases/challenge"},
        "sampling": {},
        "types": list(QUERY_TYPES),
        "members": kw.get("members", [member()]),
        "errata": kw.get("errata", []),
    }


def test_query_types_split_geospatial_and_dataset():
    keys = [t["key"] for t in QUERY_TYPES]
    assert len(keys) == 12 and "spatial" not in keys
    by_key = {t["key"]: t for t in QUERY_TYPES}
    assert by_key["geospatial"]["sets"] == ["aoi"]
    assert by_key["dataset"]["sets"] == ["dataset"]
    measured = {k for k, t in by_key.items() if t["sets"]}
    assert measured == {"geospatial", "dataset", "quantification", "comparison", "trend"}


def test_round_trip_and_member_uids():
    bench = from_dict(manifest(members=[member("u1"), member("u2", "ch-aoi-002")]))
    assert bench.validate() == []
    assert bench.member_uids == {"u1", "u2"}


def test_errata_void_members():
    bench = from_dict(manifest(
        members=[member("u1"), member("u2", "ch-aoi-002")],
        errata=[{"uid": "u2", "date": "2026-12-01", "reason": "dead ground truth"}],
    ))
    assert bench.validate() == []
    assert bench.member_uids == {"u1"}
    assert [m.id for m in bench.active_members] == ["ch-aoi-001"]


@pytest.mark.parametrize("data, needle", [
    (manifest(status="final"), "status"),
    (manifest(status="frozen"), "frozen date"),
    (manifest(members=[member(), member()]), "duplicate member uid"),
    (manifest(members=[member(type="spatial")]), "unknown type"),
    (manifest(members=[member(stages=["fetch"])]), "unknown stages"),
    (manifest(errata=[{"uid": "nope", "date": "d", "reason": "r"}]), "does not name a member"),
    (manifest(errata=[{"uid": "u1"}]), "date and a reason"),
])
def test_validate_rejects(data, needle):
    problems = from_dict(data).validate()
    assert any(needle in p for p in problems), problems


def test_schema_version_and_member_fields_are_enforced():
    with pytest.raises(ValueError, match="schema_version"):
        from_dict({**manifest(), "schema_version": 99})
    broken = member()
    del broken["stages"]
    with pytest.raises(ValueError, match="missing"):
        from_dict(manifest(members=[broken]))


def test_load_raises_on_invalid_and_sha_is_stable(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(manifest()))
    assert load_benchmark(good).version == "2026-draft"
    assert manifest_sha(good) == manifest_sha(good) and len(manifest_sha(good)) == 16
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(manifest(status="frozen")))
    with pytest.raises(ValueError, match="frozen date"):
        load_benchmark(bad)
