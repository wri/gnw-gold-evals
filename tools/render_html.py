"""Render a ledger run as a standalone HTML report.

    uv run python tools/render_html.py results/runs/<run_id>.json
    # -> results/reports/<run_id>.html

Injects the run (plus the current INFO_ONLY set, so verdict rendering
matches buckets.py) into ``templates/run-report.html``. The template also
works uninjected: opened raw it accepts a run JSON by drag-and-drop.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import DEDICATED, INFO_ONLY
from goldset.ledger import read_run
from goldset.store import load_store

PLACEHOLDER = "__RUN_PAYLOAD__"
TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "run-report.html"


def _case_context(case) -> dict:
    """The plain-language context the report shows beside a failing row."""
    turns = getattr(case, "turns", ()) or ()
    context = {
        "query": case.query or (turns[0]["query"] if turns else ""),
        "group": case.group,
        "scope": case.expected.get("scope", ""),
        "expected": dict(case.expected),
    }
    if turns:
        context["turns"] = [
            {"query": t.get("query", ""), "expected": dict(t.get("expected") or {})}
            for t in turns
        ]
    return context


def load_case_contexts(cases_dir: Path, run: dict) -> dict[str, dict]:
    """uid -> context for every run entry resolvable in the store (uid
    first, lineage id as fallback so older runs still enrich)."""
    by_uid, by_id = {}, {}
    for _path, case, _uid in load_store(cases_dir):
        by_uid[case.uid] = case
        by_id[case.id] = case
    contexts = {}
    for entry in run.get("results", []):
        uid = entry.get("uid")
        case = by_uid.get(uid) or by_id.get(entry.get("id"))
        if uid and case is not None:
            contexts[uid] = _case_context(case)
    return contexts


def render_report(
    run: dict, template_text: str, generated: str, cases: dict | None = None
) -> str:
    if PLACEHOLDER not in template_text:
        raise ValueError(f"template is missing the {PLACEHOLDER} placeholder")
    payload = json.dumps(
        {
            "run": run,
            "info_only": sorted(INFO_ONLY),
            "dedicated_map": dict(DEDICATED),
            "generated": generated,
            "cases": cases or {},
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")  # keep the inline <script> JSON unterminated
    return template_text.replace(PLACEHOLDER, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="results/runs/<run_id>.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="default: results/reports/<run_id>.html")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/v2"))
    args = parser.parse_args()

    run = read_run(args.run)
    contexts = (
        load_case_contexts(args.cases_dir, run) if args.cases_dir.exists() else {}
    )
    out = args.out or args.run.parents[1] / "reports" / f"{run['run_id']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.write_text(
        render_report(
            run, TEMPLATE.read_text(encoding="utf-8"), generated, cases=contexts
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
