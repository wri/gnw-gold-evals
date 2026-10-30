"""Plain baseline: Sonnet + web against Horizon on BENCHMARK draft-5, reply only.

    uv run python tools/plain_baseline.py sample --n 40               # pilot questions
    uv run python tools/plain_baseline.py references --for horizon-draft5
    uv run python tools/plain_baseline.py ask --run <id> --uids <file> --max-cost-usd 40
    uv run python tools/plain_baseline.py references --for <id>        # after the Sonnet run
    uv run python tools/plain_baseline.py score --for horizon-draft5 --uids <file>
    uv run python tools/plain_baseline.py score --for <id>
    uv run python tools/plain_baseline.py report --sonnet <id>

Plan of record: the "Plain Sonnet on BENCHMARK" doc (AJ, 2026-10-30). Output
lives under ``results/plain/``; nothing here writes to ``results/benchmark/``,
so the FE scorecards page can never pick it up. ``ask`` spends API budget:
run it only with AJ's go-ahead.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402

from goldset.benchmark import load_benchmark  # noqa: E402
from goldset.cli import resolve_case  # noqa: E402
from goldset.groundtruth import AnalyticsClient, datasets  # noqa: E402
from goldset.plain import horizon, outcome, overlay, reference, score, sonnet  # noqa: E402
from goldset.store import Case, load_store  # noqa: E402

BENCHMARK = Path("benchmarks/2026-draft-5.json")
OVERLAY = Path("benchmarks/2026-draft-5.plain-overlay.json")
CASES = Path("cases/challenge")
OUT = Path("results/plain")
HORIZON = "horizon-draft5"
# September's mean cost a question for Sonnet + web (cached, basic tools).
SEPTEMBER_USD = 0.28
WORKERS = 4


def members() -> dict[str, Case]:
    """The draft-5 questions that judge a reply: 253 of the 269."""
    bench = load_benchmark(BENCHMARK)
    uids = {m.uid for m in bench.members}
    cases = {c.uid: c for _, c, _ in load_store(CASES) if c.uid in uids}
    reply_judged = ("text", "figure", "figure_claim")
    return {uid: c for uid, c in cases.items()
            if any(c.expected.get(k) for k in reply_judged)}


def member_types() -> dict[str, str]:
    return {m.uid: m.type for m in load_benchmark(BENCHMARK).members}


def _when(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _limit(cases: dict[str, Case], uids_file: str | None) -> dict[str, Case]:
    if not uids_file:
        return cases
    wanted = set(Path(uids_file).read_text().split())
    unknown = wanted - set(cases)
    if unknown:
        raise SystemExit(f"{len(unknown)} uids in {uids_file} are not reply-judged members")
    return {uid: c for uid, c in cases.items() if uid in wanted}


def _calls(cases: dict[str, Case]) -> tuple[dict[str, Any], dict[str, overlay.Calls]]:
    if not OVERLAY.exists():
        return {"status": "missing"}, {}
    return overlay.load(OVERLAY, set(member_types()))


def _when_replied(name: str, cases: dict[str, Case]) -> dict[str, datetime]:
    """The moment each question's dates resolve to: when it was asked."""
    if name == HORIZON:
        return {uid: _when(q.started) for uid, q in horizon.load(set(cases)).items()}
    started = _when(_read(OUT / "runs" / f"{name}.json")["started"])
    return dict.fromkeys(cases, started)


# ------------------------------------------------------------------ sample


