# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Terms are defined in the [README glossary](README.md#glossary).

## What this repo is

GOLD is the capability regression suite for the GNW / Project Zeno agent: cases, harness and results ledger in one versioned repo. It answers one question per release: *did an agent change break a capability that used to work?* The headline is a **regression count**, never a mean score, and determinism outranks realism in every design call.

Before proposing changes, read `README.md`, `cases/README.md` and `results/README.md`. Where a rule below rests on a design decision, its reason is given with it.

## The CHALLENGE set (second case set — quality rates, not regressions)

`cases/challenge/` houses the CHALLENGE set, the quality/accuracy
counterpart to GOLD (plan of record: `PRDs/challenge-set.md` in the GNW
workspace). Everything about it that differs from GOLD is deliberate and
documented in `cases/challenge/README.md` — read that before touching the
set. The short version:

- The store is hierarchical — **set → cohort → case** — via the optional
  `set:` case field (`cases/challenge/<set>/<cohort>/<id>.yaml`). Sets:
  `aoi` (cohorts = prompt classes) and the numeric intents
  `quantification`/`trend`/`comparison` (cohorts = datasets; ported from
  gnw-evals eval-metrics-slice-1, authored via `generation/` — see
  `generation/README.md`), and `dataset` (dataset-selection prompts, phrased as
  "show X on the map", that should run `pick_dataset` alone; hand-authored in
  `seeds/challenge-dataset-v1.csv`), plus `monitoring` and `causal` (benchmark
  v2026 cases, `seeds/benchmark-v2026-proposed.csv`; Batch 4 in the README),
  `portfolio` (many areas at once, from the v2026 benchmark sheet; Batch 5) and
  `refusal` (how the agent declines: should-decline, alternatives,
  should-answer and app-help cohorts; `seeds/challenge-refusal-v1.csv`;
  Batch 6). Run one set with `gold run --set <name>`. Like
  `group`, `set` is never hashed into the uid.
- Verdicts are **pass rates per set and cohort** (`tools/challenge_rollup.py`),
  never regression counts. Many cases are *expected to fail*: do not triage
  those failures as regressions, and never "fix" a case to make it pass.
- Canonical published series: **prod, default profile, 3 trials**, run with
  `--cases-dir cases/challenge --results-dir results/challenge
  --status-exclude "not doing,todo"`. Its ledger lives under
  `results/challenge/` and never mixes with GOLD's runs, trends, or diffs.
