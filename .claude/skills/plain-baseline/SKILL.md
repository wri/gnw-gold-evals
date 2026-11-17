---
name: plain-baseline
description: Use when running or rescoring the plain baseline, which is plain Sonnet with web search set against Horizon on BENCHMARK draft-5 ("plain Sonnet baseline", "rescore the plain run", "compare Horizon with Sonnet + web", "plain_baseline report"). Stops before the step that spends API budget. Not for BENCHMARK runs.
---

# plain-baseline: plain Sonnet + web against Horizon

`tools/plain_baseline.py` asks plain Sonnet 5.5 with web search the
BENCHMARK `2026-draft-5` questions that judge a reply, scores only the
reply, and compares it with Horizon's stored draft-5 attempts. Everything is
fixed to draft-5: the manifest, `cases/challenge` and the overlay
`benchmarks/overlays/2026-draft-5.plain.json` are constants in the tool. It
never writes to `results/benchmark/`, so the frontend cannot pick it up.
Tool docs: [tools/README.md](../../../tools/README.md). Terms are in the
[README glossary](../../../README.md#glossary).

## Before you start

- Horizon's side is read from `results/benchmark/artifacts/`, which is
  gitignored. Work on the machine that ran draft-5, or the Horizon steps fail.
- Tokens (the CLI loads `.env`): `ANTHROPIC_API_KEY` for `ask` and for the
  judge in `score`; `ANALYTICS_API_TOKEN` or `PROD_API_TOKEN` for `references`.
- Pick a run id for the Sonnet run, for example `20261103-pilot`.

## Steps, in order

1. **Sample a pilot (optional).** `uv run python tools/plain_baseline.py sample --n 40`
   writes `results/plain/pilot-uids-seed<seed>.txt`. Skip it for a full run.
2. **Horizon reference tables:**
   `uv run python tools/plain_baseline.py references --for horizon-draft5`
   (add `--uids <file>` to limit; `--refetch` fetches stored ones again).
3. **Project the cost, which is free:**
   `uv run python tools/plain_baseline.py ask --run <id> --uids <file> --max-cost-usd <N> --dry-run`
4. **STOP. Ask the user for a go-ahead.** Show the projection and the cap.
   The next command spends API budget. Do not run it without a clear yes.
5. **Ask** (spends money; the run stops at the cap):
   `uv run python tools/plain_baseline.py ask --run <id> --uids <file> --max-cost-usd <N>`
   Leave out `--uids` for every question. `--trials` defaults to 1. A killed
   run resumes by running the same command again: stored answers are not asked twice.
6. **Sonnet reference tables:** `... references --for <id>`
7. **Score both sides** (judge calls; run `references` first or `score` stops):
   `... score --for horizon-draft5 --uids <file>` and `... score --for <id>`
8. **Rescore some questions:** `... score --for <id> --uids <file> --merge`.
   `--merge` keeps the stored scores of every question not rescored. Without
   it the file holds only the rescored questions.
9. **After an overlay change:** `... outcomes --for <id>` re-applies it to the
   stored scores. No API calls.
10. **Report:** `... report --sonnet <id>` writes `results/plain/reports/<id>.md`
    and `.json`.

## Files in `results/plain/`

| path | role |
|---|---|
| `runs/<id>.json` | Sonnet's attempts (reply, cost, searches) |
| `artifacts/<id>/` | raw answers, gitignored |
| `references/<for>.json` | reference tables the figures are judged against |
| `scores/<for>.json` | scored attempts and outcomes, for `horizon-draft5` or a run id |
| `reports/<id>.md`, `.json` | the comparison |
| `*-uids*.txt` | lists of question uids passed to `--uids` |

## Guardrails

- Never hand-edit these files. Rescore with `--merge` or rerun the step.
- Commit runs, references, scores and reports by file name. Show the user
  what will be committed first.
