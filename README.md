# gnw-gold-evals

This repo measures how well the agent behind Global Nature Watch (GNW) answers questions. GNW is a World Resources Institute (WRI) product for asking about land and nature data, such as deforestation, land cover and carbon, for named places. The agent is Project Zeno, a large language model (LLM) agent built in [wri/project-zeno](https://github.com/wri/project-zeno). The GNW app calls it Horizon.

The repo holds the cases, the harness that sends them to the agent and scores the answers, and the committed results. It measures three things:

- **CHALLENGE** measures quality as pass rates per kind of question. Its cases are phrased the way users ask, and many of them are expected to fail today: a failure is data, not a defect.
- **BENCHMARK** is a fixed exam drawn from CHALLENGE, to show whether the agent gets better over time. Its runs give the North Star rate and the page data behind the AI accuracy scorecards page of the GNW frontend.
- **The plain baseline** asks a plain LLM with web search the same BENCHMARK questions and scores its replies, so the agent can be compared with a general assistant.

GOLD, the capability regression suite this repo was first built for, now lives in project-zeno under `evals/gold/`. The GOLD files here are a legacy copy until a later pull request deletes them: see [docs/gold-legacy.md](docs/gold-legacy.md).

## Suites at a glance

| Suite | Question it answers | Cases | Results | Owner doc |
|---|---|---|---|---|
| CHALLENGE | How well does the agent answer each kind of question? A pass rate per set and cohort, against targets | `cases/challenge/<set>/<cohort>/<id>.yaml` | `results/challenge/` | [cases/challenge/README.md](cases/challenge/README.md) |
| BENCHMARK | Is the agent getting better on a fixed exam? | `benchmarks/<version>.json`, a list of CHALLENGE case uids | `results/benchmark/` | [benchmarks/README.md](benchmarks/README.md) |
| Plain baseline | What does a plain LLM with web search get on the same questions? | the BENCHMARK `2026-draft-5` questions that judge a reply | `results/plain/` | [results/plain/README.md](results/plain/README.md) |
| GOLD (legacy copy) | Did an agent change break a capability that used to work? | `cases/v2/`, and `cases/v1/` frozen | `results/gold/` | [docs/gold-legacy.md](docs/gold-legacy.md) |

A BENCHMARK version is a list of uids, not a copy of the cases. The live version, `2026-draft-5`, is a draft. Freezing a version, so that its members never change, is the intended end state, but no version is frozen yet.

<a id="glossary"></a>
## Core concepts

Every other doc uses these terms. The [glossary](docs/glossary.md) defines the rest.

- **case**: one test in one YAML file: a user query, or a scripted conversation, and the values a correct answer must contain, such as the place ids, the dataset, the date range or a figure.
- **uid**: a 16-character hash of a case's query and expected values. Editing either gives the case a new uid, so an old score is never read as a score for new content. The case's `id`, such as `ch-aoi-001`, is its human name and stays the same.
- **store**: a directory of cases with its `MANIFEST.json`. `cases/challenge` holds CHALLENGE and every BENCHMARK member.
- **run**: one execution of a selection of cases against one environment: `prod`, `staging` or `local`.
- **trial**: one attempt at one case within a run, in a fresh conversation. `--trials 3` runs each case three times.
- **check**: one named score on one attempt, such as `aoi_id_match`: `1.0` (pass), `0.0` (fail) or `null` (not evaluated).
- **bucket**: the stage of the agent's work that a check speaks for: retrieval, analysis, explanation, output or scope. A failure then points at the stage that broke.
- **ledger**: a suite's committed run records, one JSON file per run under `results/<suite>/runs/`. Only the harness writes it.

### From case to score

Code paths are under `src/goldset/` unless they start with `tools/`.

| Step | What happens | Code |
|---|---|---|
| 1. Select | `evals run` loads the store and picks the cases: by suite, status, set or id, or a BENCHMARK version's members | `cli.py`, `suites.py`, `store.py`, `benchmark.py` |
| 2. Resolve | Date tokens such as `{current_year}` are filled in. The uid keeps the token | `templates.py` |
| 3. Ask | The harness sends the query to the agent with `POST /api/chat`, reads the stream to its end, then fetches the final state with `GET /api/threads/{id}/state` | `runner/api.py`, `runner/multiturn.py` |
| 4. Score | Each evaluator compares the final state with the case's `expected` values and returns checks | `adapter.py`, `registry.py`, `evaluators/` |
| 5. Verdict | Each attempt gets a verdict from its gating checks, and each case gets a row verdict from its attempts. Checks are tallied per bucket | `buckets.py` |
| 6. Record | The run record goes to `results/<suite>/runs/<run_id>.json`. Raw agent state goes to the gitignored `results/<suite>/artifacts/` | `ledger.py`, `runner/artifacts.py` |
| 7. Read | CHALLENGE: pass rates. BENCHMARK: the North Star and the page data | `tools/challenge_rollup.py`, `tools/benchmark_page.py` |

## Start here

Each job has one doc that owns it, and most have a Claude Code skill that walks it.

| Job | Owner doc | Skill |
|---|---|---|
| Run CHALLENGE and finish the run | [cases/challenge/README.md](cases/challenge/README.md) | `challenge-cases` |
| Run BENCHMARK and publish its page data | [benchmarks/README.md](benchmarks/README.md) | `benchmark-run` |
| Rerun only the BENCHMARK members revised since a run | [benchmarks/README.md, Rerunning revised members only](benchmarks/README.md#rerunning-revised-members-only) | `benchmark-run` |
| Add or edit a CHALLENGE case | [cases/README.md](cases/README.md) for the case file and the after-edit commands, then [cases/challenge/README.md](cases/challenge/README.md) | `challenge-cases`, `case-edit` |
| Run or rescore the plain baseline | [results/plain/README.md](results/plain/README.md) | `plain-baseline` |
| Refresh the dataset catalogue snapshot | [cases/README.md, The catalogue snapshot](cases/README.md#the-catalogue-snapshot) | `sync-catalog` |
| Read or change a check | [src/goldset/evaluators/README.md](src/goldset/evaluators/README.md) | |
| Read the ledger format or compare runs | [results/README.md](results/README.md) | |
| Find a tool | [tools/README.md](tools/README.md) | |
| Anything GOLD | project-zeno `evals/gold/`; for this copy, [docs/gold-legacy.md](docs/gold-legacy.md) | `gold-run`, `new-case`, `release-gate`, `triage-run` |
| Work here as an AI coding agent | [CLAUDE.md](CLAUDE.md) | |

<a id="setup"></a>
## Quick start

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                        # install, with the dev tools
uv run pytest -q                               # the tests; no network or secrets
uv run ruff check src tools tests generation   # lint, as CI runs it
uv run evals run --suite challenge --dry-run   # list the cases a run would send; no API calls
```

A live run needs two secrets, in your shell or in a gitignored `.env` file at the repo root:

- **An API token for the agent.** `STAGING_API_TOKEN` for `--env staging`, `PROD_API_TOKEN` for `--env prod`. When that variable is not set, the harness uses `API_TOKEN`, the only token `--env local` reads. So a stale environment-specific token in `.env` wins over a fresh `API_TOKEN`.
- **The judge's key.** `ANTHROPIC_API_KEY` for the default judge. `--judge-backend openrouter-jev-decisions` uses another judge model, TypeSafe JEV through OpenRouter, and needs `OPENROUTER_API_KEY` instead.

Cases with ground truth also call the analytics API, with `ANALYTICS_API_TOKEN` or else the API token. Only GOLD cases use ground truth today.

The Python package is called `goldset` for historical reasons. A rename would touch most files for no gain.

<a id="running-the-set"></a>
## Running a suite

`evals run` and `gold run` are the same command; `gold` is the older name. A run must name its suite, so that it never lands in the wrong ledger:

| Flag | Cases from | Results to |
|---|---|---|
| `--suite challenge` | `cases/challenge` | `results/challenge/` |
| `--benchmark benchmarks/<version>.json` | that version's members, in `cases/challenge` | `results/benchmark/` |
| `--suite gold` | `cases/v2` | `results/gold/` |

`--benchmark` implies `--suite benchmark`. `--cases-dir` and `--results-dir` override a suite's directories, but the harness refuses a store and a ledger of different suites.

**Which cases run.** `--suite challenge` leaves out `not doing` and `todo` cases, because `todo` cases are not pinned yet. `--suite gold` leaves out only `not doing`. `--status-exclude` changes this. A `--benchmark` run ignores status: the manifest names its members. Narrow any run with `--set`, `--group` or `--id`.

```bash
uv run evals run --suite challenge --set aoi --env staging --build "<label>"   # smoke run of one set
uv run evals run --suite challenge --id ch-aoi-001 --env staging --verbose     # one case; --id repeats
uv run evals run --help                                                        # every flag
```

**Tiers.** Choose the tier before you start.

- A **smoke run** has 1 trial, the default. It answers a quick question in minutes. It is never committed, compared or used as a baseline. `--env local` runs are smoke runs too, because a local stack matches neither staging nor prod.
- A **canonical run** has 3 trials and the default profile, and for CHALLENGE and BENCHMARK it runs on prod. Only canonical runs are published, trended or used as a baseline. A BENCHMARK run is canonical only when it also measured every active member of its version, and `results/index.json` flags it.

**Why 3 trials.** The agent is not deterministic. In GOLD, two trials of the same build with nothing changed differed by 18 to 29 spurious regressions. That is more than the 15 real regressions measured between two different builds, so a 1-trial comparison cannot tell a good build from a broken one. Comparing the three trials stored in `results/gold/runs/20260831T163347Z_prod.json` pairwise gives the same band.

**Profile.** Leave out `--ff` unless the cases under test need a feature still behind the `experimental` tool profile. The run records its `ff`, and the run_id ends with it: `20260831T163347Z_prod` against `20260831T155003Z_prod_experimental`.

**Comparable runs only.** Compare or trend two runs only when they share `ff`, trial count and environment. Profiles offer different tools, and environments usually run different agent builds, so a comparison across them measures the setup, not the agent. If no comparable run exists, say so. [results/README.md, Comparing two runs](results/README.md#comparing-two-runs) adds what else each suite needs to match.

**Labels and notes.** Give a run a meaningful `--build`, such as the agent build string or `post-fix-validation`, not the default `unknown`. If check semantics changed since the previous run, pass `--note "<what changed>"`, so the change is not read as agent movement.

**Killed runs.** A run appends each finished case to `results/<suite>/runs/<run_id>.partial.jsonl`, which is gitignored. `uv run evals run --resume <run_id>` finishes it. With neither `--suite` nor `--results-dir`, it searches the three ledgers and uses the run only if exactly one holds it. The run's settings come from the partial file, so other flags are ignored. It refuses if the case set changed, and the record carries `resumed: true`.

**Workers and timeouts.** `--workers` sets how many cases run at once: 10 by default, capped at 20. The BENCHMARK run command in [benchmarks/README.md](benchmarks/README.md#runs) uses 5. The worker count is recorded on the run and has no effect on whether a run is canonical. An attempt gets `no_answer`, a failed attempt, when the stream sends nothing for 240 seconds or is still open at `--trial-timeout`, 900 seconds by default. A block of timeouts late in a run usually means the API is overloaded: lower `--workers` before you blame the agent.

`uv run evals prune-artifacts --suite <suite>` deletes the raw artifacts of all but the newest 5 runs.

## How scoring reads

Every check is tri-state: `1.0` (pass), `0.0` (fail) or `null` (not evaluated). Each check's documentation says whether a missing input scores `null` or `0.0`, because a `null` that should have been a fail hides a failure.

Checks roll up into five buckets, one per stage of the agent's work:

| Bucket | The question it answers |
|---|---|
| Retrieval | Did the agent understand the question and fetch the right data: place, dataset, dates? |
| Analysis | Are the numbers right? |
| Explanation | Is the prose faithful to the data? |
| Output | Are charts and dashboards presented correctly? |
| Scope | Did it do the right kind of work: answer with data, suggest datasets, ask the user to choose, or decline? |

Most checks belong to one bucket. A few are shared by two, because their failure cannot be pinned on one, and bucket tables report the two kinds apart. Info-only checks are recorded and reported but never change a verdict: they are new or unreliable checks that have not yet earned a vote. The [evaluators README](src/goldset/evaluators/README.md#index) maps every check to its bucket and lists the info-only ones.

**Verdicts.** Read a run through verdicts and bucket tallies, never a flat mean.

- An **attempt**, one trial of one case, passes when every gating check it scored passed. It fails when one scored `0.0`, or when the agent sent no reply (`no_answer`). An attempt the harness could not score, because it failed after the reply or the judge failed, is left out.
- A **row**, one case's result in a run, gets one verdict from its attempts:
  - `pass`: most of its scored attempts passed;
  - `fail`: they did not, and a tie fails;
  - `error`: no attempt could be scored. It never counts as a fail; rerun the case before you trust it;
  - `uncovered`: no gating check was evaluated. It never counts as a pass.

CHALLENGE rates and the BENCHMARK North Star are both the share of measured rows whose verdict is `pass`. The scorecards page headline is stricter: the share of questions right on every trial. [benchmarks/README.md, Metrics](benchmarks/README.md#metrics) defines the BENCHMARK rates, and [results/README.md, Scoring change log](results/README.md#scoring-change-log) says when these rules last changed.

**Multi-turn cases** run all their turns in one conversation. Per-turn checks carry the turn number, as in `t2.aoi_id_match`, and `state_delta` scores the expected changes between turns. A turn that errors ends its conversation. Only GOLD has multi-turn cases today.

**Silence is not a pass.** Each report's reconciliation line compares the checks a case's expected values imply with those actually evaluated. `tools/flakiness.py` marks a partial sample INSUFFICIENT DATA instead of calling it stable.

## Repository layout and docs

| Path | What it holds | Doc |
|---|---|---|
| `cases/` | the shared case reference, and `zeno_catalog.json`, the snapshot of the agent's dataset catalogue | [cases/README.md](cases/README.md) |
| `cases/challenge/` | CHALLENGE cases, `MANIFEST.json`, `TARGETS.yml` and the generated `COVERAGE.md` | [README](cases/challenge/README.md), [CHANGELOG](cases/challenge/CHANGELOG.md), [COVERAGE](cases/challenge/COVERAGE.md) |
| `cases/v2/`, `cases/v1/` | GOLD legacy copy: the working set and the frozen import of the retired Google Sheet | [cases/GOLD-AUTHORING.md](cases/GOLD-AUTHORING.md) |
| `benchmarks/` | BENCHMARK manifests, and `overlays/` for the plain baseline | [benchmarks/README.md](benchmarks/README.md) |
| `generation/` | the pipeline that generates CHALLENGE's numeric cases | [generation/README.md](generation/README.md) |
| `seeds/` | the CSVs that CHALLENGE cases and BENCHMARK versions were built from | [seeds/README.md](seeds/README.md) |
| `results/` | one ledger per suite, and `index.json`, the generated index of committed runs | [results/README.md](results/README.md) |
| `results/plain/` | the plain baseline's runs, references, scores and reports | [results/plain/README.md](results/plain/README.md) |
| `src/goldset/` | the library and the `evals` command | [CLAUDE.md, Module map](CLAUDE.md#module-map) |
| `src/goldset/evaluators/` | every check: what it reads, when it scores `null` or `0.0`, how to triage it | [evaluators README](src/goldset/evaluators/README.md) |
| `tools/` | command-line tools over `src/goldset`, and which files are generated | [tools/README.md](tools/README.md) |
| `schema/` | JSON Schemas for case files and BENCHMARK page data | |
| `templates/` | HTML templates for the run reports | |
| `tests/` | the tests; they need no network | |
| `docs/` | the glossary and the GOLD legacy notes | [glossary](docs/glossary.md), [gold-legacy](docs/gold-legacy.md) |
| `.claude/skills/` | Claude Code skills | [below](#claude-code-skills) |
| `.github/workflows/ci.yml` | the checks on every pull request, and a manual GOLD staging run | |

## Claude Code skills

The repo commits [Claude Code](https://claude.com/claude-code) skills under `.claude/skills/`, so everyone gets the same workflows. Invoke one by name, such as `/benchmark-run`, or describe the task and the matching skill loads.

| Skill | Use it to |
|---|---|
| **CHALLENGE and BENCHMARK** | |
| `challenge-cases` | add, import, generate or revise CHALLENGE cases; run CHALLENGE and roll the run up |
| `benchmark-run` | run a BENCHMARK version, write its page data, and rerun revised members |
| `plain-baseline` | run or rescore the plain baseline; it stops before the step that spends API budget |
| **Any store** | |
| `case-edit` | change any case: the uid consequences first, then the after-edit commands |
| `sync-catalog` | refresh the dataset catalogue snapshot and read what it changes in coverage |
| **GOLD legacy copy only** | |
| `gold-run` | run GOLD and finish the run |
| `new-case` | write a GOLD case |
| `release-gate` | give the two-run release verdict |
| `triage-run` | classify a GOLD run's failures and draft its recommendations doc |
