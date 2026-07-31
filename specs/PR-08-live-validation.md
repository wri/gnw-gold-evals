# PR-08 — Live validation campaign

## Goal

One ordered staging session that clears every live-run acceptance box left
unticked across PR-03..07, pins the one signal shape we could not pin
offline, and produces the ledger's first new-harness baseline.

## Why

The stack was built and unit-tested entirely offline; four specs carry the
same class of debt ("needs a staging token + judge budget"). Until this
campaign runs, the regression gate has no new-harness baseline to diff
against, the guards' std claims are theoretical, and `pull_source_match`
abstains on every row.

## Prerequisites

- Staging `API_TOKEN` (machine user; the local gnw-evals token is
  prod-only per its CLAUDE.md §2.1) and `ANTHROPIC_API_KEY`.
- Cost expectation, from run-6 shape: ~50s avg latency, 5 workers →
  ~115 cases × 3 trials ≈ 60–90 min wall clock; judge is haiku on ≤4
  calls/case — token cost is trivial next to the API time.

## The session, in order

1. **Parity run (PR-03's box).** Same staging build, same afternoon:
   (a) `tools/export_csv.py` → gnw-evals `--test-file` run → `ingest_run.py`;
   (b) `gold run --env staging --trials 3`.
   Compare per-check majority verdicts on the **17 legacy checks only**
   (PR-04/06 checks don't exist on the old path). Every disagreement is
   listed in the PR with both reason strings; judge-sampling noise is the
   only acceptable class. Record the **bridge retirement decision**: if
   parity holds, the CSV export becomes triage-only and the README's
   gnw-evals run instructions get removed.
2. **Guard + validator validation (PR-04/06 boxes).** The step-1b run
   doubles as this: every PR-04 guard and PR-06 validator at std ≤ 0.04
   across the 3 trials; zero false positives on run-6's 69 known-clean
   rows. Run with
   `--note "PR-04..07 methodology: guards, bucket scoring, new validators, multiturn"`
   — the first `methodology_note` ledger entry (PR-05's box), so
   diff-vs-run-6 is read as methodology change, not agent movement.
3. **Multiturn seed flakiness (PR-07's box).** mt-001..008 run in the same
   3-trial pass; per-case, per-turn flakiness table goes into the PR-07
   spec. Expectation: a 2-turn row is at best as stable as its flakiest
   turn. Any seed with a flapping deterministic check gets its
   expectations loosened or the row demoted to `todo` before the set grows.
4. **Pin `pull_source_match` (G4 follow-up).** The run's gzipped artifacts
   now hold real `statistics_last` payloads. Read them, document the
   dataset-reference shape, replace the guard's abstention with a real
   matching rule, and re-run affected rows. The guard graduates from
   "abstains everywhere" to scored.
5. **Judged-check probation review (PLAN §4).** From the 3-trial stds:
   admit or keep info-only each judged check (`clarification_requested`
   was ±0.29 in the sheet era — this is its retrial), and record the
   decision in `buckets.py`'s INFO_ONLY set with a dated comment.

## Acceptance criteria

- [ ] Parity table committed in the PR; disagreements ≤ judge noise;
      bridge decision recorded in README/PLAN.
- [ ] 3-trial run committed to `results/runs/` with `methodology_note`;
      report_run output attached; every deterministic check std ≤ 0.04.
- [ ] Per-seed multiturn flakiness table added to `specs/PR-07-multiturn.md`.
- [ ] `pull_source_match` no longer abstains on well-formed pulls; its
      matching rule documented from observed payloads.
- [ ] INFO_ONLY membership reviewed and dated.
- [ ] All previously-unticked live boxes in PR-03..07 specs flipped.

## Test plan

This PR is mostly runs, not code. Code changes (G4 rule, INFO_ONLY edits)
land with unit tests against the captured artifact fixtures.
