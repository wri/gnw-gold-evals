"""Verify (or repair) case-store integrity: uids, validity, manifest.

    uv run python tools/check.py          # verify; nonzero exit on drift (CI)
    uv run python tools/check.py --fix    # recompute uids + manifest after edits

The editing workflow this enables: edit a case YAML by hand -> run
``check.py --fix`` -> commit. The uid then truthfully identifies the new
version of the case, and the manifest's caseset_version moves with it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.store import (
    build_manifest,
    load_store,
    read_manifest,
    write_case,
    write_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=Path("cases"))
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    entries = load_store(args.cases_dir)
    if not entries:
        print(f"no cases found under {args.cases_dir}")
        return 1

    problems: list[str] = []
    for path, case, stored_uid in entries:
        problems += case.validate()
        if stored_uid != case.uid:
            if args.fix:
                write_case(args.cases_dir, case)
                print(f"fixed uid: {path} {stored_uid or '(none)'} -> {case.uid}")
            else:
                problems.append(f"{path}: stored uid {stored_uid!r} != {case.uid}")

    ids = [case.id for _p, case, _u in entries]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate case ids: {duplicates}")

    cases = [case for _p, case, _u in entries]
    manifest_on_disk = read_manifest(args.cases_dir)
    source = (manifest_on_disk or {}).get("source", "unknown")
    manifest = build_manifest(cases, source)
    if manifest_on_disk != manifest:
        if args.fix:
            write_manifest(args.cases_dir, manifest)
            print(f"manifest regenerated, caseset_version={manifest['caseset_version']}")
        else:
            problems.append("manifest is stale (run check.py --fix)")

    if problems:
        print("FAIL:", *problems, sep="\n  ")
        return 1
    print(
        f"ok: {len(entries)} cases, caseset_version={manifest['caseset_version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
