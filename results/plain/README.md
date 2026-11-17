# Plain baseline

The plain baseline asks a plain LLM, Sonnet 5.5 with web search, the
BENCHMARK `2026-draft-5` questions, and scores its replies the same way as
the agent's. It shows what a general assistant gets on the same exam. In
these files the agent is called Horizon, its name in the GNW app. Plan of
record: the "Plain Sonnet on BENCHMARK" doc (AJ, 2026-10-30).
`tools/plain_baseline.py` runs every step, and `src/goldset/plain/` holds
the logic.

**Its results stay here.** Nothing writes them to `results/benchmark/`, so
the frontend scorecards page cannot show them.

## What is compared

- **Questions**: the 253 of draft-5's 269 active members that judge a reply
  (they expect `text`, `figure` or `figure_claim`).
- **Checks**: the four reply checks (expected text, answer period, figure,
  figure claim) through the harness's own evaluators, plus the
  accepted-nudge check where a fair choice is the right answer, and two
  new Haiku judgements (did the reply answer, decline or ask back; does a
  prose ask-back offer every accepted option). Figures are checked against
  reference tables fetched from the analytics API, because Sonnet pulls no
  data.
- **Horizon's side**: its stored draft-5 attempts, rescored the same way.
  The page `results/benchmark/pages/20261028T124051Z_prod.json` names the
  run each question's attempts came from. The replies and the areas Horizon
  picked come from those runs' artifacts (`results/benchmark/artifacts/`,
  gitignored), and `references` and `score` read them too, to learn
  each area's source. Run those steps on the machine that ran draft-5.
- **Per-question calls**: `benchmarks/overlays/2026-draft-5.plain.json`,
  keyed by uid and reviewed by AJ (for example, a decline is the right
  answer, or a figure check is reported but does not gate). They live
  outside the case files because editing a member case gives it a new uid,
  which drops it from draft-5. `outcomes` re-applies the overlay without
  API calls.
- **Outcomes**: each attempt is right, wrong, declined or uncovered. A
  question is right when most of its scored attempts are right (a tie
  fails); otherwise it is declined or wrong, whichever is commoner (a tie
  counts as wrong); it is uncovered when no attempt scored. The report
  also gives the stricter "right every time" and "wrong figure on any
  attempt", and a BENCHMARK-style verdict from the harness's own
  `buckets.row_verdict`.

## Steps

In order, from the tool's docstring:

```bash
uv run python tools/plain_baseline.py sample --n 40                  # 1. pilot questions
uv run python tools/plain_baseline.py references --for horizon-draft5 # 2. reference tables for Horizon's replies
uv run python tools/plain_baseline.py ask --run <id> --uids <file> --max-cost-usd 40   # 3. ask Sonnet (spends budget)
uv run python tools/plain_baseline.py references --for <id>           # 4. reference tables for Sonnet's replies
uv run python tools/plain_baseline.py score --for horizon-draft5 --uids <file>         # 5. score Horizon
uv run python tools/plain_baseline.py score --for <id>                # 6. score Sonnet
uv run python tools/plain_baseline.py report --sonnet <id>            # 7. compare
```

- **`ask` spends API budget: run it only with AJ's go-ahead.** Pass
  `--dry-run` first: it prints the projected cost and stops.
  `--max-cost-usd` is required, and the run stops starting new attempts
  once it is spent. Each question stops at $1, with at most 20 searches and
  20 fetches.
- A killed `ask` resumes when run again with the same `--run`: answers
  already paid for are read back from its artifacts, never asked again.
- To rescore some questions and keep the rest:
  `score --for <id> --uids <file> --merge`.
- After an overlay change: `outcomes --for <id>` (no API calls).
- `--uids <file>` limits a step to the uids in a file, one per line.

## Files

| Path | Holds | Written by |
|---|---|---|
| `runs/<id>.json` | One Sonnet run: its settings, every attempt (reply, cost, searches, fetches, time) and the total spend | `ask` |
| `artifacts/<id>/` | The raw answer of each attempt (gitignored). `ask` reads them back so a killed run pays for nothing twice | `ask` |
| `references/<for>.json` | The reference tables for each figure question, fetched as of the day of the reply | `references` |
| `scores/<for>.json` | Each attempt's checks and each question's outcome, with the overlay as scored | `score`, `outcomes` |
| `reports/<id>.md`, `reports/<id>.json` | The comparison of Horizon and Sonnet: overall, without alert questions whose figures later alerts could have moved, and per question type | `report` |
| `pilot-uids-seed30.txt` | The 42 pilot questions (`sample` with its default seed, 30) | `sample` |
| `estimate-uids.txt` | 10 of the pilot questions, picked for the cost estimate | by hand, 2026-10-30 |

## Naming

- A Sonnet run is named by `--run`: the date and a purpose, such as
  `20261030-pilot` and `20261030-full`. Its references, scores and report
  take the same name.
- Horizon's side is always `horizon-draft5` (`HORIZON` in the tool).

## Keys

`.env` at the repo root is loaded.

| Step | Needs |
|---|---|
| `ask` | `ANTHROPIC_API_KEY` (Sonnet through the Messages API) |
| `references` | `ANALYTICS_API_TOKEN`, else `PROD_API_TOKEN`, else `API_TOKEN` (the analytics API) |
| `score` | `ANTHROPIC_API_KEY` (the Haiku judge) |
| `sample`, `outcomes`, `report` | nothing |
