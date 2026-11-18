"""Copy the expectations from one case of a language pair to the other.

    uv run python tools/twin_case.py --from ch-quant-001 --to ch-quant-401
    uv run python tools/twin_case.py --from ch-quant-001 --to ch-quant-401 --check

A case in another language and its English twin must hold the same
expectations (``tools/check.py`` fails when they differ). This tool writes
them once: ``expected`` of the ``--from`` case replaces ``expected`` of the
``--to`` case, in either direction, and the target file is rewritten with
its new uid. Exactly one case of the pair must be in another language and
name the other as its ``twin``.

``--check`` writes nothing: it reports the keys on which the pair differs
and exits 1 when there are any.

The target's uid changes, so finish the after-edit steps (``check.py --fix``
and ``coverage_doc.py``, both with ``--cases-dir``) before you commit. A
benchmark that holds the old uid loses that member.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check import expected_differences  # noqa: E402

from goldset.store import Case, case_path, load_store, write_case  # noqa: E402


def require_pair(source: Case, target: Case) -> None:
    """Exit unless one case is in another language and names the other, an
    English case, as its twin."""
    native = [case for case in (source, target) if case.language != "en"]
    if len(native) != 1:
        raise SystemExit(
            f"{source.id} and {target.id}: exactly one case of a pair is in "
            f"another language, not {len(native)}"
        )
    english = target if native[0] is source else source
    if native[0].twin != english.id:
        raise SystemExit(
            f"{native[0].id} names {native[0].twin or 'no case'} as its twin, "
            f"not {english.id}"
        )
    if english.is_multiturn:
        raise SystemExit(f"{english.id} is multi-turn: it has no one expected")


def twin_case(
    cases_dir: Path, source_id: str, target_id: str, check_only: bool = False
) -> tuple[list[str], str, str]:
    """(keys that differed, the target's old uid, its uid afterwards)."""
    found = {
        case.id: (path, case)
        for path, case, _uid in load_store(cases_dir)
        if case.id in (source_id, target_id)
    }
    missing = [i for i in (source_id, target_id) if i not in found]
    if missing or source_id == target_id:
        raise SystemExit(f"need two different cases in {cases_dir}; missing {missing}")
    (_source_path, source), (target_path, target) = found[source_id], found[target_id]
    require_pair(source, target)
    differing = expected_differences(source, target)
    if check_only or not differing:
        return differing, target.uid, target.uid
    # write_case picks the path, so a file elsewhere would become a second copy.
    if target_path != case_path(cases_dir, target):
        raise SystemExit(f"{target_path} is not where the store writes {target.id}")
    updated = replace(target, expected=dict(source.expected))
    write_case(cases_dir, updated)
    return differing, target.uid, updated.uid


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="source", required=True, metavar="CASE_ID")
    parser.add_argument("--to", dest="target", required=True, metavar="CASE_ID")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/challenge"))
    parser.add_argument("--check", action="store_true",
                        help="report whether the pair differs; write nothing")
    args = parser.parse_args()
    differing, old_uid, new_uid = twin_case(
        args.cases_dir, args.source, args.target, args.check
    )
    if not differing:
        print(f"ok: {args.source} and {args.target} hold the same expected")
        return 0
    if args.check:
        print(f"{args.source} and {args.target} differ in {differing}")
        return 1
    print(f"wrote {args.target}: expected copied from {args.source} ({differing})")
    print(f"uid: {old_uid} -> {new_uid}")
    print(f"next: tools/check.py --fix --cases-dir {args.cases_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
