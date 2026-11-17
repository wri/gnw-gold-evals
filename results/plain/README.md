# Plain baseline

The plain baseline asks a plain LLM, Sonnet 5.5 with web search, the
BENCHMARK `2026-draft-5` questions, and scores its replies the same way as
the agent's. It shows what a general assistant gets on the same exam. In
these files the agent is called Horizon, its name in the GNW app.
`tools/plain_baseline.py` runs every step, and `src/goldset/plain/` holds
the logic. The plan of record is the "Plain Sonnet on BENCHMARK" doc of
2026-10-30, a private claude.ai doc.

**Its results stay here.** Nothing writes them to `results/benchmark/`, so
the frontend scorecards page cannot show them.

## What is compared

- **Questions**: the 253 of draft-5's 269 active members that judge a reply
  (they expect `text`, `figure` or `figure_claim`).
- **Checks**: the four reply checks (expected text, answer period, figure,
  figure claim) through the harness's own evaluators, plus the
  accepted-nudge check where a fair choice is the right answer, and two
  Haiku judgements of the baseline's own (did the reply answer, decline or
  ask back; does a prose ask-back offer every accepted option). Figures are
  checked against reference tables fetched from the analytics API, because
  Sonnet pulls no data.
- **Horizon's side**: its stored draft-5 attempts, rescored the same way.
  The page `results/benchmark/pages/20261028T124051Z_prod.json` names the
  run each question's attempts came from.
- **Per-question calls**: `benchmarks/overlays/2026-draft-5.plain.json`,
  keyed by uid and reviewed by the repo owner (for example, a decline is
  the right answer, or a figure check is reported but does not gate). They
  live outside the case files because editing a member case gives it a new
  uid, which drops it from draft-5.
- **Outcomes**: each attempt is right, wrong, declined or uncovered. A
  question is right when most of its scored attempts are right (a tie
  fails); otherwise it is declined or wrong, whichever is commoner (a tie
  counts as wrong); it is uncovered when no attempt scored. The report also
  gives the stricter "right every time" and "wrong figure on any attempt",
  and a BENCHMARK-style verdict from the harness's own
  `buckets.row_verdict`.

**It is fixed to draft-5 as of 28 October.** The questions come from the
current `benchmarks/2026-draft-5.json`, but Horizon's attempts come from
the page above (`PAGE` in `src/goldset/plain/horizon.py`). If a draft-5
member is revised and the draft rebuilt, the steps that read Horizon's
attempts stop with "questions are not on the draft-5 page", and every step
that reads the overlay stops with "uids are not draft-5 members" until its
entry moves to the new uid. Pointing the baseline at a newer page is the
repo owner's decision.

## The raw artifacts it needs

`references` and `score`, for either side, read the draft-5 runs' raw
artifacts in `results/benchmark/artifacts/<run_id>/`: Horizon's replies,
and the areas Horizon picked, which tell each area id's source. These
directories are gitignored and exist only in the checkout that ran
draft-5. Run those steps there, or copy or link the five run directories
named in the page's `run.sources` into your checkout first. **Without them
nothing stops**: every Horizon attempt reads as no reply, and area sources
are unknown, so the scores are wrong. Do not prune them
([benchmarks/README.md](../../benchmarks/README.md), Raw artifacts).

## What each step calls

`.env` at the repo root is loaded.

| Step | Calls | Spends budget | Needs |
|---|---|---|---|
| `sample` | nothing | no | |
| `references` | the analytics API | no | `ANALYTICS_API_TOKEN`, else `PROD_API_TOKEN`, else `API_TOKEN`; the draft-5 artifacts |
| `ask` | the Anthropic Messages API: Sonnet with web search | **yes, the most** | `ANTHROPIC_API_KEY` |
| `score` | the Anthropic API (Haiku judge), and the reference tables' links | **yes** | `ANTHROPIC_API_KEY`; the draft-5 artifacts |
| `outcomes`, `report` | nothing | no | |

**Run `ask` only with the repo owner's go-ahead**, and say before running
`score` that it makes paid judge calls.

## Steps

A run is either a **pilot**, on a sample of questions with 1 attempt each,
or a **full run** on all 253. Pass the same `--uids <file>` to every step
of a pilot (`report` takes none), and none to any step of a full run. A
step without `--uids` works on all 253 questions: `references` would fetch
tables for questions Sonnet was never asked, and `score` would mark them
uncovered.

