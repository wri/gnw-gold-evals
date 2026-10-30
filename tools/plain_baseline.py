"""Plain baseline: Sonnet + web against Horizon on BENCHMARK draft-5, reply only.

    uv run python tools/plain_baseline.py sample --n 40               # pilot questions
    uv run python tools/plain_baseline.py references --for horizon-draft5
    uv run python tools/plain_baseline.py ask --run <id> --uids <file> --max-cost-usd 40
    uv run python tools/plain_baseline.py references --for <id>        # after the Sonnet run
    uv run python tools/plain_baseline.py score --for horizon-draft5 --uids <file>
    uv run python tools/plain_baseline.py score --for <id>
    uv run python tools/plain_baseline.py outcomes --for <id>          # overlay changed: no API
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
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from challenge_rollup import percentile  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from goldset.benchmark import load_benchmark  # noqa: E402
from goldset.cli import require_api_token, resolve_case  # noqa: E402
from goldset.evaluators import figures  # noqa: E402
from goldset.groundtruth import AnalyticsClient, datasets  # noqa: E402
from goldset.plain import horizon, outcome, overlay, reference, score, sonnet  # noqa: E402
from goldset.store import Case, load_store  # noqa: E402
from goldset.templates import has_templates  # noqa: E402

BENCHMARK = Path("benchmarks/2026-draft-5.json")
OVERLAY = Path("benchmarks/overlays/2026-draft-5.plain.json")
CASES = Path("cases/challenge")
OUT = Path("results/plain")
HORIZON = "horizon-draft5"
# September's mean cost a question for Sonnet + web (cached, basic tools).
SEPTEMBER_USD = 0.28
WORKERS = 4
# Judge calls are network-bound: scoring runs attempts, not questions, wide.
SCORE_WORKERS = 12
REFERENCE_POLLS = 60


def member_types() -> dict[str, str]:
    """Active draft-5 members (errata excluded) and their types."""
    return {m.uid: m.type for m in load_benchmark(BENCHMARK).active_members}


def members() -> dict[str, Case]:
    """The draft-5 questions that judge a reply: 253 of the 269."""
    uids = set(member_types())
    reply_judged = ("text", "figure", "figure_claim")
    return {c.uid: c for _, c, _ in load_store(CASES)
            if c.uid in uids and any(c.expected.get(k) for k in reply_judged)}


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


def _overlay() -> tuple[dict[str, Any], dict[str, overlay.Calls]]:
    if not OVERLAY.exists():
        return {"status": "missing"}, {}
    return overlay.load(OVERLAY, set(member_types()))


def _side(name: str, cases: dict[str, Case]
          ) -> tuple[dict[str, datetime], dict[str, list[score.Attempt]]]:
    """One assistant's attempts, and the moment each question's dates
    resolve to: when it was asked."""
    if name == HORIZON:
        loaded = horizon.load(set(cases))
        return ({uid: _when(started) for uid, (started, _) in loaded.items()},
                {uid: attempts for uid, (_, attempts) in loaded.items()})
    run = _read(OUT / "runs" / f"{name}.json")
    attempts: dict[str, list[score.Attempt]] = {}
    for record in sorted(run["attempts"].values(), key=lambda a: a["trial"]):
        if record["uid"] in cases:
            attempts.setdefault(record["uid"], []).append(score.Attempt(
                record["reply"],
                error="turn left unfinished" if record.get("incomplete") else ""))
    return dict.fromkeys(cases, _when(run["started"])), attempts


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
        "rolling window": [u for u in cases
                           if any(has_templates(v) for v in cases[u].expected.values())],
    }
    chosen: set[str] = set()
    for pool in special.values():
        chosen.update(rng.sample(sorted(pool), min(2, len(pool))))
    for kind, pool in sorted(by_type.items()):
        share = max(2, round(args.n * len(pool) / len(cases)))
        have = sum(1 for u in chosen if types[u] == kind)
        rest = [u for u in pool if u not in chosen]
        chosen.update(rng.sample(rest, max(0, min(len(rest), share - have))))
    path = OUT / f"pilot-uids-seed{args.seed}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(chosen, key=lambda u: cases[u].id)) + "\n")
    tally = Counter(types[u] for u in chosen)
    print(f"wrote {path}: {len(chosen)} questions {dict(sorted(tally.items()))}")
    return 0


# -------------------------------------------------------------- references


def cmd_references(args: argparse.Namespace) -> int:
    cases = {uid: c for uid, c in _limit(members(), args.uids).items()
             if c.expected.get("figure")}
    _, calls = _overlay()
    known, _ = horizon.known_areas()
    when, _ = _side(args.for_, cases)
    path = OUT / "references" / f"{args.for_}.json"
    stored = _read(path)["questions"] if path.exists() else {}
    todo: dict[str, reference.Reference] = {}
    for uid, case in cases.items():
        if uid in stored and stored[uid]["status"] == "ok" and not args.refetch:
            continue
        pinned = dict(calls[uid].areas) if uid in calls else None
        todo[uid] = reference.plan(resolve_case(case, when[uid]),
                                   when[uid].strftime("%Y-%m-%d"), known, pinned)
    token = os.environ.get("ANALYTICS_API_TOKEN") or require_api_token("prod")
    if not token:
        return 2
    print(f"fetching {sum(len(r.tables) for r in todo.values())} tables "
          f"for {len(todo)} questions")
    # Alert jobs over large or new windows compute for minutes: poll longer.
    reference.fetch(list(todo.values()), AnalyticsClient(token, max_polls=REFERENCE_POLLS))
    stored.update({uid: ref.to_json() for uid, ref in todo.items()})
    _write(path, {"for": args.for_, "written": datetime.now(UTC).isoformat(timespec="seconds"),
                  "questions": stored})
    print(f"wrote {path}: {dict(Counter(e['status'] for e in stored.values()))}")
    for entry in sorted(stored.values(), key=lambda e: e["id"]):
        problems = [t["error"] for t in entry["tables"] if t["error"]] + entry["skipped"]
        if problems:
            print(f"  {entry['id']}: {entry['status']}: {problems[0][:160]}")
    return 0


# --------------------------------------------------------------------- ask


def _attempt_record(uid: str, trial: int, answer: dict[str, Any]) -> dict[str, Any]:
    usage = answer["usage"]
    return {"uid": uid, "trial": trial, "reply": answer["reply"], "stopped": answer["stopped"],
            "incomplete": answer.get("incomplete", False),
            "cost_usd": usage["cost_usd"], "searches": usage["searches"],
            "fetches": usage["fetches"], "wall_s": usage["wall_s"]}


def cmd_ask(args: argparse.Namespace) -> int:
    cases = _limit(members(), args.uids)
    planned = len(cases) * args.trials
    print(f"{planned} attempts; at September's ${SEPTEMBER_USD}/question about "
          f"${planned * SEPTEMBER_USD:.0f}; stops at ${args.max_cost_usd:.2f}")
    if args.dry_run:
        return 0
    run_path = OUT / "runs" / f"{args.run}.json"
    run = _read(run_path) if run_path.exists() else {
        "run_id": args.run, "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "assistant": "sonnet+web", "benchmark": str(BENCHMARK), "trials": args.trials,
        "web_tools": args.web_tools, "attempts": {},
    }
    asked_at = _when(run["started"])
    raw = OUT / "artifacts" / args.run
    raw.mkdir(parents=True, exist_ok=True)
    # Answers already paid for (a killed run) are read back, never re-asked.
    for path in raw.glob("*_t*.json"):
        key = path.stem
        if key not in run["attempts"]:
            uid, trial = key.rsplit("_t", 1)
            run["attempts"][key] = _attempt_record(uid, int(trial), _read(path))
    spend = sonnet.Spend(args.max_cost_usd)
    # Superseded answers (asked again after a transport fix) were still paid for.
    spend.add(sum(a["cost_usd"] for a in [*run["attempts"].values(), *run.get("superseded", [])]))
    jobs = [(uid, t) for uid in sorted(cases) for t in range(1, args.trials + 1)
            if f"{uid}_t{t}" not in run["attempts"]]

    def one(job: tuple[str, int]) -> dict[str, Any] | None:
        uid, trial = job
        if spend.exhausted():
            return None
        query = resolve_case(cases[uid], asked_at).query
        answer = sonnet.ask(query, asked_at.strftime("%Y-%m-%d"), args.web_tools)
        spend.add(answer["usage"]["cost_usd"])
        _write(raw / f"{uid}_t{trial}.json", answer)
        return _attempt_record(uid, trial, answer)

    not_started = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(one, j) for j in jobs]):
            record = future.result()
            if record is None:
                not_started += 1
                continue
            run["attempts"][f"{record['uid']}_t{record['trial']}"] = record
            _write(run_path, run)
    run["spent_usd"] = round(spend.spent, 4)
    _write(run_path, run)
    print(f"wrote {run_path}: {len(run['attempts'])} attempts, ${run['spent_usd']:.2f}"
          + (f"; {not_started} not started (spend limit)" if not_started else ""))
    return 0


# ------------------------------------------------------------------- score


def _outcomes(questions: dict[str, Any], calls: dict[str, overlay.Calls]) -> None:
    """Each question's outcome from its stored attempts: no judge calls, so
    an overlay change costs nothing to apply."""
    for uid, entry in questions.items():
        entry.update(outcome.question(entry["attempts"], calls.get(uid, overlay.Calls())))


def cmd_score(args: argparse.Namespace) -> int:
    cases = _limit(members(), args.uids)
    header, calls = _overlay()
    refs_path = OUT / "references" / f"{args.for_}.json"
    refs = _read(refs_path)["questions"] if refs_path.exists() else {}
    missing_refs = [c.id for u, c in cases.items() if c.expected.get("figure") and u not in refs]
    if missing_refs:
        raise SystemExit(f"{len(missing_refs)} figure questions have no reference in "
                         f"{refs_path}; run references --for {args.for_} first")
    when, attempts = _side(args.for_, cases)
    _, area_names = horizon.known_areas()
    names = {**{score.offer_key(d.dataset_id): d.name for d in datasets().values()},
             **area_names}
    links = {uid: reference.links(refs[uid]) for uid in cases if uid in refs}
    resolved = {uid: resolve_case(case, when[uid]) for uid, case in cases.items()}
    offers = {uid: score.offer_options(case, names) for uid, case in resolved.items()}
    jobs = [(uid, i, a) for uid in sorted(cases) for i, a in enumerate(attempts.get(uid, []))]

    with concurrent.futures.ThreadPoolExecutor(max_workers=SCORE_WORKERS) as pool:
        # Each table once, before the attempts that share it ask for it at once.
        list(pool.map(figures._fetch, {link for ls in links.values() for link in ls}))
        scored = list(pool.map(
            lambda job: score.score_one(resolved[job[0]], job[2], links.get(job[0], []),
                                        offers[job[0]]), jobs))

    questions: dict[str, Any] = {
        uid: {"id": case.id, "reference": refs.get(uid, {}).get("status", "n/a"),
              "attempts": [None] * len(attempts.get(uid, []))}
        for uid, case in cases.items()
    }
    for (uid, i, _), result in zip(jobs, scored, strict=True):
        questions[uid]["attempts"][i] = result
    _outcomes(questions, calls)
    path = OUT / "scores" / f"{args.for_}.json"
    _write(path, {"for": args.for_, "scored": datetime.now(UTC).isoformat(timespec="seconds"),
                  "overlay": header, "questions": questions})
    print(f"wrote {path}: {outcome.summarise(questions.values())}")
    return 0


def cmd_outcomes(args: argparse.Namespace) -> int:
    path = OUT / "scores" / f"{args.for_}.json"
    stored = _read(path)
    header, calls = _overlay()
    _outcomes(stored["questions"], calls)
    stored["overlay"] = header
    _write(path, stored)
    print(f"wrote {path}: {outcome.summarise(stored['questions'].values())}")
    return 0


# ------------------------------------------------------------------ report


def _spread(values: list[float]) -> str:
    if not values:
        return "n/a"
    return (f"median {statistics.median(values):g}, p90 {percentile(values, 90):g}, "
            f"max {max(values):g}")


def _compare(sides: dict[str, dict[str, Any]], uids: list[str]) -> dict[str, Any]:
    """Both assistants' summaries over ``uids``, with the paired gaps."""
    summaries = {name: outcome.summarise(q[u] for u in uids) for name, q in sides.items()}
    right = {n: {u: q[u]["outcome"] == "right" for u in uids} for n, q in sides.items()}
    wrong_figure = {n: {u: q[u]["wrong_figure"] for u in uids} for n, q in sides.items()}
    return {
        "questions": len(uids),
        "summaries": summaries,
        "gaps": {
            "right": outcome.paired_gap(right["Horizon"], right["Sonnet + web"], uids),
            "wrong_figure": outcome.paired_gap(wrong_figure["Sonnet + web"],
                                               wrong_figure["Horizon"], uids),
        },
    }


