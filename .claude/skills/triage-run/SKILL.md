---
name: triage-run
description: Use when analysing a finished GOLD run — "what failed", "triage this run", "look at the results". Produces classified failures (agent / stale case / harness / flake) and a filled recommendations skeleton.
---

# triage-run — turn a ledger run into actions

Input: a `results/runs/<run_id>.json`. Output: a classified failure table and
the four-section recommendations doc. The ledger file itself is read-only.

## 1. Context before rows

Read the run header first and state it: `ff` (run_id suffix — a bare
`…_staging` run never exercised dashboards/imagery), `num_trials` (1-trial =
smoke; its "failures" may be trial noise), `caseset`/`caseset_version`
(matches current `cases/v2/MANIFEST.json`? if not, rows may be stale),
`build`, `workers`/`trial_timeout`, and any `methodology_note`.

## 2. Extract the signal

- **Failing rows:** any check `== 0.0` (majority verdict on multi-trial).
  Pull `reasons` (judged checks) and `actuals` (expected vs measured) — the
  expected-vs-measured pair is the triage evidence, lead with it.
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

Rules of thumb from history: dashboard rows all failing → check `ff` before
anything else; answer ~right but off by a tolerance → check dataset/params
routing in actuals; multiple AOI resolutions across trials → known agent
ambiguity, consider whether the case can earn a verdict at all.

## 4. Deliverable

Fill `results/recommendations/<run_id>.md` (model:
`results/recommendations/20260801T093002Z.md`):

1. **File upstream** — agent behaviour, with failing/flapping row lists.
2. **Case set** — stale expectations, park/unpark candidates, coverage holes.
3. **Harness** — check defects found while triaging.
4. **Next-run watchlist** — what to confirm on the following run.

## Hand-offs (never do these inline)

- Status changes the triage recommends → the **case-edit** skill (it enforces
  the verification rules).
- A handful of rows need remeasuring → scoped re-run + `compose_runs.py`;
  never splice fresh rows into an old run file.
- Release verdict old-vs-new → the **release-gate** skill.
