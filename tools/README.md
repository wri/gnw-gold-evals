# tools/: the CLI surface

Terms are defined in the [README glossary](../README.md#glossary).

Thin CLIs over `src/goldset/` (each adds `src/` to `sys.path` itself). Run
any of them as `uv run python tools/<tool>.py`; `--help` prints its usage.
The harness itself is the `gold` command (`uv run gold run`, see
[Running the set](../README.md#running-the-set)). No tool hand-writes a
ledger entry: [results/README.md](../results/README.md) has the contract
they all follow.

## Case store

| tool | what it does |
|---|---|
| `check.py` | Verify the case store: every uid matches its case, every case is valid, and the manifest is current. Run `--fix` after any case edit to recompute uids and the manifest; CI runs plain `check.py` on every store (`cases/v1`, `cases/v2`, `cases/challenge`). Part of the [after-edit steps](../README.md#changing-cases). |
| `audit_cases.py` | Check the case set against the authoring rules in `cases/README.md`: depth, coverage floors and the DON'T list. Run it before opening a case PR. CI runs it with `--strict`, which fails on depth and DON'T violations (see [the audit gate](../cases/README.md#the-audit-gate)). |
| `coverage_doc.py` | Regenerate a store's `COVERAGE.md` (`cases/v2` by default, `--cases-dir cases/challenge` for CHALLENGE) plus its JSON siblings (`coverage.json` and `cases_index.json`, consumed by the evals dashboard) from the store and the catalogue snapshot. Run it after any case edit or catalogue sync, and commit the result with the edit; CI's `--check` fails if any of the three committed files is out of date. |
| `sync_zeno_catalog.py` | Refresh `cases/zeno_catalog.json`, the committed snapshot of project-zeno's dataset catalogue (dataset ids, dataset-specific parameters, context layers, instruction fields) that COVERAGE.md measures against. It also carries each dataset's analytics endpoint and date window, from which ground-truth requests are built. Run it when project-zeno adds, removes or changes a dataset. It reads `origin/main` of a sibling `project-zeno` checkout (`--zeno` for another path). Then run `coverage_doc.py`. |

## Results ledger

| tool | what it does |
|---|---|
| `diff_runs.py` | Count regressions, recoveries, data bumps and coverage changes between two runs, over the cases both scored. Use it after an official run, against the last comparable run, and as the release gate (`--fail-on-regression`, optionally `--fail-on-coverage-loss`). A ground-truth check that flips while the digest of its fetched values moved is a **data bump**: listed, never gating, and flagged when it may hide a real regression. Only diff runs that are comparable as defined in [Comparing two runs](../results/README.md#comparing-two-runs). |
| `find_baseline.py` | Print the newest run in `results/gold/runs/` that matches a given run on environment, `ff`, trial count and case store (`caseset`), never the run itself; exit non-zero with the reason when none matches. The CI release gate uses it to pick the run it diffs against. |
| `flakiness.py` | For one multi-trial run, each check's mean, standard deviation and flip count across trials (`--per-case` lists the cases that flapped). Use it after every official run, and before calling a regression real, to see whether the check just flaps. Partial samples are flagged INSUFFICIENT DATA. |
| `compose_runs.py` | When a scoped re-run has refreshed some rows of a full run, combine the two into one current picture without editing either run file. Each row shows which run it came from; nothing is written to `results/gold/runs/` (see [Composing](../results/README.md#composing-a-current-picture-across-runs)). |
| `build_run_index.py` | Regenerate `results/index.json` (committed runs only, every set: headers and buckets, no rates) for web consumers. Run it after `git add`-ing a new run; `--check` is the CI freshness gate (see [Derived index](../results/README.md#derived-index)). |

## Reports

| tool | what it does |
|---|---|
| `report_run.py` | Markdown summary of one run on stdout: row verdicts, the bucket table, implied against evaluated checks (the reconciliation line), and diagnostics such as judge errors and slow rows. Use it for a quick read in the terminal or to paste into a PR. |
| `render_html.py` | Standalone HTML report of one run for stakeholders; `--all` builds the cross-run page with a run selector. Refresh both after every official run. |
| `render_inspector.py` | HTML matrix of every case against every check, with expected and measured values. Use it to find which checks failed on which cases; `--all` builds the cross-run page. |
| `render_trends.py` | Pass-rate trends across every run in the ledger, one line per `ff`. Use it to see movement across releases; never read a trend across differing `ff`. |

## CHALLENGE and BENCHMARK

A CHALLENGE verdict is a pass rate, not a regression count, and a BENCHMARK
version is a uid manifest over `cases/challenge`. Read
[cases/challenge/README.md](../cases/challenge/README.md) and
[benchmarks/README.md](../benchmarks/README.md) before you use these tools.

| tool | what it does |
|---|---|
| `challenge_rollup.py` | Pass rates for one or more CHALLENGE runs: overall, per set and per cohort, with confidence intervals and the strict rate (clean on every trial), compared against `cases/challenge/TARGETS.yml`. Errored rows leave the denominator and are reported as availability. Latency is reported too. Run it after every CHALLENGE run, before the recommendations doc. `--benchmark <manifest>` rolls up a BENCHMARK run: North Star, consistency, failure modes per type and the type x stage matrix over the manifest's active members. |
| `benchmark_sample.py` | Write a sampled BENCHMARK version (`benchmarks/<version>.json`) from the `ready` CHALLENGE cases: `--per-type` members (default 20) for each measured query type, easy and medium only for aoi and dataset. The same store and seed give the same manifest. It never regenerates a frozen version. |
| `benchmark_from_sheet.py` | Write a curated BENCHMARK version from a reviewed sheet export (`--seed <csv> --version <v>`), one member for each sheet row. It also writes each member's sheet facets into the case `notes`, so the uids do not change. |
| `benchmark_languages.py` | Write the languages companion of a BENCHMARK version (`--version <v>-languages --pairs-with <v>`): every `ready` case in another language, plus its English twin when the paired version does not hold it. A member takes the type and use cases of its twin's member. It never rewrites a frozen manifest. See [Languages companion](../benchmarks/README.md#languages-companion). |
| `check_benchmark.py` | Check every manifest in `benchmarks/` against `cases/challenge`: each active member's uid exists, its case is `ready`, and its frozen facets still match the case. For a member with a `language` or a `twin_uid`, it also checks the pair: the case's language, its twin, and that the twin is a member of the same version or of the `pairs_with` version. A problem fails a frozen version and gives a warning on a draft. CI runs it. |
| `twin_case.py` | Copy `expected` from one case of a language pair to the other (`--from <id> --to <id>`), so nobody types the expectations twice. One case of the pair must be in another language and name the other as its `twin`. The target file is rewritten with its new uid, so finish the after-edit steps afterwards. `--check` writes nothing and exits 1 when the pair differs. |
| `benchmark_page.py` | Write the page data that the FE scorecards page reads (`results/benchmark/pages/<run_id>.json`) for one BENCHMARK run. Run it on the machine that ran the run, because it reads the run's agent artifacts, which are gitignored. Commit the page with the run, then regenerate `results/index.json`. `--base <run>` fills the members that a rerun did not measure from an earlier run (see [Rerunning revised members only](../benchmarks/README.md#rerunning-revised-members-only)). |
| `plain_baseline.py` | Plain Sonnet with web search against Horizon on BENCHMARK draft-5, scored on the reply only. Output goes to `results/plain/`, never `results/benchmark/`, so the FE page cannot show it. The `ask` step spends API budget: run it only with AJ's go-ahead. |

## Legacy tools

Status: legacy. The GOLD Google Sheet that cases used to live in is
retired, and the case store is the source of truth. `gold run` replaced
gnw-evals as the runner. Routine work never needs these tools; each is kept
for the job in its last column.

| tool | what it was for | what it is still for |
|---|---|---|
| `import_sheet.py` | Imported GOLD sheet tabs into the case store; `cases/v1` is that import. | Bulk-loading cases drafted in a spreadsheet with the old sheet's columns (`--csv`). They land in `cases/v2` unless you pass `--cases-dir`; review them like any case edit. Pointing it at `cases/v1` moves the frozen baseline, which `tests/test_v1_frozen.py` rejects. |
| `export_sheet_csv.py` | Wrote the store as CSVs for the sheet: `cases.csv` replaced the tab, `changelog.csv` held each case's uid history. | A spreadsheet view of the cases for a reviewer who wants one (`--out` is required; multi-turn cases are skipped). |
| `export_csv.py` | Wrote single-turn cases as a gnw-evals test CSV, so gnw-evals could run them before `gold run` existed. | Running GOLD cases through the gnw-evals CLI, for example to compare its verdict with `gold run` on the same build (`--out` is required). |
| `ingest_run.py` | Converted gnw-evals runs (`*_detailed.csv`) into ledger run files; the runs in `results/gold/runs/` whose `harness.repo` is `gnw-evals` came in this way. | Importing any other gnw-evals run. `gold run` writes its own run files. |
| `parity.py` | Showed that `gold run` gives the same verdicts as gnw-evals on the same build, before gnw-evals was retired as the runner. | Repeating that check if you suspect the two harnesses score a shared check differently. |

## After-run ritual

The steps after every official run (render the reports, check flakiness and
diff, write the recommendations doc, commit with a regenerated
`results/index.json`) are in the root README under
[After a run](../README.md#after-a-run).
