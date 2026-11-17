# BENCHMARK

A **frozen, versioned subset of CHALLENGE** that tracks improvement over
about a year. CHALLENGE (`cases/challenge/`) grows and changes, so its rates
move under readers. BENCHMARK does not: it is the fixed exam behind the
published North Star. Terms are defined in
[docs/glossary.md](../docs/glossary.md).

| | GOLD (legacy copy, `cases/v2`) | CHALLENGE (`cases/challenge`) | BENCHMARK (`benchmarks/`) |
|---|---|---|---|
| Question | did a release break something? | how good is the system, per capability? | is the system getting better, on a fixed exam? |
| Headline | regression count | pass rate per set and cohort | North Star rate and its trend |
| Changes | curated per release | grows continuously | frozen per version (about once a year) |
| Cases | its own store | its own store | **none of its own**: a uid manifest over CHALLENGE |

This file owns the BENCHMARK procedures: running a version, the steps
after a run, rerunning revised members, and the page data contract.

## One version = one manifest

`benchmarks/<version>.json` (contract and validation:
`src/goldset/benchmark.py`):

- `status`: `draft`, then `frozen`, then `retired`. A frozen version also
  records its freeze date in `frozen`. No tool changes the status: it is a
  reviewed hand edit to the manifest.
- `members[]`: `{uid, id, type, set, cohort, difficulty, stages}`, plus the
  use-case facets of a curated version. Membership is by **uid**. The
  facets are fixed when the version is built, so a later taxonomy or
  case-note change cannot move a member between types.
- `types[]`: the query-type axis. It is the frontend's taxonomy with
  Spatial split into **Geospatial** (the `aoi` set) and **Dataset** (the
  `dataset` set). From `2026-draft-3` on it has 13 types, because
  **Portfolio** (many areas at once, the `portfolio` set) was added; the two
  earlier drafts have 12. A type that no member measures has
  `measured: false`, and reports show it as "not yet measured", never as
  zero. `2026-draft-5` measures 9 of its 13 types.
- `stage_order`: `scope`, `retrieval`, `analysis`, `explanation`,
  `output`. A failed question is attributed to its earliest failing stage in
  this order.
- `sampling`: how the version was built (tool, seed file or random seed,
  eligibility, the sheet rows left out).
- `errata[]`: `{uid, date, reason}`, the members voided after a freeze.

Use cases (`USE_CASES` in `src/goldset/benchmark.py`; a question can carry
several): UC1 alert monitoring and response, UC2 supply chain and sourcing,
UC3 investigating causes, UC4 reporting and accountability, UC5 landscape
context, UC6 understanding the data.

A version is built in one of two ways, and both write the same contract:

- **Sampled**: `tools/benchmark_sample.py --version <v>` draws a stratified
  sample from CHALLENGE.
- **Curated**: `tools/benchmark_from_sheet.py --seed <csv> --version <v>`
  writes one member per row of a reviewed sheet export in `seeds/`
  ([seeds/README.md](../seeds/README.md)). It also writes each member's
  sheet facets into its case's `notes`; notes are not hashed, so no uid
  changes.

Running either tool again on a draft rebuilds that draft in place. Both
tools refuse to rewrite a frozen manifest.

### Current versions

| Version | Status | Members | Built from |
|---|---|---|---|
| `2026-draft-5` | draft: the live version | 269 (30 sheet rows left out) | curated from `seeds/benchmark-v2026-bef-2026-10-27.csv` |
| `2026-draft-4` | retired | 269 | curated from `seeds/benchmark-v2026-bef-2026-10-26.csv` |
| `2026-draft-3` | retired | 269 | curated from `seeds/benchmark-v2026-bef-2026-10-22.csv` |
| `2026-draft-2` | retired | 199 | curated from `seeds/benchmark-v2026-proposed.csv` |
| `2026-draft` | retired | 100 | sampled, 20 for each of 5 types |
| `2026` | not built | | to be frozen from `2026-draft-5` once its drafted expectations are reviewed |