A full run, in order:

```bash
uv run python tools/plain_baseline.py references --for horizon-draft5                 # 1. tables for Horizon's replies
uv run python tools/plain_baseline.py ask --run <id> --trials 3 --max-cost-usd <N> --dry-run   # 2. projected cost, free
uv run python tools/plain_baseline.py ask --run <id> --trials 3 --max-cost-usd <N>   # 3. ask Sonnet (spends budget)
uv run python tools/plain_baseline.py references --for <id>                           # 4. tables for Sonnet's replies
uv run python tools/plain_baseline.py score --for horizon-draft5                      # 5. score Horizon (spends budget)
uv run python tools/plain_baseline.py score --for <id>                                # 6. score Sonnet (spends budget)
uv run python tools/plain_baseline.py report --sonnet <id>                            # 7. compare
```

A pilot draws its questions first, then runs the same steps with
`--uids` and without `--trials`:

```bash
uv run python tools/plain_baseline.py sample --n 40   # writes results/plain/pilot-uids-seed30.txt
uv run python tools/plain_baseline.py ask --run <id> --uids results/plain/pilot-uids-seed30.txt \
  --max-cost-usd <N> --dry-run
```

- **`--trials`** defaults to 1. The committed full run used 3, the same as
  Horizon's attempts per question.
- **Cost.** The dry run projects $0.28 a question, September's mean: 253
  questions come to about $71 a trial, or $213 for 3 trials. The committed
  full run spent $105.10 on 759 attempts, about $0.14 an attempt.
- **`--max-cost-usd`** is required. Set it to the amount agreed with the
  repo owner. When it is spent, the run starts no new attempts and stops
  partway. The cap counts everything already spent under that run id,
  including earlier invocations and answers asked again, so a resumed run
  does not get a fresh cap: raise it to continue. Each attempt also stops
  at $1, with at most 20 searches and 20 fetches.
- **Resuming.** A killed `ask` resumes when run again with the same
  `--run`: answers already paid for are read back from its artifacts in
  `results/plain/artifacts/<id>/`, never asked again. Those artifacts are
  gitignored, so resume in the same checkout.
- **Rescoring some questions**:
  `score --for <id> --uids <file> --merge` keeps the stored scores of every
  question not rescored. Without `--merge` the file holds only the rescored
  questions.
- **After an overlay change**: `outcomes --for horizon-draft5` and
  `outcomes --for <id>` re-apply it to the stored scores without API calls,
  then `report` again.

## The committed runs

| Run | Questions | Trials | Spent | Note |
|---|---|---|---|---|
| `20261030-pilot` | the 42 in `pilot-uids-seed30.txt` | 1 | $7.50 | |
| `20261030-full` | all 253 | 3 | $105.10 | trial 1 of the 42 pilot questions is reused from the pilot (the run's own `note`); the tool has no option for this |

`horizon-draft5` references and scores cover all 253 questions.

## Files

| Path | Holds | Written by |
|---|---|---|
| `runs/<id>.json` | one Sonnet run: its settings, every attempt (reply, cost, searches, fetches, time) and the total spend | `ask` |
| `artifacts/<id>/` | the raw answer of each attempt (gitignored); `ask` reads them back so a killed run pays for nothing twice | `ask` |
| `references/<for>.json` | the reference tables for each figure question, fetched as of the day of the reply | `references` |
| `scores/<for>.json` | each attempt's checks and each question's outcome, with the overlay as scored | `score`, `outcomes` |
| `reports/<id>.md`, `reports/<id>.json` | the comparison: overall, without alert questions whose figures later alerts could have moved, and per question type | `report` |
| `pilot-uids-seed30.txt` | the 42 pilot questions | `sample --n 40` with the default seed, 30 |
| `estimate-uids.txt` | 10 of the pilot questions, picked by hand on 2026-10-30 for a first cost estimate under a 10-search cap; that run is not committed and no step reads the file now | by hand |

`sample --n` is a target, not an exact count: every question type gets at
least two questions, and three special kinds (accepted offers, two
datasets, rolling windows) get two each, so `--n 40` draws 42.

## Naming

- A Sonnet run is named by `--run`: the date and a purpose, such as
  `20261030-pilot` and `20261030-full`. Its references, scores and report
  take the same name.
- Horizon's side is always `horizon-draft5` (`HORIZON` in the tool).
