# Results ledgers: contract

Each suite writes its runs to its own ledger under `results/`, and the ledgers never mix. Terms are in the [glossary](../docs/glossary.md).

| Ledger | Suite | Holds | Read as |
|---|---|---|---|
| `results/challenge/` | CHALLENGE | `runs/`, `recommendations/` | pass rates per set and cohort, with `tools/challenge_rollup.py` |
| `results/benchmark/` | BENCHMARK | `runs/`, `recommendations/`, `pages/` | the North Star, and page data for the frontend ([benchmarks/README.md](../benchmarks/README.md)) |
| `results/gold/` | GOLD legacy copy | `runs/`, `reports/`, `recommendations/`, `campaigns/` | regression counts ([docs/gold-legacy.md](../docs/gold-legacy.md)) |
| `results/plain/` | plain baseline | its own files, not run records | [plain/README.md](plain/README.md) |

Every run ledger also has a gitignored `artifacts/` with the raw agent state per case and trial. While a run is in progress it also has `runs/<run_id>.partial.jsonl`. `results/index.json` indexes the committed runs of the three run ledgers.

The contract below applies to the three run ledgers. `results/plain/` does not follow it: `tools/plain_baseline.py` writes files in a format of its own. `evals run` writes every new run file. Older GOLD runs made with gnw-evals were converted by `tools/ingest_run.py`.

A BENCHMARK run record also carries `benchmark: {path, version, status, manifest_sha, members}`. It names the manifest that chose its cases, by content hash, errata included. Its `caseset` and `caseset_version` are those of the source store, `cases/challenge`.

## File naming

```
results/<suite>/runs/<YYYYMMDD>T<HHMMSS>Z_<env>[_<ff>].json     # <suite>: challenge | benchmark | gold
```

The time is the run's start in UTC. The `_<ff>` suffix is left out when the run used the agent's default profile, so a `_prod` run and a `_prod_experimental` run used different profiles.

## Shape

Trimmed from a GOLD run, `results/gold/runs/20260831T163347Z_prod.json`. Runs in every ledger have this shape:

```jsonc
{
  "run_id": "20260831T163347Z_prod",
  "started": "2026-08-31T16:33:47Z",     // UTC
  "environment": "prod",                 // staging | prod | local
  "build": "baseline",                   // the --build label (default "unknown")
  "ff": null,                            // agent tool profile; null = default
  "harness": {"repo": "gnw-gold-evals", "sha": "28941a8"},
  "judge_model": "claude-haiku-4-5",     // or "typesafe/jev-1.13" (--judge-backend)
  "num_trials": 3,
  "workers": 10,                         // concurrency, to trace timeouts to load
  "trial_timeout": 900.0,                // per-trial wall-clock limit, seconds
  "caseset": "v2",                       // store loaded: cases/<caseset>
  "caseset_version": "bf5a593d71d658ae", // that store's MANIFEST.json at run time
  "results": [
    {
      "uid": "6c8b9a9d674922d2",         // the exact case version scored
      "id": "1-005",                     // lineage id, for humans
      "checks": {                        // every check: 1.0 | 0.0 | null
        "aoi_id_match": 1.0,             // (the majority verdict when trials > 1)
        "dataset_id_match": 0.0,
        "date_extraction": null,
        ...
      },
      "reasons": {                       // any check that explained its score,
        "answer_traceability":           // trimmed to 500 characters
          "deterministic check: the chart's closest figure to the expected ..."
      },
      "actuals": {                       // failed checks only: the measured value,
        "dataset_id_match": "11"         // so reports show expected vs measured
      },
      "latency_s": 126.2,
      "trace_url": "https://langfuse.globalnaturewatch.org/project/wri_lcl/traces/...",
      "trials": [                        // trials > 1 only: each trial's own checks
        {"checks": {"aoi_id_match": 1.0, "dataset_id_match": 0.0, ...}, "latency_s": 17.0},
        {"checks": {...}, "latency_s": 20.7},
        {"checks": {...}, "latency_s": 126.2}
      ]
    }
  ],
  "buckets": {                           // per-bucket tallies that reports render
    "retrieval": {"dedicated": {"passed": 407, "evaluated": 438},
                  "shared": {"passed": 0, "evaluated": 0},
                  "rows_covered": 103},
    ...                                  // analysis, explanation, output, scope
    "rows_total": 109,
    "verdicts": {"pass": 94, "fail": 15, "error": 0, "uncovered": 0}
  }
}
```

