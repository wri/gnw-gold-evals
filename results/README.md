# Results ledger — contract

Committed, per-run JSON files: the longitudinal record GOLD exists to keep.
(The gnw-evals `outputs/` directory is gitignored scratch; this is the
opposite — small, stable, committed.) The ingester that writes these lands
in **PR-02**; this contract is fixed now so nothing has to be re-scored.

## File naming

```
results/runs/<YYYYMMDD>T<HHMMSS>Z_<env>[_<ff>].json
```

## Shape

```jsonc
{
  "run_id": "20260731T120022Z_staging_experimental",
  "started": "2026-07-31T12:00:22Z",
  "environment": "staging",            // staging | prod
  "build": "GNW 2026.7.29.1",          // agent build the API reported
  "ff": "experimental",                 // agent tool profile, or null
  "harness": {"repo": "gnw-evals", "sha": "5a377cd"},
  "judge_model": "claude-haiku-4-5",
  "num_trials": 1,
  "caseset_version": "2f8b10272938527c",  // must match cases/MANIFEST.json
  "results": [
    {
      "uid": "0fa55d427af482af",       // the exact case version scored
      "id": "1-002",                    // lineage id, for humans
      "checks": {                       // score name -> 1.0 | 0.0 | null
        "aoi_id_match": 1.0,
        "dataset_id_match": 1.0,
        "date_extraction": 1.0,
        "agent_answer": 0.0
      },
      "reasons": {                      // judged checks only, trimmed
        "agent_answer": "expected 1,319,600 ha, actual 1,299,278 ha ..."
      },
      "actuals": {                      // failed checks only: the measured
        "agent_answer": "1,299,278 ha"  // values, so reports can show
      },                                // expected vs measured (PR-13 on)
      "latency_s": 49.9,
      "trace_url": "https://langfuse...."
    }
  ]
}
```

## Rules

- **Keying.** Results reference cases by `uid`. If a case was edited since
  the run, the uid mismatch makes that visible instead of silently
  attributing old scores to new content. Runs also record the whole-set
  `caseset_version`; regression comparisons (PR-02's `diff_runs.py`) are
  computed over the **intersection of uids** between two runs, so set growth
  never masquerades as regression or recovery.
- **Stale means stale.** A row that carries a uid the store no longer holds
  is recorded `stale_case: true` — it is never re-resolved through the
  weaker `test_id`+query join, however well the query text still matches.
  Only rows with no uid at all (legacy sheet runs) may use that fallback,
  and it is drift-checked against the case's current expectations.
- **Run files are immutable.** `write_run` refuses to overwrite an existing
  run file with different content; byte-identical re-ingest (idempotence) is
  allowed. Re-ingesting after a tooling fix means deleting the file first,
  visibly, in a reviewable commit.
- **Checks are tri-state.** `1.0` pass, `0.0` fail, `null` not evaluated.
  Every run report must state evaluated-vs-implied check counts (the
  reconciliation line) — see PR-05.
- **Multi-trial runs** store one entry per case with
  `"trials": [{...}, {...}, {...}]` per check where trials > 1; the
  top-level `checks` value is the majority verdict.
- **No fabricated or backfilled runs.** A ledger entry is written by the
  ingester from real harness output, never by hand.
