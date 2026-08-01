# PR-02 — Results ledger and regression diff

## Goal

Make runs durable and comparable: ingest harness output into committed
per-run JSONs keyed by case `uid`, and compute regressions between any two
runs.

## Why

- gnw-evals' `outputs/` is gitignored scratch; the longitudinal record GOLD
  exists for currently lives in ad-hoc HTML reports.
- Results must be pinned to the exact case version scored — the sheet era
  couldn't distinguish "the agent regressed" from "someone edited the
  expectation" (see the 2026-07-30 double run: 0/0 → 7/7 on
  `agent_answer` purely from sheet edits).

## Scope

**In:** `tools/ingest_run.py` (gnw-evals `*_summary.csv` + `*_detailed.csv`
→ `results/runs/<run_id>.json` per the contract in `results/README.md`);
`tools/diff_runs.py` (two run files → regression report);
`results/runs/` seeded with the first real ingested run.

**Out:** running the harness itself (PR-03), any scoring-policy change
(PR-05 consumes this ledger; this PR only records).

## Design

- **Ingest** joins harness rows to cases by the `uid` column the export
  carries (fallback: `test_id` + exact query match, warned). Rows whose uid
  is absent from the current manifest are recorded with
  `"stale_case": true` — never dropped, never silently re-keyed.
- Check columns map 1:1 from the harness's `*_score` fields, dropping the
  `_score` suffix; judge `*_reason` strings are trimmed to 500 chars into
  `reasons`. `null` stays `null` (tri-state is contractual).
- Run metadata (`environment`, `build`, `ff`, harness sha, judge model,
  trials) is passed as flags or read from a small sidecar the runner is
  taught to write in PR-03; until then, flags.
- **Diff** compares two run files over the **intersection of uids**:
  - *regression*: check pass → fail
  - *recovery*: fail → pass
  - *new coverage / lost coverage*: null ↔ scored transitions
  - uid-set changes are listed separately ("N cases changed identity") so
    set churn is visible but never counted as regression.
  - Output: markdown to stdout + optional JSON (`--json`), designed to be
    pasted into a release thread.

## Acceptance criteria

- [x] Ingesting the same CSVs twice is idempotent (same file, byte-equal).
- [x] A doctored fixture pair produces exactly the expected regression /
      recovery / coverage-change lists (unit-tested, no live API).
- [x] Stale-case rows are flagged, counted in the summary line, excluded
      from regression math.
- [x] `diff_runs.py` on runs with different `caseset_version` prints the
      intersection size and refuses `--strict` mode.
- [x] One real staging run ingested and committed as the ledger's first
      entry.

## Test plan

Fixtures: two synthetic run JSONs + a synthetic harness CSV pair covering
every transition type (pass→fail, fail→pass, null→scored, scored→null,
stale uid). `uv run python -m pytest tests/test_ingest.py tests/test_diff.py`.
