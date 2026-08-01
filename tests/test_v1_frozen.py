"""Tripwire: cases/v1 is the FROZEN as-imported baseline.

cases/v1 changes on deliberate sheet re-imports ONLY. All curation work
(expectation edits, unparkings, new cases) belongs in cases/v2. Because the
caseset_version is a hash over every case uid, ANY semantic edit under
cases/v1 moves it and fails this test — which is the point: v2 work leaking
into v1 should fail CI, not pass silently.

If this test fails and you did NOT just re-import the sheet into v1, revert
the v1 change and land it in cases/v2 instead. If you DID deliberately
re-import, update V1_CASESET_VERSION below in the same PR and say so in the
PR description.
"""

import json
from pathlib import Path

from goldset.store import build_manifest, load_store

ROOT = Path(__file__).resolve().parents[1]
V1_DIR = ROOT / "cases" / "v1"

# The as-imported (pre-H7) baseline. Only a deliberate sheet re-import may
# change this constant.
V1_CASESET_VERSION = "185eb0b1bb6ea24a"


def test_v1_manifest_pins_baseline_caseset_version():
    manifest = json.loads((V1_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["caseset_version"] == V1_CASESET_VERSION, (
        "cases/v1 is the frozen as-imported baseline; its caseset_version may "
        "only change on a deliberate sheet re-import. Land curation edits in "
        "cases/v2 instead (see this file's docstring)."
    )


def test_v1_files_hash_to_the_pinned_version():
    """Recompute the version from the YAML files themselves, so a stale
    manifest cannot hide an edited case file."""
    cases = [case for _path, case, _uid in load_store(V1_DIR)]
    manifest = build_manifest(cases, source="gold-live.csv")
    assert manifest["caseset_version"] == V1_CASESET_VERSION, (
        "a case file under cases/v1 was edited — v1 is frozen; make the "
        "change in cases/v2 (see this file's docstring)."
    )
