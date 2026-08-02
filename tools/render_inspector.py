"""Render a ledger run as a standalone per-check inspection matrix.

    uv run python tools/render_inspector.py results/runs/<run_id>.json
    # -> results/reports/<run_id>_inspector.html

One row per case, one column per check (grouped by bucket): pass/fail/
not-evaluated per cell, expected vs measured in the row expansion, row
verdict plus a flaky tag whenever trials disagreed. The template also
works uninjected: opened raw it accepts a run JSON by drag-and-drop.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import INFO_ONLY
from goldset.ledger import read_run

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_html import load_case_contexts

PLACEHOLDER = "__RUN_PAYLOAD__"
TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "run-inspector.html"


def render_inspector(run: dict, template_text: str, generated: str,
                     cases: dict | None = None) -> str:
    if PLACEHOLDER not in template_text:
        raise ValueError(f"template is missing the {PLACEHOLDER} placeholder")
    payload = json.dumps(
        {
            "run": run,
            "info_only": sorted(INFO_ONLY),
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
                        help="default: results/reports/<run_id>_inspector.html")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/v2"))
    args = parser.parse_args()

    run = read_run(args.run)
    contexts = (
        load_case_contexts(args.cases_dir, run) if args.cases_dir.exists() else {}
    )
    out = args.out or args.run.parents[1] / "reports" / f"{run['run_id']}_inspector.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.write_text(
        render_inspector(
            run, TEMPLATE.read_text(encoding="utf-8"), generated, cases=contexts
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
