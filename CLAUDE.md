# CLAUDE.md

Rules and routing for Claude Code and other AI coding agents in this repo. What the repo is and how it works: [README.md](README.md). Terms: [docs/glossary.md](docs/glossary.md).

## Routing

- Find the job in [README, Start here](README.md#start-here). It names the one doc that owns the procedure and the skill that walks it. Follow that doc; do not rebuild a procedure from this file.
- CHALLENGE, BENCHMARK and the plain baseline are live here. GOLD lives in wri/project-zeno `evals/gold/`: do new GOLD work there. `cases/v1`, `cases/v2`, `results/gold/`, the skills `gold-run`, `new-case`, `release-gate` and `triage-run`, and the manual CI staging run are a legacy copy ([docs/gold-legacy.md](docs/gold-legacy.md)). Rules marked GOLD apply to that copy only.
- Where a rule below rests on a design decision, its reason is given with it.

## Commands

```bash
uv sync                                          # install (Python 3.11+)
uv run pytest -q                                 # every test; no network
uv run pytest tests/test_canonical.py -q         # one file
uv run ruff check src tools tests generation     # lint, as CI runs it
uv run evals run --suite challenge --dry-run     # list a run's cases; no API calls
```

## Rules for runs

- **Name the suite.** Pass `--suite challenge`, `--benchmark benchmarks/<version>.json` or `--suite gold`. There is no default, so a run never lands in another suite's ledger.
- **Tiers, profile and comparability** are owned by [README, Running a suite](README.md#running-a-suite). In short: smoke runs have 1 trial and are never committed; canonical runs have 3 trials and the default profile; never compare or trend across differing `ff`, trial count or environment.
- **Never commit a smoke run or an `--env local` run.** A local stack matches neither staging nor prod. The ledgers hold earlier exceptions, such as CHALLENGE's 1-trial runs of 2026-09-01 and local runs of 2026-09-25. Do not add more.
- **Ask the user before you spend API budget** with `generation/generate_cases.py` or the plain baseline's `ask` and `score` steps. `generate_cases.py --dry-run` and `ask --dry-run` cost nothing.
- **Pass `--note`** when check semantics changed since the previous run, so the change is not read as agent movement.
- **Finish a committed run.** It is done only when its suite's after-run steps are done: [CHALLENGE](cases/challenge/README.md#after-every-run), [BENCHMARK](benchmarks/README.md#after-a-run). The `challenge-cases` and `benchmark-run` skills walk them. Show the user what will be committed before you commit.
- **Regenerate `results/index.json`** with `tools/build_run_index.py` after you stage a run, and after any manifest change: a rebuild, an erratum or a freeze. The index reads the staged runs and `benchmarks/*.json`, and CI checks that it is fresh.
- **The ledger is written by the harness only.** Never hand-write, edit, backfill or splice a run file: its header describes how its own rows were produced. A re-ingest after a tooling fix means deleting the file visibly in a reviewable commit. To combine a full run with a scoped rerun, use `tools/compose_runs.py`, or `tools/benchmark_page.py --base` for BENCHMARK.
- **The BENCHMARK page data is a cross-repo contract.** wri/project-zeno-next parses it strictly, so change its shape only together with the frontend ([Page data contract](benchmarks/README.md#page-data-contract)).
- **The plain baseline writes to `results/plain/` only**, never to `results/benchmark/`, so the frontend can never show it ([results/plain/README.md](results/plain/README.md)).

## Rules for cases

- **Never fix a case to make it pass.** CHALLENGE cases are expected to fail today: a failure is data, not a defect, and never a regression.
- **Never edit a member of a frozen BENCHMARK version.** Void it with an erratum and add new CHALLENGE cases. No version is frozen yet; editing a member of a draft drops it from the draft until the draft is rebuilt, and `tools/check_benchmark.py` warns.
- **Run the after-edit commands** for the store after any change to a case file, and commit their output with the edit ([cases/README.md, After an edit](cases/README.md#after-an-edit)). CI fails the pull request otherwise.
- **Generated files are never hand-edited.** Change the inputs and rerun the tool. [tools/README.md, Generated or hand-edited](tools/README.md#generated-or-hand-edited) lists which files are which.
- **A pull request that changes cases says which and why.** The uid records what changed; only the pull request records the reason.
- **Never import a seed CSV again, and never rename one.** A second import writes the CSV's values over every edit made since, and case notes and manifests record seed file names ([seeds/README.md](seeds/README.md#rules)).
- **`tools/import_sheet.py` writes to `cases/v2` unless `--cases-dir` is given.** Pass `--cases-dir cases/challenge` for CHALLENGE.
- **Plain-baseline calls per question go in `benchmarks/overlays/2026-draft-5.plain.json`**, keyed by uid, never in the case files: an edit to a member case would drop it from the draft.
- **Status changes follow the [status lifecycle](cases/README.md#status-lifecycle).** Parking needs a dated `notes.status_reason`.
- **GOLD:** edit `cases/v2` only. `cases/v1` is frozen, and `tests/test_v1_frozen.py` fails if it changes.

## The identity system

**WARNING**: critical for every ledger. Do not break it. Every result in `results/<suite>/runs/` is keyed on a case's uid, and every BENCHMARK manifest lists its members by uid, so the uid is the only link between a score and the exact case content it measured. If the hash changes for content that did not change, every committed run stops matching its cases, every BENCHMARK version loses its members, and the history is lost. If the hash misses a change that did happen, old scores are attributed to the edited case, and comparisons treat two different tests as one. `src/goldset/canonical.py` defines the hashing.

- **uid** = `sha256(canonical_json(query + non-empty expected values))[:16]`. Changing the query or any `expected` value mints a new uid: that is the versioning mechanism, not an error. `status`, `set`, `group`, `notes`, key order, leading and trailing whitespace, and line endings never affect it, so triage never mints a version.
- **Multi-turn uids** hash every turn's query and expected values in order, so reordering turns mints a new uid. In `cases/v2` each turn's `deltas` are hashed too, because its `MANIFEST.json` sets `uid_includes_deltas`. The frozen `cases/v1` uids leave them out.
- **The hash covers every expected field, scored or not**, such as `dataset_name`, which no check reads. An unscored field is still part of what the case asserts, and a check may start reading it later. If the hash skipped it, an edit to it would change the case without a new uid. Do not narrow the hash to scored fields, and do not move expectations into `notes` to avoid a new uid.
- **caseset_version**, in each store's `MANIFEST.json`, hashes the sorted uids. Comparisons run over the uids two runs share.
- **`id`**, such as `ch-aoi-001`, is the stable name across versions.
- `tests/test_schema.py` validates every case file against `schema/case.schema.json`, so a malformed case fails the tests, not a run.

## Dataset catalogue

`cases/zeno_catalog.json` is a committed snapshot of project-zeno's dataset catalogue, so CI needs no network. Refresh it with the `sync-catalog` skill when project-zeno's datasets change ([cases/README.md, The catalogue snapshot](cases/README.md#the-catalogue-snapshot)). `src/goldset/groundtruth/catalog.py` builds ground-truth requests from the snapshot. It hardcodes the payload shape and the area type map from project-zeno's `_build_payload` and `_get_aoi_type`, so change those only after a reviewed upstream change.

## Module map

Under `src/goldset/`; the tools in `tools/` are thin command-line wrappers ([tools/README.md](tools/README.md)).

| Module | Holds |
|---|---|
| `canonical.py` | uid and caseset_version hashing |
| `store.py` | the `Case` dataclass, case YAML read and write, manifests; unknown top-level keys are rejected |
| `suites.py` | which store and ledger each suite uses |
| `templates.py` | date tokens in queries, resolved when a run starts |
| `adapter.py`, `eval_types.py` | a case's expectations as the evaluators' typed input, and the result type |
| `runner/` | agent API calls, multi-turn threads, raw artifact capture |
| `evaluators/`, `registry.py` | the checks, and the order the runner calls them in |
| `buckets.py` | the bucket map, the info-only set, attempt and row verdicts |
| `ledger.py` | run records, run_ids, majorities, partial files |
| `benchmark.py` | the BENCHMARK manifest contract |
| `groundtruth/` | run-time ground truth: selectors, requests, the fetch before the first trial |
| `plain/` | the plain baseline's logic |
| `models.py`, `judge_config.py` | the LLM judge client and backend |
| `cli.py` | the `evals` command, also installed as `gold` |

## Working agreements

- Numbers in code; structure and semantics to the judge. No LLM judge is ever asked to do arithmetic.
- Every check's documentation says whether a missing input scores `null` or `0.0`, and why.
- A new judged check starts info-only. It gates only once it shows a standard deviation of at most 0.10 over a 3-trial run (`tools/flakiness.py`). The three judged checks inherited from gnw-evals (`agent_answer`, `expected_text_match`, `clarification_requested`) already gated and still do.
- Judge structured outputs put the reasoning field before the score field.