`validate_run` in `src/goldset/ledger.py` requires `run_id`, `started`, `environment`, `build`, `ff`, `harness`, `judge_model`, `num_trials`, `caseset_version` and `results`. Older runs can lack other fields: the [Scoring change log](#scoring-change-log) says which.

Optional fields, written only when they apply:

| Field | Level | Meaning |
|---|---|---|
| `methodology_note` | run | The `--note` text: check semantics changed since the previous run, so movement on those checks is not an agent change. |
| `resumed` | run | `true` when the run was finished with `evals run --resume`. Its timing mixes two sessions. |
| `error` | entry | The harness could not score the case: the request was refused, the connection failed, or the harness hit an error. On a multi-trial run it is on the entry only when no trial could be scored. The row verdict is then `error`, never `fail`. |
| `judge_errors` | entry | Checks whose judge call failed. They stay `null`. On a multi-trial run it is on the entry only when no trial could be scored, and the row verdict is then `error`. |
| `no_answer` | entry or trial | The agent sent no reply: the stream stalled, dropped or failed with a server error before it finished. A stall is 240 seconds with no data, or a stream still open at the trial timeout. The attempt counts as failed, not as an error. On a multi-trial run it sits on the trial. |
| `error` | trial | Why the harness could not score that trial: it failed after the reply, or a judge call failed. That trial is left out of the per-check majorities and of the row verdict. |
| `stream_s` | entry and trial | The agent turn: from `POST /api/chat` to the last stream line. Compare latency with it. `latency_s` runs until the final state and any dashboard are fetched. Neither includes scoring or judge time. |
| `info` | entry | `{"slow": true, "threshold_s": 180.0}` when the case took longer than `--slow-threshold`. Never scored. |
| `ground_truth` | run and entry | Present when a case carried `expected.ground_truth`; see [GOLD legacy copy only](#gold-legacy-copy-only). |
| `turns_detail` | entry | Multi-turn cases only: each turn's query, reasons, latency and trace URL. Their checks sit in `checks` as `t<N>.<check>`. |
| `stale_case`, `drift`, `joined_by` | entry | Written only by `tools/ingest_run.py`; see [Stale means stale](#stale-means-stale). |

## Rules

- **Keying.** Results reference cases by `uid`. If a case was edited since the run, the uid mismatch shows it, instead of attributing old scores to new content. Runs also record the store's `caseset_version`.
- **Run files are immutable.** `write_run` refuses to overwrite a run file with different content. A byte-identical rewrite is allowed. Re-ingesting after a tooling fix means deleting the file first, visibly, in a reviewable commit.
- **No fabricated or backfilled runs.** A run file is written by `evals run` from real harness output, never by hand. Legacy GOLD runs came through `tools/ingest_run.py`.
- **In-flight state is a sidecar.** While a run executes, each finished entry is appended to `runs/<run_id>.partial.jsonl`, which is gitignored and synced to disk per case. The run file is written once, at the end, and the partial file is deleted.
- **Resumed runs.** `evals run --resume <run_id>` finishes a killed run from its partial file. The record then carries `resumed: true` and is otherwise the same as an unbroken run.
- **Checks are tri-state**: `1.0` pass, `0.0` fail, `null` not evaluated.
- **Implied checks must evaluate.** A case's expected values imply checks that must evaluate (`buckets.implied_checks_for_case`). `tools/report_run.py` prints the reconciliation line, which lists each implied check that was not evaluated.
- <a id="stale-means-stale"></a>**Stale means stale.** Only `tools/ingest_run.py` writes `stale_case: true`. A row with a uid joins on that uid alone: if the store no longer holds it, the row is stale. It is never matched again through a weaker join, because that would attach old scores to edited case content. A legacy row with no uid may join on `id` plus the exact query, with a warning (`joined_by: "test_id"`). It is stale if the case's expected values have changed since, and `drift` lists them. Stale rows stay in the file but are left out of diffs and flakiness. Separately, `tools/report_run.py` shows `stale_case` as the status of a failing row whose uid the current store no longer holds.

### Multi-trial runs

A run with `num_trials` above 1 still stores one entry per case:

- `trials` lists every trial: its `checks`, `latency_s` and `stream_s`, and `no_answer` or `error` when they apply.
- `checks` holds each check's majority verdict across the scored trials: pass only if more than half of the trials that evaluated it passed, a tie fails, and `null` if no trial evaluated it.
- A trial that got no reply counts as a failed attempt. A trial the harness could not score is left out of the majorities.
- The entry carries `error` and `judge_errors` only when no trial could be scored.
- `reasons`, `actuals`, `latency_s`, `trace_url` and `turns_detail` come from the last trial.
- The row verdict comes from the attempts (`buckets.row_verdict`), not from the per-check majorities: see [README, How scoring reads](../README.md#how-scoring-reads).

## Comparing two runs

Two runs are comparable only with the same `ff`, the same trial count and the same environment. [README, Running a suite](../README.md#running-a-suite) owns these conditions, the reasons for them and the evidence for 3 trials. Each kind of comparison adds one more condition:

- **CHALLENGE rates**: the same `caseset_version`. A rate over a different set of cases has a different denominator.
- **BENCHMARK rates**: the same version. Rates are only comparable within a version.
- **A per-case diff**: the `caseset_version` may differ. The diff covers only the uids both runs scored, so a growing case set never shows up as regressions or recoveries. GOLD's `tools/diff_runs.py`, its data bumps and the release gate are in [docs/gold-legacy.md](../docs/gold-legacy.md#regression-diffs).

## Composing a current picture across runs

A scoped rerun is often all that is needed: when only a few rows changed, or when one capability was unreachable during the full run. It is tempting to write the fresher scores into the earlier run file, to get a single number to quote. **Don't.** `write_run` refuses it, and the rules above forbid it. A run record also describes how its rows were produced, through `ff`, `workers`, `build`, `harness` and `caseset_version`. Rows spliced in from other conditions would make that metadata false.

Compose in the analysis instead:

```bash
uv run python tools/compose_runs.py results/<suite>/runs/<primary>.json \
    results/<suite>/runs/<supplementary>.json
```

It resolves every active case to its freshest measurement at the case's current uid. A supplement wins over the primary, and a later supplement over an earlier one. It prints where each row came from, names any row nothing has measured, warns when the sources disagree on `ff`, and writes nothing to the ledger. It reads the store each run records, and it refuses BENCHMARK runs: combine those with `tools/benchmark_page.py --base` ([benchmarks/README.md](../benchmarks/README.md#rerunning-revised-members-only)).

## Derived index

`results/index.json` is a generated projection of the committed runs of every ledger: per run, the header fields plus the `buckets` block, with no computed rates and no per-case rows. Web consumers, such as the evals dashboard, use it to list runs and draw trends from one fetch, because raw.githubusercontent.com cannot list directories.

- Regenerate it with `uv run python tools/build_run_index.py` after you stage a new run, and commit it with the run. It lists files with `git ls-files`, so unstaged local runs never leak in. CI's `--check` fails on a stale index.
- It also reads `benchmarks/*.json`, so a rebuilt manifest, an erratum or a freeze needs a fresh index too.
- Each BENCHMARK entry in `sets.benchmark` carries the run's `benchmark` block, `canonical` and `canonical_reasons`. A run is canonical when it is prod, default profile, 3 trials and measured every currently active member.
- A BENCHMARK entry whose page data is committed carries `page`, the page's path. When the page combines the run with earlier runs, the entry carries `composed_with` and is judged canonical over the runs together.
- The top-level `benchmarks` object maps each version to its `path`, `status`, `frozen` date, `members`, `voided` count, `runs` and `canonical_runs`.

## Scoring change log

Changes that affect how an older run reads. Rates on either side of a scoring change are not comparable point for point.

- **2026-08-04**: runs start to record `workers`, `trial_timeout` and `caseset`. To find which store an older run loaded, match its `caseset_version` against the manifests' git history.
- **2026-09-25**: runs start to record `stream_s`, the latency to compare. Older runs carry only `latency_s`.
- **2026-10-27**: an attempt that got no reply records `no_answer` and counts as a failed attempt. An attempt the harness could not score keeps its own `error` and is left out, and a row is `error` only when no attempt was scored. Before, any errored trial made the whole row `error`.
- **2026-10-28**: the row verdict comes from the majority of the attempts, each passing when every gating check it scored passed. Before, it came from each check's majority across trials. That failed rows right on 2 of 3 attempts when a check was scored on one attempt only, and passed rows right on 1 of 3 whose attempts failed different checks.

## GOLD legacy copy only

Only GOLD cases carry `expected.ground_truth` today, though the harness records it for any store. A ground-truth case adds an object to its entry, and the run gains a summary:

```jsonc
// on the entry
"ground_truth": {
  "selector": "sum(carbon_emissions_MgCO2e) WHERE tree_cover_loss_year=2019",
  "values": [658496.56],            // fetched at run start, one fetch per run
  "digest": "…",                    // absent when `unresolved` is set
  "dataset_id": "4",
  "content_date_fixed": false,
  "resource_id": "09272a7f-…",
  "fetched_at": "2026-09-14T12:00:05Z",
  "request": {"endpoint": "/v0/land_change/tree_cover_loss/analytics",
              "payload": {"aoi": {"type": "admin", "ids": ["MDG.3.4"]}}},
  "metadata": {"aoi": {"provider": "gadm", "version": "4.1"}},  // the server's echo
  "agent_values": [[658496.56]],    // per trial, aligned with `trials`: the agent's
                                    // own pulled figure for each value; null where
                                    // its pull lacked one
  "unresolved": "column 'x' not in the response"  // only when the selector missed
}

// on the run, present when any entry has one
"ground_truth": {
  "base_url": "https://analytics.globalnaturewatch.org",
  "cases": 1,
  "prefetch_seconds": 3.4,          // summed across sessions on a resumed run
  "tolerance": 0.02                 // relative tolerance the run graded with
}
```

**Ground truth is recorded, not trusted.** A ground-truth case is graded against values fetched from the production analytics API before any trial, and its entry records what was fetched and how. The API has no data-version field, so `digest` is the only sign that the data moved: a digest that differs between two runs means that case's data changed. It hashes the values the selector picked, not the whole response. It is left out on an unresolved selector, where it would be the same for every such case and prove nothing. `tools/diff_runs.py` reads it to file [data bumps](../docs/gold-legacy.md#data-bumps), and reads `agent_values` to flag a bump that may hide a real agent break.
