---
name: triage-run
description: Use when analysing a finished GOLD run ("what failed", "triage this run", "look at the results"). Produces classified failures (agent regression, stale expectation, harness defect, flake) and a filled recommendations skeleton.
---

# triage-run — turn a ledger run into actions

Input: a `results/runs/<run_id>.json`. Output: a classified failure table and
the four-section recommendations doc. The ledger file itself is read-only.
Terms are defined in the [README glossary](../../../README.md#glossary).

## 1. Context before rows

Read the run header first and state it:

- `ff` (also the run_id suffix), read together with the run date. Before
  2026-08-31 dashboards and imagery existed only behind `ff=experimental`;
  from that date the default profile has them. What each profile holds:
  [README, Running the set](../../../README.md#running-the-set).
- `num_trials`: a 1-trial run is a smoke run, and its "failures" may be trial
  noise.
- `caseset` / `caseset_version`: if the version differs from that store's
  current `MANIFEST.json` (`cases/<caseset>/`), some rows were scored against
  older case content.
- `build`, `workers` / `trial_timeout`, and any `methodology_note`.

## 2. Extract the signal

- **Failing rows:** any gating check `== 0.0` (the majority verdict on a
  multi-trial run). An info-only check at `0.0` never fails a row. Pull
  `reasons` (judged checks) and `actuals` (the measured value for each failed
  check); measured against expected is the triage evidence, so lead with it.
- **Flapping rows:** checks whose per-trial values disagree (`trials` array).
  Cross-check with `uv run python tools/flakiness.py <run> --per-case`.
- **Judge errors:** rows with `judge_errors` are *unmeasured*, not failed —
  rerun them before trusting anything about them.
- **Error rows:** excluded from tallies, not failures; a contiguous block of
  timeouts is a load signature (check `workers`), not an agent regression.
- **Tri-state discipline:** `null` = not evaluated (n/a per that check's
  spec), never a fail. Report evaluated-vs-implied counts if they diverge.

## 3. Classify every failure (with the evidence for the call)

| class | typical evidence |
|---|---|
| **agent regression** | previously-passing uid now fails consistently across trials; actuals show changed behaviour |
| **stale expectation** | agent output is defensibly right; expected value predates a data/product change |
| **harness defect** | reason text contradicts actuals; check fired on wrong artifact; parse failure |
| **flake** | trial disagreement, nudge-dependent routing, borderline tolerance |

Rules of thumb:

- A whole capability failing at once (every dashboard row, say): first check
  that the run's profile had it (`ff` and run date, section 1).
- An answer roughly right but outside the tolerance: check dataset and
  parameter routing in actuals.
- Several AOI resolutions across trials: a known agent ambiguity; consider
  whether the case can earn a verdict at all.

## 4. Deliverable

Fill `results/recommendations/<run_id>.md` with the four sections the
after-run ritual requires ([README, After a run](../../../README.md#after-a-run));
`results/recommendations/20260801T093002Z.md` is the model:

1. **File upstream:** agent behaviour, with failing and flapping row lists.
2. **Case set:** stale expectations, park and unpark candidates, coverage holes.
3. **Harness:** check defects found while triaging.
4. **Next-run watchlist:** what to confirm on the following run.

## Hand-offs (never do these inline)

- Status changes the triage recommends → the **case-edit** skill (it enforces
  the verification rules).
- A handful of rows need remeasuring → scoped re-run + `compose_runs.py`;
  never splice fresh rows into an old run file.
- Release verdict old-vs-new → the **release-gate** skill.
