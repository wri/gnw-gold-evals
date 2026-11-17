# Glossary

Definitions only. Counts are in each store's COVERAGE.md ([CHALLENGE](../cases/challenge/COVERAGE.md), [GOLD](../cases/v2/COVERAGE.md)), and rules are in the doc that owns each topic: [README, Start here](../README.md#start-here) says which. The suites themselves are described in the [README](../README.md#suites-at-a-glance). Terms marked *(GOLD)* apply only to the [GOLD legacy copy](gold-legacy.md).

## The product

- **GNW, Global Nature Watch**: the World Resources Institute (WRI) product for asking questions about land and nature data for named places.
- **Project Zeno, the agent**: the large language model (LLM) agent behind GNW, built in [wri/project-zeno](https://github.com/wri/project-zeno). The harness asks it a question with `POST /api/chat`, then reads its final state with `GET /api/threads/{id}/state`. Checks score that state.
- **Horizon**: the agent's name in the GNW app. The plain baseline and the scorecards page call the agent Horizon.
- **frontend (FE)**: the GNW web app, in [wri/project-zeno-next](https://github.com/wri/project-zeno-next). Its AI accuracy scorecards page shows BENCHMARK page data.
- **GOLD** *(GOLD)*: the capability regression suite, run before each release. Its headline is a regression count, not a score. project-zeno also calls it the capability smoke-test set, which is not the same thing as a [smoke run](#smoke-run). It moved to project-zeno `evals/gold/` on 2026-10-27.
- **gnw-evals**: the earlier evaluation harness ([wri/gnw-evals](https://github.com/wri/gnw-evals)) that this harness was ported from. A few legacy tools still read or write its formats.
- **harness**: the code here that sends each case to the agent, fetches the final state and scores it (`evals run`).
- **environment**: the agent deployment a run targets: `staging`, `prod` or `local` (`http://localhost:8000`). It is recorded on the run and in its run_id.
- <a id="profile"></a>**ff, tool profile**: `ff` (feature flag) is a field in the chat request that picks the agent's tool profile. Leaving it out gives the default profile. `experimental` adds features not yet released to the default. A run records its `ff`, and its run_id ends with it.
- **AOI, area of interest**: the place a question is about, as the agent resolved it: one or more ids from a boundary source, `aoi_source`. The sources are `gadm`, `kba`, `wdpa` and `landmark`.
- **GADM**: the Database of Global Administrative Areas: country, state and district boundaries. Ids look like `BRA.25_1`: a country code, admin-level numbers, then a `_N` suffix that `aoi_id_match` ignores.
- **KBA, WDPA, LandMark**: the other AOI sources: Key Biodiversity Areas, the World Database on Protected Areas, and LandMark, a map of indigenous and community lands.
- **dataset, catalogue**: the agent's datasets are numbered and defined in project-zeno's dataset catalogue (`src/agent/datasets/catalog/*.yml`). A case's `dataset_id` names the dataset it expects. A retired dataset id, such as 0 (DIST-ALERT), is never reused.
- **LGMS**: the Land Greenhouse Gas Monitoring System dataset (id 12). It is on the `experimental` profile only.
- **nudge**: the agent's structured follow-up offer, held in the `nudge` state field as `{type, options, data?}`. A `dataset_choice` nudge offers datasets, which is scope `suggest`. Other types, such as `aoi_choice`, ask the user to pick or clarify, which is scope `clarify`. It replaced the older `suggested_datasets` field, which the agent no longer writes.
- **send_nudge**: the agent tool that writes a nudge with fixed arguments, the most deterministic kind of nudge.
- **thread**: one conversation with the agent. Each trial runs in a fresh thread. A multi-turn case sends all its turns to one thread.

## Cases and stores

- **case**: one test, stored as one YAML file: `cases/challenge/<set>/<cohort>/<id>.yaml` in CHALLENGE, `cases/<store>/<group>/<id>.yaml` in GOLD. It holds a query (or turns), the expected values it is graded on, a status, a group and free-form notes.
- **id**: a case's stable, human-readable name, such as `ch-aoi-001` in CHALLENGE or `1-030` in GOLD. It survives edits, so it links every version of one test.
- <a id="uid"></a>**uid**: a 16-character hash (truncated SHA-256) of a case's query and every non-empty expected value. For a multi-turn case it covers every turn in order, and in `cases/v2` each turn's `deltas` too. Editing the query or any expected value gives a new uid. Status, set, group and notes never do. Results are keyed by uid. The rules and their reasons are in [CLAUDE.md, The identity system](../CLAUDE.md#the-identity-system).
- <a id="caseset-version"></a>**caseset_version**: a 16-character hash of the sorted uids of every case in a store, kept in the store's `MANIFEST.json`. It changes when a case is added, removed or given a new uid. Two runs with the same caseset_version scored the same case content.
- **store**: a directory of case files plus its generated `MANIFEST.json`. `cases/challenge` holds CHALLENGE and every BENCHMARK member. `cases/v2` and `cases/v1` are the GOLD legacy copy. See [cases/README.md](../cases/README.md#the-stores).
- **MANIFEST.json**: a per-store file written by `tools/check.py --fix`: the caseset_version plus an index from id to uid.
- **expected, notes**: `expected` holds the values a case is graded on. Each non-empty key switches on one or more checks and is part of the uid. `notes` holds annotations, such as `status_reason`, that are never hashed or scored.
- **set, cohort**: CHALLENGE's two levels above the case. A set is a kind of question, such as `aoi` or `quantification`, stored in the case's `set` field. A cohort is a group of cases within a set, stored in `group`. Neither is hashed.
- **group**: the directory a case sits in. In CHALLENGE it is the cohort. In GOLD it is the capability the case tests, such as `direct` or `temporal`.
- **status**: where a case is in its lifecycle: `ready`, `todo`, `done` or `not doing`. `done` is used in GOLD only. See [Status lifecycle](../cases/README.md#status-lifecycle).
- **park, unpark**: set a case to `not doing` with a dated reason in `notes.status_reason`, or bring it back. An unparked case must show again that the reason it was parked no longer holds.
- **scope**: the kind of work a case expects: `analyse` to pull data and answer, `suggest` to offer datasets, `clarify` to ask the user to choose, or `refuse` to decline. The harness classifies the agent's final state into one of these. `refuse` matches a state with no data pull, no suggestion and no nudge.
- **multi-turn case, deltas**: a case with `turns:` instead of one query and expected block. All its turns share one thread. A turn's `deltas` name state fields under three keys: `changed` fields must differ from the previous turn, `retain` fields must stay the same, and `absent` fields must be empty. The `state_delta` check scores them. Only GOLD has multi-turn cases today.
- <a id="ground-truth"></a>**ground truth**: an `expected.ground_truth` selector, such as `sum(area_ha) WHERE year=2019`, that names a figure instead of pinning its value. The harness fetches the value from the analytics API when the run starts, so the case survives data releases with its uid. Only GOLD cases use it today. See [Run-time ground truth](../cases/README.md#run-time-ground-truth-ground_truth).
- **figure formula**: an `expected.figure` or `figure_claim` formula that names a figure the answer must state. It is checked against the table the agent itself pulled. BENCHMARK members use it. See `figure_match` in the [evaluators README](../src/goldset/evaluators/README.md#index).
- **query template, run token**: a token such as `{current_year}` in a query, or `{run-30d}` in an expected date, replaced with a concrete date when the run starts. The uid hashes the token, not the date, so the case keeps its identity as time passes.
- **env_gated** *(GOLD)*: a note on a case whose capability is missing in some environment or profile, so its zeros are not read as regressions. Only people read it; no code does.
- **sentinel** *(GOLD)*: a deliberately loosely worded case, kept so that a drift towards over-nudging is still caught.
- **depth rule** *(GOLD)*: a case's expected values must imply at least two checks in at least two buckets, so a pass always measured something. CI enforces it on `cases/v2` ([The audit gate](../cases/GOLD-AUTHORING.md#the-audit-gate)).
- **COVERAGE.md**: a generated report of what a store covers: groups, buckets, expected fields, datasets, and held or parked cases. `cases/challenge/` and `cases/v2/` each have one.
- **catalogue snapshot**: `cases/zeno_catalog.json`, a committed copy of the agent's dataset catalogue. COVERAGE.md is generated from it without network access, and ground-truth requests are built from it.
- **seed**: a CSV under `seeds/` that cases or a BENCHMARK version were built from. See [seeds/README.md](../seeds/README.md).
- **benchmark sheet**: a reviewed spreadsheet with one row per BENCHMARK question, exported to a seed CSV. The current one is the BEF sheet, whose exports are `seeds/benchmark-v2026-bef-*.csv`. Its rows carry the use cases UC1 to UC6.

## BENCHMARK versions

- **version, manifest, member**: a BENCHMARK version is one manifest, `benchmarks/<version>.json`. It lists its members, each a CHALLENGE case uid with facets (type, cohort, difficulty, stages) fixed when the version was built.
- **draft, frozen, retired, erratum**: the states of a version. A **draft** may be rebuilt, and editing a member case drops that member until the draft is rebuilt. A **frozen** version never changes: its members are never edited, and an **erratum** voids a broken member instead. A **retired** version is kept only because its runs reference it. Today `2026-draft-5` is the live draft and no version is frozen yet; freezing is the intended end state.
- **query type**: the BENCHMARK axis that groups questions by what they ask, such as Quantification or Monitoring. A type the manifest marks `measured: false` is reported as not yet measured, never as zero.
- **use case (UC1 to UC6)**: the priority use cases from the benchmark sheet: UC1 alert monitoring and response, UC2 supply chain and sourcing, UC3 investigating causes, UC4 reporting and accountability, UC5 landscape context, UC6 understanding the data. The page data reports rates per use case.
- **North Star**: BENCHMARK's headline rate: the share of measured active members whose row verdict is `pass`, with a Wilson 95% interval. Page data calls it `majority`. See [Metrics](../benchmarks/README.md#metrics).
- **every-time rate, any-time rate**: stricter and looser readings of the same run. The every-time rate counts a question right only when every scored attempt was right; it is the headline of the scorecards page. The any-time rate counts a question right when at least one attempt was.
- **page data**: `results/benchmark/pages/<run_id>.json`, the precomputed numbers for one BENCHMARK run that the scorecards page reads. See [Page data contract](../benchmarks/README.md#page-data-contract).

## Runs and results

- **run**: one execution of the selected cases against one environment, written as one run record.
- <a id="trial"></a>**trial, attempt**: one execution of one case within a run, in a fresh thread. `--trials 3` runs each case three times. The run stores every trial's checks.
- **majority verdict**: one check's result across trials: pass if more than half of the trials that evaluated it passed, else fail (a tie fails). It is not evaluated if no trial evaluated it. The row verdict does not use it.
- <a id="smoke-run"></a>**smoke run, canonical run**: the two run tiers. A smoke run has 1 trial, the default, and is never committed, compared or used as a baseline. A canonical run has 3 trials and the default profile, and is the only kind that is published, trended, diffed or used as a baseline. For CHALLENGE and BENCHMARK it is also on prod, and a BENCHMARK run must also measure every active member. GOLD documents call a canonical run an **official run**. See [Running a suite](../README.md#running-a-suite).
- **build label**: free text passed with `--build` naming the agent build under test. The default is `unknown`. The harness records it as given.
- **run record, ledger**: a run record is the JSON file one run writes to `results/<suite>/runs/`, immutable once written. A ledger is a suite's committed set of run records. Nothing in it is ever written or edited by hand. Contract: [results/README.md](../results/README.md).
- **run_id**: a run record's name, `<YYYYMMDD>T<HHMMSS>Z_<env>[_<ff>]` in UTC, for example `20260831T163347Z_prod`.
- **partial file**: `results/<suite>/runs/<run_id>.partial.jsonl`, gitignored. A run appends each finished case to it, so a killed run can be resumed.
- **artifacts**: raw agent state for each case and trial, gzipped under `results/<suite>/artifacts/<run_id>/` and gitignored. They keep evidence a run record does not, and `tools/benchmark_page.py` reads them. `uv run evals prune-artifacts --suite <suite>` deletes all but the newest runs' artifacts.
- **methodology note**: text passed with `--note` and stored as `methodology_note` on the run. It records that check semantics changed since the previous run.
- **rollup**: `tools/challenge_rollup.py`'s reading of one or more runs as pass rates, with confidence intervals and latency. With `--benchmark` it gives the North Star and failure modes. It never writes to the ledger.
- **comparable runs**: two runs with the same `ff`, the same trial count and the same environment. See [Running a suite](../README.md#running-a-suite).
- **regression, recovery** *(GOLD)*: between two runs, for a case uid present in both: a check that went from pass to fail, or from fail to pass. Counted per check, not per case. Info-only checks never count towards the gate.
- <a id="data-bump"></a>**data bump** *(GOLD)*: a ground-truth check that flipped between two runs while the digest of its fetched values moved, so the data changed under the case. See [Data bumps](gold-legacy.md#data-bumps).
- **coverage loss, coverage gain** *(GOLD)*: a check that went from evaluated to not evaluated, or the reverse, between two runs. A check that stopped running has not passed.
- **baseline** *(GOLD)*: the canonical run a new run is diffed against: the newest committed canonical run that is comparable with it.
- **release gate** *(GOLD)*: the check before a release: `tools/diff_runs.py --fail-on-regression` between the baseline and a canonical run of the candidate build. See [The release gate](gold-legacy.md#the-release-gate).
- **stale_case, stale expectation**: `stale_case` marks a result whose uid the current store no longer holds. A stale expectation is something else: an expected value that is out of date, so the case fails although the agent is right.
- **flaky check**: a check whose trials disagree within one run. `tools/flakiness.py` reports each check's mean, standard deviation and number of flips across trials.
- **compose**: build a current picture from a full run plus scoped re-runs with `tools/compose_runs.py`. It works in the analysis only and never writes to the ledger.
- **recommendations doc**: `results/<suite>/recommendations/<run_id>.md`, the written analysis of a committed run: what to report, what the run says about the cases and the harness, and what to watch next.
- **campaign** *(GOLD)*: a write-up of a multi-run validation effort, kept in `results/gold/campaigns/`.
- **probation**: a trial period before something is trusted again. An info-only check must meet its stated condition before it gates. An unparked case must show that the reason it was parked no longer holds.

## Scoring

- **check**: one named score on one attempt, such as `aoi_id_match`: `1.0` for a pass, `0.0` for a fail, or `null` when it was not evaluated.
- **evaluator**: a function of the agent's final state and the case's expected values that returns one or more checks. Evaluators are registered in `src/goldset/registry.py`.
- **deterministic, judged**: how a check decides: in code, or by asking the LLM judge. Some checks combine the two, and the evaluators README says which.
- **judge**: the LLM that scores judged checks: `claude-haiku-4-5` unless `--judge-backend` picks another. It is never asked to do arithmetic; numbers are compared in code.
- **implied check, reconciliation line**: implied checks are those a case's expected values guarantee will be evaluated. A report's reconciliation line compares the implied count with the evaluated count, so a check that silently did not run shows up.
- <a id="bucket"></a>**bucket, stage**: one of five stages of the agent's work that a check speaks for: retrieval, analysis, explanation, output and scope. A **dedicated** check belongs to one bucket. A **shared** check belongs to two, because its failure cannot be pinned on one. BENCHMARK says **stage** when it attributes a failure. See [How scoring reads](../README.md#how-scoring-reads).
- <a id="info-only"></a>**gating, info-only**: a gating check can turn an attempt to fail. An info-only check is recorded and reported but never changes a verdict or the release gate. New judged checks start info-only. The list is `INFO_ONLY` in `src/goldset/buckets.py`, explained in [Info-only checks](../src/goldset/evaluators/README.md#info-only-checks).
- <a id="row"></a>**row, row verdict**: a row is one case's result in a run; the word dates from the Google Sheet. Its verdict is `pass`, `fail`, `error` or `uncovered`, as defined in [How scoring reads](../README.md#how-scoring-reads).
- **no_answer**: the mark on an attempt that got no reply: the stream stalled, dropped or failed with a server error. It counts as a failed attempt, not an error.
- **judge error**: a judge call that failed. The check stays `null` and its name is recorded in `judge_errors`. The attempt is left out of the verdict, and the row becomes `error` only if no attempt could be scored.
- **gate**: used for several things, so say which: the CI checks on every pull request; the audit gate (`audit_cases.py --strict`); the release gate; a check being gating; the flakiness limits.