def cmd_sample(args: argparse.Namespace) -> int:
    """Pilot questions: spread over the types in proportion, with at least
    two of each, and every kind the method treats specially represented."""
    cases = members()
    types = member_types()
    rng = random.Random(args.seed)
    by_type: dict[str, list[str]] = {}
    for uid in sorted(cases):
        by_type.setdefault(types[uid], []).append(uid)
    special = {
        "accepted offer": [u for u in cases if cases[u].expected.get("accept_nudge_offering")
                           or cases[u].expected.get("accept_aoi_nudge_offering")],
        "two datasets": [u for u in cases if ";" in cases[u].expected.get("dataset_id", "")],
        "rolling window": [u for u in cases if "{" in json.dumps(cases[u].expected)],
    }
    chosen: set[str] = set()
    for pool in special.values():
        chosen.update(rng.sample(sorted(pool), min(2, len(pool))))
    for kind, pool in sorted(by_type.items()):
        share = max(2, round(args.n * len(pool) / len(cases)))
        have = [u for u in chosen if types[u] == kind]
        rest = [u for u in pool if u not in chosen]
        chosen.update(rng.sample(rest, max(0, min(len(rest), share - len(have)))))
    path = OUT / f"pilot-uids-seed{args.seed}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(chosen, key=lambda u: cases[u].id)) + "\n")
    tally: dict[str, int] = {}
    for uid in chosen:
        tally[types[uid]] = tally.get(types[uid], 0) + 1
    print(f"wrote {path}: {len(chosen)} questions {dict(sorted(tally.items()))}")
    return 0


# -------------------------------------------------------------- references


def cmd_references(args: argparse.Namespace) -> int:
    cases = {uid: c for uid, c in _limit(members(), args.uids).items()
             if c.expected.get("figure")}
    _, calls = _calls(cases)
    known, _ = horizon.known_area_sources()
    when = _when_replied(args.for_, cases)
    path = OUT / "references" / f"{args.for_}.json"
    stored = _read(path)["questions"] if path.exists() else {}
    todo = []
    for uid, case in cases.items():
        if uid in stored and stored[uid]["status"] == "ok" and not args.refetch:
            continue
        now = when[uid]
        pinned = dict(calls[uid].areas) if uid in calls else None
        todo.append(reference.plan(resolve_case(case, now), now.strftime("%Y-%m-%d"),
                                   known, pinned))
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
    for entry in sorted(stored.values(), key=lambda e: e["id"]):
        problems = [t["error"] for t in entry["tables"] if t["error"]] + entry["skipped"]
        if problems:
            print(f"  {entry['id']}: {entry['status']}: {problems[0][:160]}")
    return 0


# --------------------------------------------------------------------- ask


