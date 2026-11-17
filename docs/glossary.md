## Glossary

Definitions only: counts are in each store's COVERAGE.md ([CHALLENGE](cases/challenge/COVERAGE.md), [GOLD](cases/v2/COVERAGE.md)), and rules are in the sections above and in [CLAUDE.md](CLAUDE.md). Terms marked *(GOLD)* apply only to the GOLD legacy copy.

### The product

- **GNW (Global Nature Watch)**: the World Resources Institute (WRI) product for asking questions about land and nature data for named places.
- **Project Zeno, the agent**: the LLM agent behind GNW, built in [wri/project-zeno](https://github.com/wri/project-zeno). The harness asks it a question with `POST /api/chat`, then reads its final state with `GET /api/threads/{id}/state`; checks score that state.
- **Horizon**: the agent's name in the GNW app. The plain baseline and the scorecards page call the agent Horizon.
- **suite**: one of the things this repo measures with the harness: `challenge`, `benchmark` or `gold`. `--suite` picks a suite's case store and results directory together. See [Running a suite](#running-the-set).
- **CHALLENGE**: the quality and accuracy suite, in `cases/challenge/` (set, cohort, case). Its verdicts are pass rates per set and cohort, never regression counts, and its ledger is `results/challenge/`. See [cases/challenge/README.md](cases/challenge/README.md).
- **BENCHMARK**: a frozen, versioned subset of CHALLENGE behind the North Star: a uid manifest at `benchmarks/<version>.json`, run with `evals run --benchmark`, with results in `results/benchmark/`. See [benchmarks/README.md](benchmarks/README.md).
- **plain baseline**: a plain LLM (Sonnet with web search) asked the BENCHMARK `2026-draft-5` questions and scored on its reply only, beside the agent's own replies. Its results are in `results/plain/`. See [results/plain/README.md](results/plain/README.md).
- **GOLD** *(GOLD)*: the capability regression suite, run before each release (also called the capability smoke-test set; not the same thing as a [smoke run](#smoke-run)). Its headline is a regression count, not a score. It moved to project-zeno `evals/gold/` on 2026-10-27; `cases/v1`, `cases/v2` and `results/gold/` here are a legacy copy.
- **gnw-evals**: the earlier evaluation harness ([wri/gnw-evals](https://github.com/wri/gnw-evals)) that this harness was ported from. A few [legacy tools](#legacy-tools) still read or write its formats.
- **harness**: the code here that sends each case to the agent, fetches the final state and scores it (`src/goldset/runner/`, run with `evals run`).
- **environment**: the agent deployment a run targets: `staging`, `prod` or `local` (`http://localhost:8000`). Recorded on the run and in its run_id.
- <a id="profile"></a>**ff, tool profile**: `ff` (feature flag) is a field in the chat request that picks the agent's tool profile. Leaving it out gives the default profile; `experimental` adds features not yet released to the default. A run records its `ff`, and its run_id ends with it. See [Running a suite](#running-the-set).
- **AOI (area of interest)**: the place a question is about, as the agent resolved it: one or more ids from a boundary source (`aoi_source`), which is `gadm`, `kba`, `wdpa` or `landmark`.
- **GADM**: the Database of Global Administrative Areas: country, state and district boundaries. Ids look like `BRA.25_1`: a country code, admin-level numbers, then a `_N` suffix that `aoi_id_match` ignores.
- **KBA, WDPA, Landmark**: the other AOI sources: Key Biodiversity Areas, the World Database on Protected Areas, and LandMark (indigenous and community lands).
- **dataset, catalogue**: the agent's datasets are numbered and defined in project-zeno's dataset catalogue (`src/agent/datasets/catalog/*.yml`). A case's `dataset_id` names the dataset it expects. A retired dataset id, such as 0 (DIST-ALERT), is never reused.
- **LGMS**: the Land GHG Monitoring System dataset (id 12), hidden on the default profile.
- **nudge**: the agent's structured follow-up offer, held in the `nudge` state field as `{type, options, data?}`. A `dataset_choice` nudge offers datasets (scope `suggest`); other types, such as `aoi_choice`, ask the user to pick or clarify (scope `clarify`). It replaced the older `suggested_datasets` field, which the agent no longer writes.
- **send_nudge**: the agent tool that writes a nudge with fixed arguments, the most deterministic kind of nudge.
- **thread**: one conversation with the agent. Each trial runs in a fresh thread; a multi-turn case sends all its turns to one thread.

### Cases and stores

- **case**: one test, stored as one YAML file: `cases/challenge/<set>/<cohort>/<id>.yaml` in CHALLENGE, `cases/<store>/<group>/<id>.yaml` in GOLD. It holds a query (or turns), the expected values it is graded on, a status, a group and free-form notes.
- **id**: a case's stable, human-readable name, such as `ch-aoi-001` (CHALLENGE), `1-030` or `mt-005` (GOLD). It survives edits, so it links every version of one test.
- <a id="uid"></a>**uid**: a 16-character hash (truncated SHA-256) of a case's query and every non-empty expected value; for a multi-turn case, of every turn in order (in v2, including each turn's `deltas`). Editing the query or any expected value gives a new uid; status, set, group and notes never do. Results are keyed by uid. The exact rules are in [CLAUDE.md](CLAUDE.md#the-identity-system).
- <a id="caseset-version"></a>**caseset_version**: a 16-character hash of the sorted uids of every case in a store, kept in the store's `MANIFEST.json`. It changes when a case is added, removed or given a new uid. Two runs with the same caseset_version scored the same case content; runs with different ones can still be compared over the cases they share ([Comparing two runs](results/README.md#comparing-two-runs)).
- **store**: a directory of case files plus its generated `MANIFEST.json`. `cases/challenge` holds CHALLENGE and every BENCHMARK member. `cases/v2` (the GOLD working set) and `cases/v1` (the frozen import of the retired Google Sheet; a test fails if it changes) are the GOLD legacy copy. See [cases/README.md](cases/README.md#the-stores).
- **MANIFEST.json**: a per-store file written by `tools/check.py --fix`: the caseset_version plus an id-to-uid index.
- **expected, notes**: `expected` holds the values a case is graded on; each non-empty key switches on one or more checks and is part of the uid. `notes` holds annotations, such as `status_reason`, that are never hashed or scored.
- **set, cohort**: CHALLENGE's two levels above the case. A set is a kind of question (`aoi`, `dataset`, `quantification`, `comparison`, `trend`, `monitoring`, `causal`, `portfolio`), stored in the case's `set` field. A cohort is a group of cases within a set (a prompt class or a dataset), stored in `group`. Neither is hashed. Run one set with `--set <name>`.
- **group**: the directory a case sits in. In CHALLENGE it is the cohort; in GOLD it is the capability the case tests (`direct`, `temporal`, `dashboard` and so on).
- **status**: where a case is in its lifecycle: `ready`, `todo`, `done` or `not doing`. `done` is used in GOLD only. By default every status except `not doing` runs. See [Status lifecycle](cases/README.md#status-lifecycle).
- **park, unpark**: set a case to `not doing` with a dated reason in `notes.status_reason`, or bring it back. An unparked case must show again that the reason it was parked no longer holds.
- **scope**: the kind of work a case expects: `analyse` (pull data and answer), `suggest` (offer datasets), `clarify` (ask the user to choose) or `refuse` (decline). The harness classifies the agent's final state into one of these; `refuse` matches a state with no data pull, no suggestion and no nudge.
- **`;` in expected values**: in `dataset_id`, `scope`, `nudge_type` and `chart_type`, `a;b` means either value is acceptable. In `aoi_ids` it means all of them (the two sets must match). Other fields have their own rules, given with each check in the [evaluators README](src/goldset/evaluators/README.md#index) and in [cases/README.md](cases/README.md#semicolons).
- **multi-turn case, deltas**: a case with `turns:` instead of one query and expected block; all turns share one thread. A turn's `deltas` say which state fields must have `changed`, stayed the same (`retain`) or become empty (`absent`) since the previous turn, scored as the `state_delta` check. Only GOLD has multi-turn cases today.
- <a id="ground-truth"></a>**ground truth**: an `expected.ground_truth` selector, such as `sum(area_ha) WHERE year=2019`, that names a figure instead of pinning its value. The harness fetches the value from the analytics API when the run starts, so the case survives data releases with its uid. Only GOLD cases use it today. See [Run-time ground truth](cases/README.md#run-time-ground-truth-ground_truth).
- **figure formula**: an `expected.figure` (and `figure_claim`) formula that names a figure the answer must state, checked against the table the agent itself pulled. BENCHMARK members use it. See `figure_match` in the [evaluators README](src/goldset/evaluators/README.md#index).
- **query template, run token**: a token such as `{current_year}` in a query, or `{run-30d}` in an expected date, replaced with a concrete date when the run starts. The uid hashes the token, not the date, so the case keeps its identity as time passes.
- **env_gated** *(GOLD)*: a note on a case whose capability is missing in some environment or profile, so its zeros are not read as regressions. Only people read it; no code does.
- **sentinel** *(GOLD)*: a deliberately loosely worded case, kept so that a drift towards over-nudging is still caught.
- **depth rule** *(GOLD)*: a case's expected values must imply at least two checks in at least two buckets, so a pass always measured something. CI enforces it on `cases/v2` ([The audit gate](cases/GOLD-AUTHORING.md#the-audit-gate)).
- **COVERAGE.md**: a generated report of what a store covers: groups, buckets, expected fields, datasets and held or parked cases. `cases/challenge/COVERAGE.md` and `cases/v2/COVERAGE.md` exist. Never edit one by hand; CI fails if it is out of date.
- **catalogue snapshot**: `cases/zeno_catalog.json`, a committed copy of the agent's dataset catalogue, so COVERAGE.md can be generated without network access. It also holds the analytics endpoint and date window that ground-truth requests are built from.
- **seed**: a CSV under `seeds/` that cases or a BENCHMARK version were built from. See [seeds/README.md](seeds/README.md).

### Runs and results

- **run**: one execution of the selected cases against one environment, written as one run record.
- <a id="trial"></a>**trial, attempt**: one execution of one case within a run, in a fresh thread. `--trials 3` runs each case three times; the run stores each check's majority verdict and every trial's scores.
- **majority verdict**: a check's result across trials: pass if more than half of the trials that evaluated it passed, otherwise fail (a tie fails); not evaluated if no trial evaluated it.
- <a id="smoke-run"></a>**smoke run, canonical run, official run**: the run tiers. A smoke run (1 trial, the default) is for quick iteration and is never committed, diffed or used as a baseline. A canonical run (prod, default profile, 3 trials) is a published CHALLENGE or BENCHMARK result; a BENCHMARK run is canonical only if it also measured every active member. An official run *(GOLD)* (3 trials) is anything that produces a regression count or becomes a baseline. See [Running a suite](#running-the-set).
- **build label**: free text passed with `--build` naming the agent build under test (default `unknown`). The harness records it as given; it does not ask the API.
- **run record, ledger**: a run record is the JSON file one run writes to `results/<suite>/runs/`, immutable once written. A ledger is a suite's committed set of run records. Nothing in it is ever written or edited by hand. Contract: [results/README.md](results/README.md).
- **run_id**: a run record's name, `<YYYYMMDD>T<HHMMSS>Z_<env>[_<ff>]` in UTC, for example `20260831T163347Z_prod`. The suffix shows the environment and `ff` at a glance.
- **partial file**: `results/<suite>/runs/<run_id>.partial.jsonl` (gitignored), where a run appends each finished case so that a killed run can be resumed.
- **artefacts**: raw agent state for each case and trial, gzipped under `results/<suite>/artifacts/<run_id>/` (gitignored). They keep evidence a run record does not. `uv run evals prune-artifacts --suite <suite>` deletes all but the newest runs' artefacts.
- **methodology note**: text passed with `--note` and stored as `methodology_note` on the run, recording that check semantics changed since the previous run.
- **rollup**: `tools/challenge_rollup.py`'s reading of one or more runs as pass rates, with confidence intervals and latency; with `--benchmark`, the North Star and failure modes. It prints its tables (and writes JSON with `--json`); it never writes to the ledger.
- **North Star**: BENCHMARK's headline rate: the share of measured active members whose verdict passed (most scored attempts right), with a Wilson 95% interval. See [benchmarks/README.md](benchmarks/README.md#metrics).
- **page data**: `results/benchmark/pages/<run_id>.json`, the precomputed numbers for one BENCHMARK run that the frontend scorecards page reads. See [Page data contract](benchmarks/README.md#page-data-contract).
- **manifest, member, erratum**: a BENCHMARK version's manifest lists its members, each a CHALLENGE case uid with facets frozen when the version was built. An erratum voids a broken member of a frozen version instead of editing it.
- **regression, recovery** *(GOLD)*: between two runs, for a case uid present in both: a check that went from pass to fail (regression) or from fail to pass (recovery). Counted per check, not per case. Info-only checks never count towards the gate.
- <a id="data-bump"></a>**data bump** *(GOLD)*: a ground-truth check that flipped between two runs while the digest of its fetched values moved, so the data changed under the case. `diff_runs.py` lists bumps but never counts them as regressions or recoveries, and they never gate. A bump that the agent's own recorded figure does not explain is flagged as a possible hidden regression.
- **coverage loss, coverage gain** *(GOLD)*: a check that went from evaluated to not evaluated (loss) or the reverse (gain) between two runs. A check that stopped running has not passed.
- **comparable runs**: two runs whose comparison means something: same `ff`, same trial count (3) and same environment. The caseset_version may differ, because a diff only covers uids present in both runs. See [Comparing two runs](results/README.md#comparing-two-runs).
- **baseline** *(GOLD)*: the official run a new run is diffed against: the most recent committed official run that is comparable with it.
- **release gate** *(GOLD)*: the check before a release: `tools/diff_runs.py --fail-on-regression` between the baseline and an official run of the candidate build. See [The release gate](#the-release-gate).
- **stale_case, stale expectation**: `stale_case` marks a result whose uid the current store no longer holds ([results/README.md](results/README.md)). A stale expectation is something else: an expected value that is out of date, so the case fails although the agent is right.
- **flaky check**: a check whose trials disagree within one run. `tools/flakiness.py` reports each check's mean, standard deviation and number of flips across trials.
- **compose**: build a current picture from a full run plus scoped re-runs with `tools/compose_runs.py`. It works in the analysis only and never writes to the ledger.
- **recommendations doc**: `results/<suite>/recommendations/<run_id>.md`, the written analysis of a committed run: what to report, what the run says about the cases and the harness, and what to watch next.
- **campaign** *(GOLD)*: a write-up of a multi-run validation effort, kept in `results/gold/campaigns/`.
- **probation, re-admission**: a trial period before something is trusted again. An info-only check must meet its stated condition before it gates again; an unparked case must show that the reason it was parked no longer holds.

### Scoring

- **check**: one named score on a case, such as `aoi_id_match`. Every check is tri-state.
- **evaluator**: a function of the agent's final state and the case's expected values that returns one or more checks. Evaluators are registered in `src/goldset/registry.py`.
- **deterministic, judged**: how a check decides: in code, or by asking the LLM judge. Some checks combine the two (for example, the judge picks the figure out of the prose and code compares it); the evaluators README says which.
- **judge**: the LLM (`claude-haiku-4-5` unless `--judge-backend` picks another) that scores judged checks. It is never asked to do arithmetic; numbers are compared in code.
- **tri-state**: every check scores `1.0` (pass), `0.0` (fail) or `null` (not evaluated). Each check's documentation says when a missing input scores `null` and when it scores `0.0`.
- **implied check, reconciliation line**: implied checks are those a case's expected values guarantee will be evaluated. A report's reconciliation line compares the implied count with the evaluated count, so a check that silently did not run shows up.
- <a id="bucket"></a>**bucket**: one of five pipeline stages a check speaks for: retrieval, analysis, explanation, output and scope (see [How scoring reads](#how-scoring-reads)). A **dedicated** check belongs to one bucket; a **shared** check belongs to two, because its failure cannot be pinned on one. BENCHMARK calls the buckets **stages** when it attributes a failure.
- <a id="info-only"></a>**gating, info-only**: a gating check can turn a row's verdict to fail. An info-only check is recorded and reported but never affects a row verdict or the release gate; new judged checks start info-only. The list is `INFO_ONLY` in `src/goldset/buckets.py`, explained in [Info-only checks](src/goldset/evaluators/README.md#info-only-checks).
- <a id="row"></a>**row, row verdict**: a row is one case's result in a run (the word dates from the sheet). Its verdict is `pass` (most scored attempts right), `fail`, `error` (no attempt could be scored, never counted as a fail) or `uncovered` (no gating check was evaluated, never counted as a pass). See [How scoring reads](#how-scoring-reads).
- **judge error**: a judge call that failed. The check stays `null` and its name is recorded in `judge_errors`; the attempt is left out of the verdict, and the row becomes `error` only if no attempt could be scored.
- **gate**: used for several things, so say which: the CI checks on every PR; the audit gate (`audit_cases.py --strict`); the release gate (`diff_runs.py --fail-on-regression`); a check being gating; the flakiness limits.