def _table(comparison: dict[str, Any]) -> list[str]:
    lines = ["| | Right | Wrong | Declined | Uncovered | Wrong figure | BENCHMARK-style |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, s in comparison["summaries"].items():
        r = s["rates"]
        lines.append(f"| {name} | {r['right']:.1%} | {r['wrong']:.1%} | {r['declined']:.1%} | "
                     f"{r['uncovered']:.1%} | {s['wrong_figure_rate']:.1%} | "
                     f"{s['benchmark_style_rate']:.1%} |")
    gaps = comparison["gaps"]
    lines += [
        "",
        f"Right, Horizon minus Sonnet: {gaps['right']['gap']:+.1%} "
        f"(95% interval {gaps['right']['low']:+.1%} to {gaps['right']['high']:+.1%}). "
        f"Wrong figure, Sonnet minus Horizon: {gaps['wrong_figure']['gap']:+.1%} "
        f"(95% interval {gaps['wrong_figure']['low']:+.1%} to {gaps['wrong_figure']['high']:+.1%}).",
    ]
    return lines


def cmd_report(args: argparse.Namespace) -> int:
    scores = {"Horizon": _read(OUT / "scores" / f"{HORIZON}.json"),
              "Sonnet + web": _read(OUT / "scores" / f"{args.sonnet}.json")}
    sides = {name: s["questions"] for name, s in scores.items()}
    common = sorted(set(sides["Horizon"]) & set(sides["Sonnet + web"]))
    cases = members()
    types = member_types()
    # Alert figures Horizon did not fetch with the reference's own request
    # were computed after its reply, so later alerts may have moved them;
    # that can only count against Horizon, so the result is also given
    # without them (plan doc, Comparability).
    drift = [u for u in common
             if "11" in cases[u].expected.get("dataset_id", "").replace("|", ";").split(";")
             and cases[u].expected.get("figure")
             and not any(a.get("pulled_reference") for a in sides["Horizon"][u]["attempts"])]
    report = {
        "sonnet": args.sonnet,
        "all": _compare(sides, common),
        "without_alert_drift": _compare(sides, [u for u in common if u not in drift]),
        "alert_drift_flagged": sorted(cases[u].id for u in drift),
        "by_type": {kind: _compare(sides, [u for u in common if types[u] == kind])
                    for kind in sorted({types[u] for u in common})},
    }
    run = _read(OUT / "runs" / f"{args.sonnet}.json")
    attempts = list(run["attempts"].values())
    statuses = {name: s["overlay"].get("status", "missing") for name, s in scores.items()}
    lines = [
        f"# Plain baseline: Horizon against Sonnet + web ({args.sonnet})", "",
        f"{len(common)} questions. Overlay as scored: {statuses}.", "",
        *_table(report["all"]),
        "",
        f"## Without the {len(drift)} alert questions later alerts could have moved", "",
        *_table(report["without_alert_drift"]),
        "",
        "## By question type", "",
        "| Type | Questions | Horizon right | Sonnet right | Sonnet wrong figure |",
        "| --- | --- | --- | --- | --- |",
    ]
    for kind, c in report["by_type"].items():
        h, so = c["summaries"]["Horizon"], c["summaries"]["Sonnet + web"]
        lines.append(f"| {kind} | {c['questions']} | {h['rates']['right']:.0%} | "
                     f"{so['rates']['right']:.0%} | {so['wrong_figure_rate']:.0%} |")
    lines += [
        "",
        f"Sonnet cost an attempt: {_spread([a['cost_usd'] for a in attempts])} (USD); "
        f"searches {_spread([a['searches'] for a in attempts])}; "
        f"fetches {_spread([a['fetches'] for a in attempts])}; "
        f"stopped at the $1 limit: {sum(a['stopped'] for a in attempts)}; "
        f"unfinished turns: {sum(a.get('incomplete', False) for a in attempts)}; "
        f"spent ${run.get('spent_usd', 0):.2f} in all.",
    ]
    path = OUT / "reports" / f"{args.sonnet}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write(path.with_suffix(".json"), report)
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
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("outcomes", help="re-apply the overlay to stored scores (no API calls)")
    p.add_argument("--for", dest="for_", required=True, help=f"'{HORIZON}' or a Sonnet run id")
    p.set_defaults(func=cmd_outcomes)

    p = sub.add_parser("report", help="compare the two scored assistants")
    p.add_argument("--sonnet", required=True, help="the Sonnet run id")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