def cmd_ask(args: argparse.Namespace) -> int:
    cases = _limit(members(), args.uids)
    planned = len(cases) * args.trials
    print(f"{planned} attempts; at September's ${SEPTEMBER_USD}/question about "
          f"${planned * SEPTEMBER_USD:.0f}; stops at ${args.max_cost_usd:.2f}")
    if args.dry_run:
        return 0
    run_path = OUT / "runs" / f"{args.run}.json"
    started = datetime.now(UTC)
    run = _read(run_path) if run_path.exists() else {
        "run_id": args.run, "started": started.isoformat(timespec="seconds"),
        "assistant": "sonnet+web", "benchmark": str(BENCHMARK), "trials": args.trials,
        "web_tools": args.web_tools, "attempts": {},
    }
    today = _when(run["started"]).strftime("%Y-%m-%d")
    spend = sonnet.Spend(args.max_cost_usd)
    raw = OUT / "artifacts" / args.run
    raw.mkdir(parents=True, exist_ok=True)
    jobs = [(uid, t) for uid in sorted(cases) for t in range(1, args.trials + 1)
            if f"{uid}_t{t}" not in run["attempts"]]

    def one(job: tuple[str, int]) -> tuple[str, dict[str, Any]] | None:
        uid, trial = job
        try:
            spend.check()
        except sonnet.CostCap:
            return None
        query = resolve_case(cases[uid], _when(run["started"])).query
        answer = sonnet.ask(query, today, args.web_tools)
        spend.add(answer["usage"]["cost_usd"])
        (raw / f"{uid}_t{trial}.json").write_text(json.dumps(answer, indent=1, default=str))
        usage = answer["usage"]
        return f"{uid}_t{trial}", {
            "uid": uid, "trial": trial, "reply": answer["reply"], "stopped": answer["stopped"],
            "cost_usd": usage["cost_usd"], "searches": usage["searches"],
            "fetches": usage["fetches"], "wall_s": usage["wall_s"],
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done in pool.map(one, jobs):
            if done:
                run["attempts"][done[0]] = done[1]
                _write(run_path, run)
    run["spent_usd"] = round(sum(a["cost_usd"] for a in run["attempts"].values()), 4)
    _write(run_path, run)
    skipped = len(jobs) - sum(1 for j in jobs if f"{j[0]}_t{j[1]}" in run["attempts"])
    print(f"wrote {run_path}: {len(run['attempts'])} attempts, ${run['spent_usd']:.2f}"
          + (f"; {skipped} not started (spend limit)" if skipped else ""))
    return 0


# ------------------------------------------------------------------- score


def _attempts(name: str, cases: dict[str, Case]) -> dict[str, list[dict[str, Any]]]:
    """Each question's attempts as text the user reads, plus what scoring
    needs beyond it (Horizon's nudge and own pulls)."""
    if name == HORIZON:
        return {uid: [{"text": "" if a.no_answer else score.as_read(a.reply, a.nudge),
                       "nudge": a.nudge, "pulled": a.pulled_links}
                      for a in q.attempts]
                for uid, q in horizon.load(set(cases)).items()}
    run = _read(OUT / "runs" / f"{name}.json")
    out: dict[str, list[dict[str, Any]]] = {}
    for attempt in sorted(run["attempts"].values(), key=lambda a: a["trial"]):
        if attempt["uid"] in cases:
            out.setdefault(attempt["uid"], []).append(
                {"text": attempt["reply"], "nudge": None, "pulled": []})
    return out


def cmd_score(args: argparse.Namespace) -> int:
    cases = _limit(members(), args.uids)
    header, calls = _calls(cases)
    refs_path = OUT / "references" / f"{args.for_}.json"
    refs = _read(refs_path)["questions"] if refs_path.exists() else {}
    missing_refs = [c.id for u, c in cases.items() if c.expected.get("figure") and u not in refs]
    if missing_refs:
        raise SystemExit(f"{len(missing_refs)} figure questions have no reference in "
                         f"{refs_path}; run references --for {args.for_} first")
    when = _when_replied(args.for_, cases)
    attempts = _attempts(args.for_, cases)
    dataset_names = {d.dataset_id: d.name for d in datasets().values()}
    _, area_names = horizon.known_area_sources()

    def one(uid: str) -> tuple[str, dict[str, Any]]:
        case = resolve_case(cases[uid], when[uid])
        links = reference.Reference.from_json(uid, refs[uid]).links if uid in refs else []
        own = {reference.resource_id(link) for link in links}
        offers = score.offer_options(case, dataset_names, area_names)
        scored = []
        for attempt in attempts.get(uid, []):
            offer = (score.horizon_nudge_offer(case, attempt["nudge"], attempt["pulled"])
                     if attempt["nudge"] else None)
            result = score.score_attempt(case, attempt["text"], links,
                                         nudge_offer=offer, offers=offers)
            # Horizon asked exactly the reference request: the API served it
            # the same stored result, so its figure is judged on what it saw.
            result["pulled_reference"] = bool(
                own & {reference.resource_id(u) for u in attempt["pulled"]})
            scored.append(result)
        verdict = outcome.question(scored, calls.get(uid, overlay.Calls()))
        return uid, {"id": cases[uid].id, "attempts": scored,
                     "outcome": verdict.outcome, "benchmark": verdict.benchmark,
                     "wrong_figure": verdict.wrong_figure,
                     "reference": refs.get(uid, {}).get("status", "n/a")}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        questions = dict(pool.map(one, sorted(cases)))
    path = OUT / "scores" / f"{args.for_}.json"
    _write(path, {"for": args.for_, "scored": datetime.now(UTC).isoformat(timespec="seconds"),
                  "overlay": header, "questions": questions})
    results = {u: outcome.QuestionResult(q["outcome"], q["benchmark"], q["wrong_figure"], ())
               for u, q in questions.items()}
    print(f"wrote {path}: {outcome.summarise(results)}")
    return 0


# ------------------------------------------------------------------ report


def _results(name: str) -> dict[str, Any]:
    return _read(OUT / "scores" / f"{name}.json")["questions"]


def _spread(values: list[float]) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    return f"median {statistics.median(ordered):g}, p90 {p90:g}, max {ordered[-1]:g}"


def cmd_report(args: argparse.Namespace) -> int:
    sides = {"Horizon": _results(HORIZON), "Sonnet + web": _results(args.sonnet)}
    common = sorted(set(sides["Horizon"]) & set(sides["Sonnet + web"]))
    summaries = {
        name: outcome.summarise({u: outcome.QuestionResult(
            q[u]["outcome"], q[u]["benchmark"], q[u]["wrong_figure"], ()) for u in common})
        for name, q in sides.items()
    }
    right = {n: {u: q[u]["outcome"] == "right" for u in common} for n, q in sides.items()}
    wrong_fig = {n: {u: q[u]["wrong_figure"] for u in common} for n, q in sides.items()}
    gaps = {
        "right": outcome.paired_gap(right["Horizon"], right["Sonnet + web"], common),
        "wrong_figure": outcome.paired_gap(wrong_fig["Sonnet + web"], wrong_fig["Horizon"], common),
    }
    run = _read(OUT / "runs" / f"{args.sonnet}.json")
    costs = [a["cost_usd"] for a in run["attempts"].values()]
    searches = [a["searches"] for a in run["attempts"].values()]
    fetches = [a["fetches"] for a in run["attempts"].values()]
    stopped = sum(a["stopped"] for a in run["attempts"].values())
    lines = [
        f"# Plain baseline: Horizon against Sonnet + web ({args.sonnet})", "",
        f"{len(common)} questions. Overlay: {_read(OVERLAY).get('status', 'missing') if OVERLAY.exists() else 'missing'}.",
        "", "| | Right | Wrong | Declined | Uncovered | Wrong figure | BENCHMARK-style |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in summaries.items():
        r = s["rates"]
        lines.append(f"| {name} | {r['right']:.1%} | {r['wrong']:.1%} | {r['declined']:.1%} | "
                     f"{r['uncovered']:.1%} | {s['wrong_figure_rate']:.1%} | "
                     f"{s['benchmark_style_rate']:.1%} |")
    lines += [
        "",
        f"Right, Horizon minus Sonnet: {gaps['right']['gap']:+.1%} "
        f"(95% interval {gaps['right']['low']:+.1%} to {gaps['right']['high']:+.1%}).",
        f"Wrong figure, Sonnet minus Horizon: {gaps['wrong_figure']['gap']:+.1%} "
        f"(95% interval {gaps['wrong_figure']['low']:+.1%} to {gaps['wrong_figure']['high']:+.1%}).",
        "",
        f"Sonnet cost a question: {_spread(costs)} (USD); searches {_spread(searches)}; "
        f"fetches {_spread(fetches)}; stopped at the $1 limit: {stopped}; "
        f"spent ${sum(costs):.2f}.",
    ]
    path = OUT / "reports" / f"{args.sonnet}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write(path.with_suffix(".json"), {"sonnet": args.sonnet, "questions": len(common),
                                       "summaries": summaries, "gaps": gaps})
    print("\n".join(lines))
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="pick pilot questions")
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=30)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("references", help="fetch reference tables")
    p.add_argument("--for", dest="for_", required=True,
                   help=f"'{HORIZON}' (as of each draft-5 run) or a Sonnet run id")
    p.add_argument("--uids", help="file of uids to limit to")
    p.add_argument("--refetch", action="store_true", help="fetch stored ones again")
    p.set_defaults(func=cmd_references)

    p = sub.add_parser("ask", help="put questions to Sonnet + web (spends API budget)")
    p.add_argument("--run", required=True, help="run id, e.g. 20261103-pilot")
    p.add_argument("--uids", help="file of uids to limit to")
    p.add_argument("--trials", type=int, default=1)
    p.add_argument("--max-cost-usd", type=float, required=True)
    p.add_argument("--web-tools", choices=sorted(sonnet.WEB_TOOL_VERSIONS),
                   default=sonnet.DEFAULT_WEB_TOOLS)
    p.add_argument("--workers", type=int, default=WORKERS)
    p.add_argument("--dry-run", action="store_true", help="print the projection only")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("score", help="score one assistant's attempts (Haiku judge calls)")
    p.add_argument("--for", dest="for_", required=True, help=f"'{HORIZON}' or a Sonnet run id")
    p.add_argument("--uids", help="file of uids to limit to")
    p.add_argument("--workers", type=int, default=WORKERS)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("report", help="compare the two scored assistants")
    p.add_argument("--sonnet", required=True, help="the Sonnet run id")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