Retired versions stay in the repo because their runs reference them.
What changed between versions is in [Version history](#version-history).

## Rules

**Sampling** (`tools/benchmark_sample.py --version <v>`): `ready` cases
only. Geospatial and Dataset draw from **easy and medium** cases only: the
hard cohorts are so hard that they would pin the number to the frontier
instead of tracking improvement. 20 per measured type, stratified by
difficulty and cohort where the set labels difficulty, else by cohort, with
a fixed seed. Rebuilding a draft is a deliberate, reviewed act: commit the
diff. CI never rebuilds a manifest.

**Changing a member case.** Editing the query or an expected value of a
case gives it a new uid, and the version's member keeps the old one.
`tools/check_benchmark.py` reports it, and what to do depends on the
version's status:

| Status | What `check_benchmark.py` does | What to do |
|---|---|---|
| `draft` | prints a warning and exits 0; CI still fails, because `tests/test_check_benchmark.py` requires every committed manifest to be clean | rebuild the draft, regenerate `results/index.json` and commit them with the edit: [After an edit](../cases/challenge/README.md#after-an-edit) in the CHALLENGE README |
| `frozen` | prints an error and exits 1 | never edit a member: undo the edit, or void the member with an erratum and add a new case |
| `retired` | checks the manifest's structure only | nothing: a retired version keeps its old uids |

Rebuilding a draft changes the `canonical` flag of earlier runs in
`results/index.json`, because the index judges each run against the
manifest as it stands now: the runs behind the latest result stop covering
every member until the revised members are rerun ([Rerunning revised
members only](#rerunning-revised-members-only)).

**Freeze.** Once a version is frozen, its member cases are edit-frozen in
practice: change CHALLENGE by adding cases, not by editing members.

**Errata.** A frozen version is immutable apart from errata. A member found
broken (a wrong expectation, dead ground truth) is voided by an erratum,
never edited. Voided members leave the denominator of every report of that
version, and reports state the count. More than about 5% voided triggers an
early re-version. After an erratum, regenerate `results/index.json`.

**Re-versioning** (about once a year): build the new version, run the old
and the new version once side by side (the bridge), then retire the old
one. Rates are only comparable within a version.

## Runs

```bash
caffeinate -i uv run evals run --env prod --trials 3 \
  --benchmark benchmarks/2026-draft-5.json --build "<label>"
```

- `caffeinate -i` keeps a Mac awake: an idle sleep stalls a long run. Leave
  it out on other systems.
- `--benchmark` implies `--suite benchmark`. It runs the manifest's active
  members from its source store, writes to `results/benchmark/`, and records
  `benchmark: {path, version, status, manifest_sha, members}` on the run.
  Add `--dry-run` to list the members without calling the API.
- Tokens: `PROD_API_TOKEN` for the agent and `ANTHROPIC_API_KEY` for the
  judge. The CLI loads `.env` ([README.md](../README.md), Setup).
- If a run is killed, finish it with `uv run evals run --resume <run_id>`.
  With no other flag the CLI looks for the run in all three ledgers and uses
  the one match.
- Leave `--workers` at its default, 10. The canonical flag does not look at
  it (`tools/build_run_index.py` checks environment, profile and trials
  only), but each run records it: if a block of timeouts appears late in a
  run, lower it before blaming the agent.

A run is a **trend point** only when it is a **canonical run**: prod,
default profile (no `ff`), 3 trials, and every active member measured or
errored (none missing). `results/index.json` gives each BENCHMARK run a
`canonical` flag and, when it is false, the reasons.

## After a run

A BENCHMARK run is finished when its run record, page data, index entry and
recommendations doc are committed together. Do these in order, in the
checkout that ran the run:

1. **Check the manifest** before you start:
   `uv run python tools/check_benchmark.py benchmarks/<v>.json`. An error
   (frozen version) stops the run. A warning (draft) means a member case was
   edited or is no longer `ready`, so the run would leave it out: rebuild the
   draft first ([Rules](#rules)).
2. **Run it** ([Runs](#runs)).
3. **Roll it up** and read the North Star and the failure modes:
   ```bash
   uv run python tools/challenge_rollup.py --benchmark benchmarks/<v>.json \
     results/benchmark/runs/<run_id>.json
   ```
   For a rerun of revised members this covers the rerun's members only.
4. **Write the page data**:
   ```bash
   uv run python tools/benchmark_page.py results/benchmark/runs/<run_id>.json
   ```
   It reads the run's raw artifacts in
   `results/benchmark/artifacts/<run_id>/`. They are gitignored, so they
   exist only in the checkout that ran the run, and another checkout cannot
   write the page. For a rerun, add `--base` for every earlier run
   ([Rerunning revised members only](#rerunning-revised-members-only)).
5. **Stage the run and its page**:
   ```bash
   git add results/benchmark/runs/<run_id>.json results/benchmark/pages/<run_id>.json
   ```
6. **Regenerate the index**: `uv run python tools/build_run_index.py`. It
   lists tracked and staged files only, so stage first. Read the run's entry
   in `results/index.json`: call it a trend point only if it says
   `canonical: true`.
7. **Write `results/benchmark/recommendations/<run_id>.md`**. Say whether
   the run is canonical, and give the version and its status.
8. **Commit** the run, the page, `results/index.json` and the
   recommendations doc in one commit.
9. **Push** the commit. The page reaches users only when a frontend release
   pins that commit ([Page data contract](#page-data-contract)).

**Recommendations docs.** Every committed BENCHMARK run has one. A full run
or a combined page gets a full report: what the run measured, its North
Star and failure modes, what to file upstream, what it says about the cases
and the harness, and what to watch next.
`results/benchmark/recommendations/20261023T094447Z_prod.md` shows the
shape. A rerun whose results only feed a combined page gets a short note
that names the report using it. When a later report replaces one, the older
doc gets a "Superseded by" line at the top. No check in CI enforces this.

## Rerunning revised members only

After some members of a draft are revised, rerun just those members and
combine them with the earlier runs, instead of rerunning all of them.
First finish [After an edit](../cases/challenge/README.md#after-an-edit) in
the CHALLENGE README: until the draft is rebuilt, its manifest still lists
the old uids, which the earlier runs measured, so there is nothing to
rerun. Then:

1. **List the runs behind the version's latest result**: the newest index
   entry of the version that has a page, plus the runs that page combines
   (`composed_with` in the index, `run.sources` in the page):
   ```bash
   uv run python -c "import json,sys; e=[r for r in json.load(open('results/index.json'))['sets']['benchmark'] if r['benchmark']['version']==sys.argv[1] and 'page' in r][-1]; print(*e.get('composed_with', []), e['run_id'])" 2026-draft-5
   ```
   Pass every run it prints in the next steps. If you pass only the newest,
   which may itself be a small rerun, `--missing-from` selects nearly every
   member.
2. **Check the selection**: it must list exactly the revised members.
   ```bash
   uv run evals run --env prod --trials 3 --benchmark benchmarks/<v>.json \
     --missing-from results/benchmark/runs/<run1>.json \
     --missing-from results/benchmark/runs/<runN>.json --dry-run
   ```
   "measured every active member; nothing to run" means the draft was not
   rebuilt.
3. **Run it**: the same command without `--dry-run`, with `--build
   "<label>"`, under `caffeinate -i` on a Mac. Run it in the checkout that
   ran the earlier runs, because step 5 needs their artifacts.
4. **Roll it up** if you want the rerun's own numbers (After a run, step
   3). The rollup covers only the rerun's members: its rate is not the
   version's rate.
5. **Write the combined page**, with every run from step 1 as a base:
   ```bash
   uv run python tools/benchmark_page.py results/benchmark/runs/<rerun>.json \
     --base results/benchmark/runs/<run1>.json \
     --base results/benchmark/runs/<runN>.json
   ```
   For each member, the newest run that measured it wins. The tool prints
   the combined rate ("every time" and "majority" over all active members),
   and the page's `summary` holds it: that is the version's result. The tool
   needs `results/benchmark/artifacts/<run_id>/` for the rerun and for every
   base. If the earlier runs were made in another checkout, copy or link
   their artifact directories into this one first. The manifest must not
   change between steps 3 and 5: the tool stops when its `manifest_sha`
   differs from the rerun's.
6. **Continue with [After a run](#after-a-run), step 5.** In the index the
   rerun's entry names its bases under `composed_with` and is judged over
   all of them: canonical when every run is prod, default profile and 3
   trials and together they cover every active member. In the
   recommendations doc, say that the results come from different dates, so
   agent changes in between show up only in the rerun members. Prefer a full
   run before a freeze.

## Page data contract

`results/benchmark/pages/<run_id>.json` holds the precomputed numbers for
one BENCHMARK run: the data behind the AI accuracy scorecards page of the
GNW frontend. `tools/benchmark_page.py` writes it, and nothing else does;
never edit it by hand. A combined page (`--base`) is named after the
rerun.

Top-level keys, at `schema_version` 1 (`SCHEMA_VERSION` in
`tools/benchmark_page.py`):

| Key | Holds |
|---|---|
| `schema_version` | the page format version, `1` |
| `generated_by` | `"tools/benchmark_page.py"` |
| `run` | the run's `run_id`, `started`, `environment`, `ff`, `num_trials` and `harness_sha`; a combined page adds `sources`, each run it draws on with its question count |
| `benchmark` | the manifest's `version`, `status` and `manifest_sha`, the number of active `members`, and how many sheet rows were `excluded` |
| `summary` | the headline numbers: `majority` (the North Star), `every_time` (the page headline) and `any_time` rates, counts, `failure_modes`, `failure_modes_by_standard`, `consistency`, per-trial `attempt_rates` and `datasets_covered` |
| `stages` | per stage in `stage_order`: checks checked and passed, and the first failures |
| `unattributed` | failed questions whose only failures were on shared checks |
| `types` | per query type: the same rates and failure modes, plus `measured`, stage checks and example questions |
| `use_cases` | per use case (UC1 to UC6): the same rates and failure modes, plus the composition of its questions |
| `questions` | one entry per active member: its verdict, per-trial results, failed checks, expected values, the run it came from, and a summary of each attempt |

The JSON Schema for the page is `schema/benchmark_page.schema.json`, and
`tests/test_benchmark_page_schema.py` checks every committed page against
it.

**The frontend reads it strictly.** In
[wri/project-zeno-next](https://github.com/wri/project-zeno-next),
`src/features/ai-accuracy-scorecards` fetches each page from GitHub at a
commit of this repo and parses it with a schema that throws on a mismatch.
It shows only the runs that its `model/releases.ts` lists, each pinned to a
full commit sha of this repo. So:

- A new page reaches users only with a frontend release that adds its run
  to `releases.ts`. Pin canonical runs only.
- The commit that holds the page must be pushed to
  [wri/gnw-gold-evals](https://github.com/wri/gnw-gold-evals), and a pinned
  sha must stay reachable there. Never rebase, squash or force-push a branch
  that holds a pinned commit.
- Rebuilding a page in place changes nothing users see until
  `releases.ts` pins a commit that holds the new page.
- Changing the page's shape (a key, a type, the meaning of a field) is a
  cross-repo contract change: change the schema, its test and the frontend
  parser in the same cycle.

## Raw artifacts

`results/benchmark/artifacts/<run_id>/` holds each attempt's raw agent
state. It is gitignored and never leaves the checkout that ran the run.
Two things read it later:

- `tools/benchmark_page.py`, for the run and for every `--base` run. It
  stops if a directory is missing.
- The plain baseline (`references` and `score`), for the draft-5 runs on
  page `20261028T124051Z_prod`. It does not stop: without the artifacts it
  reads every Horizon attempt as no reply.

`uv run evals prune-artifacts --suite benchmark` keeps the newest 5 run
directories (`--keep-runs`) and deletes the rest. Prune only when no page
you may rebuild and no plain baseline step still needs the older runs: with
draft-5's five runs in place, one more run and a default prune delete the
oldest of them.

## The plain baseline

`tools/plain_baseline.py` asks Sonnet with web search the `2026-draft-5`
questions that judge a reply (253 of the 269) and rescores the agent's own
draft-5 attempts the same way. Per-question calls that the case files
cannot hold without new uids live in
`benchmarks/overlays/2026-draft-5.plain.json`, keyed by uid. Its results go
to `results/plain/`, never to `results/benchmark/`, so the frontend cannot
show them. See [results/plain/README.md](../results/plain/README.md).

## Metrics

`tools/challenge_rollup.py --benchmark` computes these in Python.
`tools/benchmark_page.py` writes the same numbers, plus per-type, per-use-case
and per-question detail, to the page data, and `results/index.json` points
each run at its page. The page's headline is the share of questions right
on **every** trial (`every_time`); `majority` is the North Star below.

- **North Star**: the majority-verdict complete rate, with a Wilson 95%
  interval, over the active members that were measured. A question counts
  when most of its scored attempts were right; an attempt is right when
  every applicable non-info check passed on it. This rule dates from
  2026-10-28. Earlier reports counted a question when each check passed in
  most trials, so their rates are not comparable point for point.
- **Consistency**: of complete answers, the share clean on every trial.
- **Availability**: an attempt that got no reply (the stream stalled,
  dropped or failed) counts as a wrong attempt, and the page reports how
  many of all attempts got none. An attempt the harness could not score (an
  AI reviewer or the state fetch failed) is left out. A member with no
  scored attempt is errored: it leaves the denominator and is reported
  separately. Runs before 2026-10-27 errored the whole member on any
  errored attempt.
- **Per type**: the same rate, and failure modes by primary-failure
  attribution. Each failed member goes to its earliest failing dedicated
  stage in `stage_order` (from its per-check majorities, or, when none
  failed, from the checks that failed on its wrong attempts). Failures only
  on shared checks are `unattributed`. Pass, stages and unattributed add up
  to 100% of measured.
- **Failure modes by standard** (page data only,
  `failure_modes_by_standard` on every group): the same breakdown for each
  accuracy standard the page can show. A question is wrong under
  `every_time` when any trial is wrong, under `majority` when its verdict
  fails (identical to the failure modes above), and under `any_time` when no
  trial is right. A failed verdict counts at its primary failure. A passed
  verdict that was wrong on some trials counts at the earliest dedicated
  stage that failed on any trial (`challenge_rollup.failure_stage`). Each
  question sits at one stage under every standard, so a stricter standard
  only adds questions.
- **Coverage matrix**: type by stage, from `members[].stages`. Those stages
  are the checks a case's expected fields imply when the version is built
  (`stages_for` in `tools/benchmark_sample.py`). The figure checks are not
  among them, so the matrix shows no analysis stage for members scored on
  their figures.

## Version history

Each version's case changes are recorded in detail in
[cases/challenge/CHANGELOG.md](../cases/challenge/CHANGELOG.md).

- **`2026-draft`** (sampled 2026-09-29; one run, 29 September): 20 members
  each of geospatial, dataset, quantification, comparison and trend. Its
  numeric members were scored on retrieval only (no expected numbers, no
  scored explanation), so for those three types its complete rate meant
  "fetched the right data". Replaced by `2026-draft-2`.
- **`2026-draft-2`** (curated 2026-10-01; one run, 1 October): 199 members
  from the proposed v2026 set. Members carry Jobs to be Done numbers,
  impact pathways and user groups. Replaced by `2026-draft-3`.
- **`2026-draft-3`** (curated 2026-10-23; one run, 23 October): 269 members
  from the benchmark sheet of 22 October, with use cases UC1 to UC6 and the
  Portfolio type. 30 rows that need a seeded test account are left out.
  Replaced by `2026-draft-4`.
- **`2026-draft-4`** (2026-10-24 to 2026-10-26): `2026-draft-3` with
  expectations revised after its first run, rebuilt in place several times
  ("Expectation review after the first draft-3 run" and the 2026-10-26
  entries in the CHALLENGE changelog), including eight Ghana questions moved
  to Côte d'Ivoire. Its runs of 24 to 26 October are kept as history.
  Replaced by `2026-draft-5`.
- **`2026-draft-5`** (2026-10-27): every `2026-draft-4` member reviewed
  against "could this answer mislead the user?" ("Draft-5 review" in the
  CHALLENGE changelog). About 170 members gained figure formulas, checked
  against the table each attempt pulls, and two more questions moved off
  Ghana.
