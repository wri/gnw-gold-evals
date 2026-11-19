"""BENCHMARK manifest contract (goldset.benchmark)."""

import json
from pathlib import Path

import pytest

from goldset.benchmark import (
    QUERY_TYPES,
    SCHEMA_VERSION,
    from_dict,
    load_benchmark,
    manifest_sha,
    render,
)

REPO = Path(__file__).resolve().parents[1]


def member(uid="u1", id="ch-aoi-001", type="geospatial", **kw):
    optional = {k: kw[k] for k in ("language", "twin_uid") if k in kw}
    return {"uid": uid, "id": id, "type": type, "set": kw.get("set", "aoi"),
            "cohort": kw.get("cohort", "direct"),
            "difficulty": kw.get("difficulty", "easy"),
            "stages": kw.get("stages", ["retrieval"]), **optional}


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
        **({"pairs_with": kw["pairs_with"]} if "pairs_with" in kw else {}),
    }


def test_query_types_split_geospatial_and_dataset():
    keys = [t["key"] for t in QUERY_TYPES]
    assert len(keys) == 13 and "spatial" not in keys
    by_key = {t["key"]: t for t in QUERY_TYPES}
    assert by_key["geospatial"]["sets"] == ["aoi"]
    assert by_key["dataset"]["sets"] == ["dataset"]
    measured = {k for k, t in by_key.items() if t["sets"]}
    assert measured == {"geospatial", "dataset", "quantification", "comparison", "trend",
                        "monitoring", "causal", "portfolio"}


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
    (manifest(members=[member(language="fr", twin_uid="u2")]), "language 'fr'"),
    (manifest(members=[member(language="en", twin_uid="u2")]), "language 'en'"),
    (manifest(members=[member(language="es")]), "needs a twin_uid"),
    (manifest(members=[member(language="id", twin_uid="u1")]), "its own twin"),
    (manifest(pairs_with=2026), "not a version name"),
    (manifest(pairs_with="2026-draft"), "pair with itself"),
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


def test_language_facets_load_and_are_written_only_when_set():
    spanish = member("u2", "ch-aoi-002", language="es", twin_uid="u1")
    bench = from_dict(manifest(members=[member(), spanish], pairs_with="2026"))
    assert bench.validate() == []
    assert bench.pairs_with == "2026"
    english, native = bench.members
    assert (native.language, native.twin_uid) == ("es", "u1")
    assert native.to_dict() == spanish
    assert (english.language, english.twin_uid) == ("", "")
    assert english.to_dict() == member()
    assert from_dict(manifest()).pairs_with == ""


def test_committed_manifests_round_trip_unchanged():
    paths = sorted((REPO / "benchmarks").glob("*.json"))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        bench = from_dict(json.loads(text))
        assert render(bench.raw) == text, path
        if not bench.pairs_with:
            assert not any(m.language or m.twin_uid for m in bench.members), path
            continue
        # A languages companion: language and twin_uid exist only here, and its
        # pairs_with must name a committed manifest for the twins to resolve against.
        assert any(m.language for m in bench.members), path
        assert all(m.twin_uid for m in bench.members if m.language), path
        assert (REPO / "benchmarks" / f"{bench.pairs_with}.json").exists(), path
