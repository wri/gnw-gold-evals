# tools/: the command-line tools

Thin command-line tools over `src/goldset/`; each adds `src/` to `sys.path` itself. Run any of them as `uv run python tools/<tool>.py`, and `--help` prints its usage. The harness itself is the `evals` command: see [README, Running a suite](../README.md#running-a-suite). The scripts that generate CHALLENGE's numeric cases live in `generation/` ([generation/README.md](../generation/README.md)). Terms are in the [glossary](../docs/glossary.md).

How the tools pick a store or a ledger:

- `check.py`, `coverage_doc.py` and `render_trends.py` take `--suite`, with `challenge` as the default. So do the `--all` modes of `render_html.py` and `render_inspector.py`.
- `report_run.py`, `compose_runs.py` and single-run renders read the store each run records. `--suite` or `--cases-dir` names another.
- `audit_cases.py` has no `--suite`: it checks GOLD's `cases/v2` unless `--cases-dir` names another store.
- An explicit `--cases-dir`, `--results-dir` or `--runs-dir` always wins.

No tool writes a ledger entry by hand: [results/README.md](../results/README.md) has the contract they all follow.

## CHALLENGE and BENCHMARK

| tool | what it does |
|---|---|
| `challenge_rollup.py` | Pass rates for one or more CHALLENGE runs: overall, per set and per cohort, with confidence intervals and the strict rate, which needs every trial clean. It compares them with `cases/challenge/TARGETS.yml` and reports latency. Errored rows leave the denominator and are reported as availability. `--benchmark <manifest>` rolls up a BENCHMARK run: the North Star, consistency, and failure modes per type and stage. |
| `benchmark_sample.py` | Write a sampled BENCHMARK version from the `ready` CHALLENGE cases: `--per-type` members, 20 by default, for each measured query type, and easy and medium only for the aoi and dataset sets. The same store and seed give the same manifest. It never regenerates a frozen version. |
| `benchmark_from_sheet.py` | Write a curated BENCHMARK version from a reviewed sheet export (`--seed <csv> --version <v>`), one member for each sheet row. It also writes each member's sheet facets into the case `notes`, which leaves the uids unchanged. |
| `check_benchmark.py` | Check every manifest in `benchmarks/` against `cases/challenge`: each active member's uid exists, its case is `ready`, and its fixed facets still match the case. A problem fails a frozen version and warns on a draft. Retired versions are checked for structure only. CI runs it. |
| `benchmark_page.py` | Write the page data for one BENCHMARK run, `results/benchmark/pages/<run_id>.json`. Run it on the machine that ran the run, because it reads the run's gitignored artifacts. `--base <run>` fills the members a rerun did not measure from an earlier run. The page's shape is a contract with the frontend ([Page data contract](../benchmarks/README.md#page-data-contract)). |
| `plain_baseline.py` | Plain Sonnet with web search against Horizon on BENCHMARK `2026-draft-5`, scored on the reply only. Output goes to `results/plain/`, never to `results/benchmark/`. The `ask` and `score` steps spend API budget: run them only with the repo owner's go-ahead ([results/plain/README.md](../results/plain/README.md)). |

## Case store

| tool | what it does |
|---|---|
| `check.py` | Verify a store: every uid matches its case, every case is valid, and the manifest is current. `--fix` recomputes the uids and the manifest after an edit. CI runs it without `--fix` on `cases/v1`, `cases/v2` and `cases/challenge`. |
| `coverage_doc.py` | Regenerate a store's `COVERAGE.md`, `coverage.json` and `cases_index.json` from the store and the catalogue snapshot. The evals dashboard reads the two JSON files. CI's `--check` fails if any of the three is out of date. |
| `sync_zeno_catalog.py` | Refresh `cases/zeno_catalog.json`, the snapshot of project-zeno's dataset catalogue, from `origin/main` of a sibling `../project-zeno` checkout. `--zeno` names another checkout. Then run `coverage_doc.py` for each store ([cases/README.md, The catalogue snapshot](../cases/README.md#the-catalogue-snapshot)). |

The commands to run after a case edit are owned by [cases/README.md, After an edit](../cases/README.md#after-an-edit).

## Results and reports

| tool | what it does |
|---|---|
| `build_run_index.py` | Regenerate `results/index.json` from the committed and staged runs and from `benchmarks/*.json`. Run it after you stage a run and after any manifest change. `--check` is the CI freshness gate ([Derived index](../results/README.md#derived-index)). |
| `flakiness.py` | For one multi-trial run, each check's mean, standard deviation and flip count across trials. `--per-case` lists the cases that flapped. Partial samples are flagged INSUFFICIENT DATA. Use it before you call a failure real. |
| `report_run.py` | A Markdown summary of one run: row verdicts, the bucket table, the reconciliation line and diagnostics such as judge errors and slow rows. Use it for a quick read in the terminal or to paste into a pull request. |
| `render_html.py` | A standalone HTML report of one run, written to `results/<suite>/reports/`. `--all` builds the page for every run in a ledger. |
| `render_inspector.py` | An HTML matrix of every case against every check, with expected and measured values. `--all` builds the page for every run in a ledger. |
| `render_trends.py` | Pass-rate trends across every run in a ledger, one line per `ff`. Never read a trend across differing `ff`. |

HTML reports have been committed for the GOLD ledger only, in `results/gold/reports/`.

## After a run

The steps after a committed run belong to each suite: [CHALLENGE](../cases/challenge/README.md#after-every-run), [BENCHMARK](../benchmarks/README.md#after-a-run) and the [GOLD legacy copy](../docs/gold-legacy.md#after-a-gold-run).

## GOLD legacy copy tools

These tools were built for GOLD. Keep them while the GOLD legacy copy is here.

| tool | what it does |
|---|---|
| `diff_runs.py` | Count regressions, recoveries, data bumps and coverage changes between two runs, over the cases both scored. `--fail-on-regression` and `--fail-on-coverage-loss` make it the release gate ([docs/gold-legacy.md](../docs/gold-legacy.md#regression-diffs)). |
| `find_baseline.py` | Print the newest run in a ledger that matches a given run on environment, `ff`, trial count and case store, or exit non-zero with the reason. The CI release gate uses it. |
| `compose_runs.py` | Combine a full run with scoped reruns into one current picture without editing either run file ([Composing](../results/README.md#composing-a-current-picture-across-runs)). It also reads CHALLENGE runs, and refuses BENCHMARK runs. |
| `audit_cases.py` | Check `cases/v2` against the GOLD authoring rules: depth, coverage floors and the DON'T list. CI runs it with `--strict`, which fails on depth and DON'T violations ([The audit gate](../cases/GOLD-AUTHORING.md#the-audit-gate)). |

### Legacy tools

Cases used to live in a Google Sheet, and runs used to go through gnw-evals. Both are retired: the case store is the source of truth, and `evals run` is the only runner. Each tool below is kept for the job in its last column.

| tool | what it was for | what it is still for |
|---|---|---|
| `import_sheet.py` | Imported GOLD sheet tabs into the store; `cases/v1` is that import. | **Keep it: it is also the loader for CHALLENGE's seed CSVs** ([seeds/README.md](../seeds/README.md)). It bulk-loads cases from a CSV with the sheet's columns (`--csv`; `--set` adds a CHALLENGE set). It writes to `cases/v2` unless `--cases-dir` is given. Never import a seed again: a second import overwrites every edit made since. |
| `export_sheet_csv.py` | Wrote the store as CSVs for the sheet. | A spreadsheet view of the cases for a reviewer who wants one (`--out` is required; multi-turn cases are skipped). |
| `export_csv.py` | Wrote single-turn cases as a gnw-evals test CSV. | Running GOLD cases through the gnw-evals command, for example to compare its verdict with `evals run` on the same build. |
| `ingest_run.py` | Converted gnw-evals runs into ledger run files; the GOLD runs whose `harness.repo` is `gnw-evals` came in this way. | Importing any other gnw-evals run. `evals run` writes its own run files. |
| `parity.py` | Showed that the harness gives the same verdicts as gnw-evals on the same build. | Repeating that check if you suspect the two harnesses score a shared check differently. |

## Generated or hand-edited

A generated file is written by a tool and never edited by hand: change its inputs and run the tool again. CI checks several of them for freshness, so a stale one fails the pull request.

| File | Kind | Written by |
|---|---|---|
| `cases/<store>/MANIFEST.json` | generated | `tools/check.py --fix`; CI checks it |
| `cases/<store>/COVERAGE.md`, `coverage.json`, `cases_index.json` | generated | `tools/coverage_doc.py`; CI runs `--check` |
| `cases/zeno_catalog.json` | generated | `tools/sync_zeno_catalog.py`, from project-zeno's dataset catalogue |
| `results/<suite>/runs/<run_id>.json` | generated | `evals run` only; older GOLD runs by `tools/ingest_run.py` |
| `results/index.json` | generated | `tools/build_run_index.py`; CI runs `--check` |
| `results/benchmark/pages/<run_id>.json` | generated | `tools/benchmark_page.py` |
| `results/plain/` runs, references, scores and reports | generated | `tools/plain_baseline.py` ([results/plain/README.md](../results/plain/README.md)) |
| `results/<suite>/reports/*.html` | generated | `tools/render_html.py`, `render_inspector.py`, `render_trends.py` |
| Case YAML, `cases/<store>/.../<id>.yaml` | hand-edited or tool-written | by hand, `tools/import_sheet.py` or `generation/promote_cases.py`. `tools/check.py --fix` rewrites the `uid:` line, and `tools/benchmark_from_sheet.py` writes the BENCHMARK membership notes |
| `benchmarks/<version>.json` | tool-written, errata by hand | `tools/benchmark_sample.py` or `tools/benchmark_from_sheet.py`. No tool writes `errata[]` entries; both tools keep the existing ones when they rebuild a draft |
| `benchmarks/overlays/2026-draft-5.plain.json` | hand-edited | the plain baseline's calls per question, reviewed by the repo owner |
| `generation/manifests/*.csv`, `generation/<dataset>/*.md`, `generation/dataset_config.py` | hand-edited | the inputs of the generation pipeline ([generation/README.md](../generation/README.md)) |
| `seeds/*.csv` | hand-edited | sheet exports and hand-made CSVs ([seeds/README.md](../seeds/README.md)) |
| `cases/challenge/TARGETS.yml` | hand-edited | CHALLENGE's target rates |
| `results/<suite>/recommendations/*.md`, `results/gold/campaigns/*.md` | hand-written | the written analysis of a run, and write-ups of multi-run efforts |