- The after-run ritual applies to CHALLENGE too, adapted to rates: rollup,
  then a recommendations doc in `results/challenge/recommendations/<run_id>.md`,
  then commit run + rollup + recommendations together (see "After every
  run" in `cases/challenge/README.md`).
- The GOLD skills (gold-run, case-edit, new-case, release-gate, triage-run)
  and `audit_cases.py --strict` apply to `cases/v2` only.
- Identity and ledger discipline are unchanged: after any case edit, run
  `tools/check.py --fix --cases-dir cases/challenge` and
  `tools/coverage_doc.py --cases-dir cases/challenge`, and commit both with
  the edit (CI gates both).

## BENCHMARK (frozen subset of CHALLENGE — the North Star exam)

`benchmarks/<version>.json` is a **uid manifest** over `cases/challenge`, not
a case store: read `benchmarks/README.md` first. Key rules:

- Membership is by uid, and type/cohort/difficulty/stages are frozen per
  member. Editing a member case drops it (new uid); `tools/check_benchmark.py`
  (CI) errors on frozen versions and warns on drafts. Never edit a member
  of a frozen version: void it with an erratum and add new CHALLENGE cases.
- Build a version by sampling (`tools/benchmark_sample.py --version <v>`:
  20 per measured type; aoi and dataset easy+medium only) or by curating
  from a reviewed sheet (`tools/benchmark_from_sheet.py --seed <csv>
  --version <v>`: one member per row, with its use cases UC1–UC6, or jobs,
  impact pathways and user groups for the older sheet layout). Current
  version: `2026`, frozen on 2026-11-18 from `2026-draft-5` (curated from
  the BEF sheet, 269; reviewed on 2026-10-27 by "could this answer mislead
  the user?", with figure formulas checked against each attempt's own
  pull). No draft is open. Regeneration is
  deliberate, never CI's. Frozen manifests are never regenerated.
- Rolling-window questions use run-relative date tokens in expected values
  (`{run-30d}`, `{run}`, `{month_start}`, `{last_month_start}`,
  `{last_month_end}`) plus `date_tolerance_days`; the uid hashes the token.
- Run with `gold run --benchmark benchmarks/<v>.json --env prod --trials 3`
  (no ff); results go to `results/benchmark/`. Only canonical runs are trend
  points (`results/index.json` flags them). Roll up with
  `tools/challenge_rollup.py --benchmark benchmarks/<v>.json <run>.json`.
- Then write the page data the FE accuracy-benchmarks page reads:
  `tools/benchmark_page.py results/benchmark/runs/<run_id>.json` writes
  `results/benchmark/pages/<run_id>.json`. It needs the run's local agent
  artifacts (gitignored), so do it on the machine that ran the run, and
  commit it with the run before regenerating `results/index.json`.
- To rerun only members revised since a run, add `--missing-from
  <run>.json` to `gold run --benchmark`, then write the page with
  `benchmark_page.py <rerun>.json --base <run>.json` (both flags repeat for
  a chain of reruns); the index judges the combination canonical (`benchmarks/README.md`, "Rerunning revised
  members only").
- After an erratum or a freeze, regenerate `results/index.json`.
- To add a language to the languages companion (`2026-languages`), follow
  "Adding a language" in `benchmarks/README.md`. A new language code needs a
  harness change first, and the two sides of a pair are never edited apart.
- An attempt that got no reply (`no_answer` on its trial: the stream sent
  nothing for 240 s, hit the wall clock, dropped or returned a 5xx) is a
  wrong attempt. An attempt the harness could not score keeps its trial
  `error` and is left out; a member errors only when no attempt was scored
  (AJ, 2026-10-27). Runs recorded before then errored the whole member on
  any errored attempt, so a member can move from error to fail across that
  date.

## Commands

```bash
uv sync                                                        # install (Python 3.11+)
uv run pytest -q                                               # full suite, no network
uv run pytest tests/test_canonical.py -q                       # one file
uv run pytest tests/test_store.py::test_write_read_round_trip  # one test
uv run ruff check src tools tests                              # lint, as CI runs it

# Runs. Tokens: STAGING_API_TOKEN / PROD_API_TOKEN, else API_TOKEN;
# .env is loaded automatically (README "Setup").
uv run gold run --env staging --build "<label>"              # smoke: 1 trial, 10 workers
uv run gold run --env staging --trials 3 --build "<label>"   # official / release gate
uv run gold run --resume <run_id>                            # finish a killed run
uv run gold run --dry-run                                    # list selected cases, no API calls

# After any case edit: all three, committed with the edit
uv run python tools/check.py --fix
uv run python tools/coverage_doc.py
uv run python tools/audit_cases.py --strict

uv run python tools/sync_zeno_catalog.py   # refresh the dataset catalogue snapshot
```

## Rules for runs

Procedures and reasons: README ["Running the set"](README.md#running-the-set) and ["After a run"](README.md#after-a-run).

- **Profile.** Run the default profile (no `--ff`) unless the cases under test need a feature still behind `experimental`. Never diff or trend across differing `ff`; the run_id suffix shows it (`_prod` versus `_prod_experimental`).
- **Two tiers.** A smoke run (1 trial, the CLI default) is never committed, diffed or used as a baseline. Anything that produces a regression count or becomes a baseline uses `--trials 3`.
- **Comparable runs only.** Both sides of a diff need the same `ff`, the same trial count and the same environment ([Comparing two runs](results/README.md#comparing-two-runs)). If no comparable run exists, say so rather than diffing against something else.
- **Methodology note.** If check semantics changed since the previous run, pass `--note "<what changed>"` when starting `gold run`, so diffs are not read as agent changes.
- **Ground truth.** Cases with `expected.ground_truth` fetch their expected figures from the production analytics API, whatever `--env`, once per run before the first trial. A failed fetch aborts the run before any agent call, so nothing is written. Because every run fetches afresh, two runs can differ with no agent change; `diff_runs.py` files those flips as data bumps, never regressions ([Run-time ground truth](cases/README.md#run-time-ground-truth-ground_truth)).
- **Timeouts.** A block of `ReadTimeout`s late in a run usually means too many workers (runs record `workers` and `trial_timeout` so this can be traced). Lower `--workers` before blaming the agent.
- **Finish official runs.** An official run is not done until the four steps in README "After a run" are complete. Show the user what will be committed before committing. After `git add`-ing the run JSON, regenerate the run index (`uv run python tools/build_run_index.py`; it enumerates tracked and staged files, so add the run first) and commit `results/index.json` in the same commit; CI gates its freshness.
- **The ledger is written by the harness only.** Never hand-write, edit, backfill or splice a run file; a re-ingest after a tooling fix means deleting the file visibly in a reviewable commit. To combine a full run with a scoped re-run, use `tools/compose_runs.py` ([results/README.md](results/README.md)).

## Rules for cases

**COVERAGE.md must move with the case set.** Any change to a case file (query, expected values, status, group, notes, or a new or deleted case) is incomplete until `tools/check.py --fix` and `tools/coverage_doc.py` have run and their output is committed with the edit; run `tools/audit_cases.py --strict` as well. CI fails the PR on a stale uid or manifest, a stale COVERAGE.md (a changed `Last updated` date alone does not count) or an audit violation. Procedure: README ["Changing cases"](README.md#changing-cases); the `case-edit` and `new-case` skills have the steps.

- For GOLD, edit `cases/v2` only. `cases/v1` is frozen, and `tests/test_v1_frozen.py` fails if it changes.
- Status changes follow [Status lifecycle](cases/README.md#status-lifecycle). In particular, `done` needs a passing 3-trial run at the case's current uid, cited by run_id in `notes.status_reason`, and parking needs a dated `status_reason`.

## The identity system

**WARNING**: critical for the ledger. Do not break it. Every result in `results/gold/runs/` is keyed on a case's uid, so the uid is the only link between a score and the exact case content it was measured against. If the hash changes for content that did not change, every committed run stops matching its cases and the regression history is lost. If the hash misses a change that did happen, old scores are silently attributed to the edited case, and diffs compare two different tests as if they were one. `src/goldset/canonical.py` defines the hashing; the README glossary defines [uid](README.md#uid) and [caseset_version](README.md#caseset-version).

- **uid** = `sha256(canonical_json(query + non-empty expected values))[:16]`. Changing the query or any `expected` value mints a new uid: that is the versioning mechanism, not an error. `status`, `group`, `notes`, key order, leading and trailing whitespace, and line endings never affect it, so triage never mints a version.
- **A case's `language`** (`es`, `id`, `pt` or `fr`) is hashed too, because it sets how `figure_match` reads the reply's numbers. English is the default, is never written and is left out of the hash, so uids minted before the field existed do not change. `twin` is a pointer to the English case and is never hashed.
- **Multi-turn uids** hash every turn's query and expected values in order, so reordering turns mints a new uid. In v2, each turn's `deltas` are hashed too (its `MANIFEST.json` sets `uid_includes_deltas`); frozen v1 uids leave them out.
- **The hash covers every expected field, scored or not** (for example `dataset_name`, which no check reads). An unscored field is still part of what the case asserts, and a check may start reading it later; if the hash skipped it, an edit to it would change the case without a new uid. Do not narrow the hash to scored fields, and do not move expectations into `notes` to avoid uid churn.
- **caseset_version** (in each store's `MANIFEST.json`) hashes the sorted uids. Results key on uid; diffs run over the uids two runs share.
- **`id`** (such as `1-030`) is the stable lineage handle across versions.
- `tests/test_schema.py` validates every case file against `schema/case.schema.json`, so a malformed case fails the suite, not a run.

## Dataset coverage against project-zeno

COVERAGE.md's "Dataset coverage" section measures the case set against the agent's dataset catalogue (`src/agent/datasets/catalog/*.yml` in wri/project-zeno), read from the committed snapshot `cases/zeno_catalog.json` so that CI needs no network. When project-zeno adds, removes or changes a dataset, run `tools/sync_zeno_catalog.py`, then `tools/coverage_doc.py`, and commit both together. The sync reads `origin/main` of the sibling checkout `../project-zeno` with `git show` and never touches its working tree (`--zeno` and `--ref` override the defaults). The `sync-catalog` skill has the steps.

The snapshot is also the ground-truth request table. It carries each dataset's `analytics_api_endpoint`, `content_date`, `content_date_fixed`, `start_date` and `end_date`, and `src/goldset/groundtruth/catalog.py` builds every analytics request from them, so a dataset whose window grows upstream cannot leave ground truth computed over the old one. Payload shape, the 4/8/10 `intersections` split and the AOI type map have no YAML form in project-zeno (they are code in its `_build_payload` and `_get_aoi_type`), so `catalog.py` hardcodes them and they change only with a reviewed upstream change. A dataset missing from the snapshot has no request, and a case that needs it fails the run loudly.

## Architecture

- `src/goldset/`: the library.
  - `canonical.py`: uid and caseset_version hashing.
  - `store.py`: the `Case` dataclass, case YAML read and write, manifests. Unknown top-level keys are rejected on read.
  - `templates.py`: `{token}` dates in queries, resolved when a run starts (the uid hashes the token).
  - `adapter.py`, `eval_types.py`: turn a case's expectations into the harness's typed inputs, and define its result type.
  - `runner/`: API calls (`api.py`), multi-turn threads (`multiturn.py`), raw artefact capture (`artifacts.py`).
  - `evaluators/` and `registry.py`: the checks, and the order the runner calls them in.
  - `models.py`: the LLM judge client; `judge_config.py`: the judge backend (`--judge-backend`) and the model name recorded on runs.
  - `groundtruth/`: run-time ground truth: selector parsing, analytics requests built from the catalogue snapshot, and the fetch before the first trial.
  - `buckets.py`: the bucket map, the info-only set, row verdicts, and the reconciliation of implied with evaluated checks.
  - `ledger.py`: run records, run_ids, majority verdicts and partial files.
  - `cli.py`: the `gold` command.
- `tools/`: thin CLIs over `src/goldset` (they add `src/` to `sys.path`); see `tools/README.md`.
- `cases/v{1,2}/<group>/<id>.yaml`: one case per file, so review, blame and revert work per case. `expected:` holds the hashed expectations (keys without the `expected_` prefix); `notes:` holds unhashed annotations.
- `results/`: the committed per-run JSON ledgers, one subtree per set (`results/gold/`, `results/challenge/`); contract in `results/README.md`. Checks are tri-state `1.0`/`0.0`/`null`.
- `schema/case.schema.json`: the case contract. `templates/`: the HTML report templates.
- The case store is the source of truth. The Google Sheet it was first imported from is retired; README ["Legacy tools"](README.md#legacy-tools) covers the remaining bridge tools.

## Working agreements

- Numbers in code; structure and semantics to the judge. No LLM judge is ever asked to do arithmetic.
- Every check's documentation decides whether a missing input scores `null` (not evaluated) or `0.0` (fail), and says why.
- A new judged check starts info-only and gates only once it shows a standard deviation of at most 0.10 over a 3-trial run (`tools/flakiness.py`). The three judged checks inherited from gnw-evals (`agent_answer`, `expected_text_match`, `clarification_requested`) already gated and still do.
- Judge structured outputs put the reasoning field before the score field.
