"""Plain baseline: Sonnet + web against Horizon on BENCHMARK draft-5, reply only.

    uv run python tools/plain_baseline.py references --for horizon
    uv run python tools/plain_baseline.py references --for <sonnet run id>

Plan of record: the "Plain Sonnet on BENCHMARK" doc (AJ, 2026-10-30). Output
lives under ``results/plain/``; nothing here writes to ``results/benchmark/``,
so the FE scorecards page can never pick it up.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402

from goldset.benchmark import load_benchmark  # noqa: E402
from goldset.cli import resolve_case  # noqa: E402
from goldset.groundtruth import AnalyticsClient  # noqa: E402
from goldset.plain import horizon, reference  # noqa: E402
from goldset.store import Case, load_store  # noqa: E402

BENCHMARK = Path("benchmarks/2026-draft-5.json")
CASES = Path("cases/challenge")
OUT = Path("results/plain")
HORIZON = "horizon-draft5"


def members() -> dict[str, Case]:
    """The draft-5 questions that judge a reply: 253 of the 269."""
    bench = load_benchmark(BENCHMARK)
    uids = {m.uid for m in bench.members}
    cases = {c.uid: c for _, c, _ in load_store(CASES) if c.uid in uids}
    reply_judged = ("text", "figure", "figure_claim")
    return {uid: c for uid, c in cases.items()
            if any(c.expected.get(k) for k in reply_judged)}


def _when(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def cmd_references(args: argparse.Namespace) -> int:
    cases = {uid: c for uid, c in members().items() if c.expected.get("figure")}
    if args.uids:
        wanted = set(Path(args.uids).read_text().split())
        cases = {uid: c for uid, c in cases.items() if uid in wanted}
    known, _ = horizon.known_area_sources()
    if args.for_ == HORIZON:
        questions = horizon.load(set(cases))
        when = {uid: _when(q.started) for uid, q in questions.items()}
    else:
        run = json.loads((OUT / "runs" / f"{args.for_}.json").read_text(encoding="utf-8"))
        when = {uid: _when(run["started"]) for uid in cases}
    path = OUT / "references" / f"{args.for_}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))["questions"] if path.exists() else {}
    todo = []
    for uid, case in cases.items():
        if uid in stored and stored[uid]["status"] == "ok" and not args.refetch:
            continue
        now = when[uid]
        todo.append(reference.plan(resolve_case(case, now), now.strftime("%Y-%m-%d"), known))
    token = os.environ.get("ANALYTICS_API_TOKEN") or os.environ.get("PROD_API_TOKEN")
    if not token:
        print("ANALYTICS_API_TOKEN or PROD_API_TOKEN must be set", file=sys.stderr)
        return 2
    print(f"fetching {sum(len(r.tables) for r in todo)} tables for {len(todo)} questions")
    reference.fetch(todo, AnalyticsClient(token))
    for ref in todo:
        stored[ref.uid] = ref.to_json()
    _write(path, {"for": args.for_, "written": datetime.now(UTC).isoformat(timespec="seconds"),
                  "questions": stored})
    counts: dict[str, int] = {}
    for entry in stored.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    print(f"wrote {path}: {counts}")
    for uid, entry in sorted(stored.items(), key=lambda kv: kv[1]["id"]):
        problems = [t["error"] for t in entry["tables"] if t["error"]] + entry["skipped"]
        if problems:
            print(f"  {entry['id']}: {entry['status']}: {problems[0][:160]}")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    refs = sub.add_parser("references", help="fetch reference tables")
    refs.add_argument("--for", dest="for_", required=True,
                      help=f"'{HORIZON}' (as of each draft-5 run) or a Sonnet run id")
    refs.add_argument("--uids", help="file of uids to limit to")
    refs.add_argument("--refetch", action="store_true", help="fetch stored ones again")
    refs.set_defaults(func=cmd_references)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
