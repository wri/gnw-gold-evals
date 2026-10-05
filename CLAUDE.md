# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Terms are defined in the [README glossary](README.md#glossary).

## What this repo is

GOLD is the capability regression suite for the GNW / Project Zeno agent: cases, harness and results ledger in one versioned repo. It answers one question per release: *did an agent change break a capability that used to work?* The headline is a **regression count**, never a mean score, and determinism outranks realism in every design call.

Before proposing changes, read `README.md`, `cases/README.md` and `results/README.md`. Where a rule below rests on a design decision, its reason is given with it.

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
- **Timeouts.** A block of `ReadTimeout`s late in a run usually means too many workers (runs record `workers` and `trial_timeout` so this can be traced). Lower `--workers` before blaming the agent.
- **Finish official runs.** An official run is not done until the four steps in README "After a run" are complete. Show the user what will be committed before committing.
- **The ledger is written by the harness only.** Never hand-write, edit, backfill or splice a run file; a re-ingest after a tooling fix means deleting the file visibly in a reviewable commit. To combine a full run with a scoped re-run, use `tools/compose_runs.py` ([results/README.md](results/README.md)).

## Rules for cases

**COVERAGE.md must move with the case set.** Any change to a case file (query, expected values, status, group, notes, or a new or deleted case) is incomplete until `tools/check.py --fix` and `tools/coverage_doc.py` have run and their output is committed with the edit; run `tools/audit_cases.py --strict` as well. CI fails the PR on a stale uid or manifest, a stale COVERAGE.md (a changed `Last updated` date alone does not count) or an audit violation. Procedure: README ["Changing cases"](README.md#changing-cases); the `case-edit` and `new-case` skills have the steps.

- Edit `cases/v2` only. `cases/v1` is frozen, and `tests/test_v1_frozen.py` fails if it changes.
- Status changes follow [Status lifecycle](cases/README.md#status-lifecycle). In particular, `done` needs a passing 3-trial run at the case's current uid, cited by run_id in `notes.status_reason`, and parking needs a dated `status_reason`.

## The identity system

**WARNING**: critical for the ledger. Do not break it. Every result in `results/runs/` is keyed on a case's uid, so the uid is the only link between a score and the exact case content it was measured against. If the hash changes for content that did not change, every committed run stops matching its cases and the regression history is lost. If the hash misses a change that did happen, old scores are silently attributed to the edited case, and diffs compare two different tests as if they were one. `src/goldset/canonical.py` defines the hashing; the README glossary defines [uid](README.md#uid) and [caseset_version](README.md#caseset-version).

- **uid** = `sha256(canonical_json(query + non-empty expected values))[:16]`. Changing the query or any `expected` value mints a new uid: that is the versioning mechanism, not an error. `status`, `group`, `notes`, key order, leading and trailing whitespace, and line endings never affect it, so triage never mints a version.
- **Multi-turn uids** hash every turn's query and expected values in order, so reordering turns mints a new uid. In v2, each turn's `deltas` are hashed too; frozen v1 uids leave them out.
- **The hash covers every expected field, scored or not** (for example `dataset_name`, which no check reads). An unscored field is still part of what the case asserts, and a check may start reading it later; if the hash skipped it, an edit to it would change the case without a new uid. Do not narrow the hash to scored fields, and do not move expectations into `notes` to avoid uid churn.
- **caseset_version** (in each store's `MANIFEST.json`) hashes the sorted uids. Results key on uid; diffs run over the uids two runs share.
- **`id`** (such as `1-030`) is the stable lineage handle across versions.
- `tests/test_schema.py` validates every case file against `schema/case.schema.json`, so a malformed case fails the suite, not a run.

## Dataset coverage against project-zeno

COVERAGE.md's "Dataset coverage" section measures the case set against the agent's dataset catalogue (`src/agent/datasets/catalog/*.yml` in wri/project-zeno), read from the committed snapshot `cases/zeno_catalog.json` so that CI needs no network. When project-zeno adds, removes or changes a dataset, run `tools/sync_zeno_catalog.py`, then `tools/coverage_doc.py`, and commit both together. The sync reads `origin/main` of the sibling checkout `../project-zeno` with `git show` and never touches its working tree (`--zeno` and `--ref` override the defaults). The `sync-catalog` skill has the steps.

## Architecture

- `src/goldset/`: the library.
  - `canonical.py`: uid and caseset_version hashing.
  - `store.py`: the `Case` dataclass, case YAML read and write, manifests. Unknown top-level keys are rejected on read.
  - `templates.py`: `{token}` dates in queries, resolved when a run starts (the uid hashes the token).
  - `adapter.py`, `eval_types.py`: turn a case's expectations into the harness's typed inputs, and define its result type.
  - `runner/`: API calls (`api.py`), multi-turn threads (`multiturn.py`), raw artefact capture (`artifacts.py`).
  - `evaluators/` and `registry.py`: the checks, and the order the runner calls them in.
  - `models.py`: the LLM judge client.
  - `buckets.py`: the bucket map, the info-only set, row verdicts, and the reconciliation of implied with evaluated checks.
  - `ledger.py`: run records, run_ids, majority verdicts and partial files.
  - `cli.py`: the `gold` command.
- `tools/`: thin CLIs over `src/goldset` (they add `src/` to `sys.path`); see `tools/README.md`.
- `cases/v{1,2}/<group>/<id>.yaml`: one case per file, so review, blame and revert work per case. `expected:` holds the hashed expectations (keys without the `expected_` prefix); `notes:` holds unhashed annotations.
- `results/`: the committed ledger; contract in `results/README.md`. Checks are tri-state `1.0`/`0.0`/`null`.
- `schema/case.schema.json`: the case contract. `templates/`: the HTML report templates.
- The case store is the source of truth. The Google Sheet it was first imported from is retired; README ["Legacy tools"](README.md#legacy-tools) covers the remaining bridge tools.

## Working agreements

- Numbers in code; structure and semantics to the judge. No LLM judge is ever asked to do arithmetic.
- Every check's documentation decides whether a missing input scores `null` (not evaluated) or `0.0` (fail), and says why.
- A new judged check starts info-only and gates only once it shows a standard deviation of at most 0.10 over a 3-trial run (`tools/flakiness.py`). The three judged checks inherited from gnw-evals (`agent_answer`, `expected_text_match`, `clarification_requested`) already gated and still do.
- Judge structured outputs put the reasoning field before the score field.
