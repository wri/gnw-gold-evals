---
name: plain-baseline
description: Use when running or rescoring the plain baseline, which is plain Sonnet with web search set against Horizon on BENCHMARK draft-5 ("plain Sonnet baseline", "rescore the plain run", "compare Horizon with Sonnet + web", "plain_baseline report"). Stops before every step that spends API budget. Not for BENCHMARK runs.
---

# plain-baseline: plain Sonnet + web against Horizon

`tools/plain_baseline.py` asks plain Sonnet 5.5 with web search the
BENCHMARK `2026-draft-5` questions that judge a reply, scores only the
reply, and compares it with Horizon's stored draft-5 attempts. It never
writes to `results/benchmark/`, so the frontend cannot pick it up.
[results/plain/README.md](../../../results/plain/README.md) owns the
procedure; this skill follows it. Terms are defined in
[docs/glossary.md](../../../docs/glossary.md).

## Before you start

- **Artifacts.** `references` and `score`, for either side, read the
  draft-5 runs' artifacts in `results/benchmark/artifacts/`, which are
  gitignored. Check that the five run directories named in
  `results/benchmark/pages/20261028T124051Z_prod.json` (`run.sources`) are
  there. Without them nothing fails: Horizon's attempts read as no reply,
  and the scores are wrong. Work in the checkout that ran draft-5, or copy or
  link those directories in.
- **Draft-5 must not have changed.** If a draft-5 member was revised since
  28 October, the Horizon steps stop with "questions are not on the draft-5
  page", and steps that read the overlay stop with "uids are not draft-5
  members". Stop and ask the repo owner what to compare against.
- **Tokens** (the tool loads `.env`): `ANTHROPIC_API_KEY` for `ask` and for
  the judge in `score`; `ANALYTICS_API_TOKEN` or `PROD_API_TOKEN` for
  `references`.
- **Pilot or full run.** A pilot uses a uid file on every step; a full run
  uses none, and `--trials 3` (the committed full run's setting; the
  default is 1). Never mix: a step without `--uids` works on all 253
  questions.
- Pick a run id for the Sonnet run: the date and a purpose, for example
  `20261117-pilot`.

## Steps, in order

`U` below is `--uids <file>` for a pilot and nothing for a full run; `T`
is `--trials 3` for a full run and nothing for a pilot.

1. **Pilot only: sample.** `uv run python tools/plain_baseline.py sample --n 40`
   writes `results/plain/pilot-uids-seed30.txt` (42 questions: `--n` is a
   target).
2. **Horizon reference tables** (the analytics API, no budget):
   `uv run python tools/plain_baseline.py references --for horizon-draft5 U`
   (`--refetch` fetches stored ones again).
3. **Project the cost, which is free:**
   `uv run python tools/plain_baseline.py ask --run <id> U T --max-cost-usd <N> --dry-run`.
   It projects $0.28 a question (about $71 a trial for all 253); the
   committed full run spent about half that, $105.10 for 3 trials.
4. **STOP. Ask the user for a go-ahead.** Show the projection and the cap.
   The next command spends API budget. Do not run it without a clear yes.
   The cap counts everything the run id has already spent, so a resumed run
   needs a cap above that total.
5. **Ask** (spends money; the run starts no new attempt once the cap is
   spent):
   `uv run python tools/plain_baseline.py ask --run <id> U T --max-cost-usd <N>`.
   A killed run resumes by running the same command again, in the same
   checkout: stored answers are not asked twice.
6. **Sonnet reference tables:** `... references --for <id> U`.
7. **STOP before scoring.** `score` makes paid Haiku judge calls: say so.
   Then score both sides (run `references` first or `score` stops):
   `... score --for horizon-draft5 U` and `... score --for <id> U`.
8. **Rescore some questions:** `... score --for <id> --uids <file> --merge`.
   `--merge` keeps the stored scores of every question not rescored. Without
   it the file holds only the rescored questions.
9. **After an overlay change:** `... outcomes --for horizon-draft5` and
   `... outcomes --for <id>` re-apply it to the stored scores. No API calls.
10. **Report:** `... report --sonnet <id>` writes
    `results/plain/reports/<id>.md` and `.json`. No API calls.

## Files in `results/plain/`

| path | role |
|---|---|
| `runs/<id>.json` | Sonnet's attempts (reply, cost, searches) |
| `artifacts/<id>/` | raw answers, gitignored |
| `references/<for>.json` | reference tables the figures are judged against |
| `scores/<for>.json` | scored attempts and outcomes, for `horizon-draft5` or a run id |
| `reports/<id>.md`, `.json` | the comparison |
| `pilot-uids-seed30.txt` | the 42 pilot questions |
| `estimate-uids.txt` | 10 pilot questions once used for a cost estimate; no step reads it |

## Guardrails

- Never hand-edit these files. Rescore with `--merge` or rerun the step.
- Commit runs, references, scores and reports by file name. Show the user
  what will be committed first.
