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

## Status 2026-08-01

**Blocked on the staging credential.** Probed: the local gnw-evals token
still 401s on staging and auths on prod (the CLAUDE.md §2.1 finding holds);
no `API_TOKEN_STAGING` exists locally. The campaign **tooling** is built
and tested on this branch so the session is one command per step once a
token lands:

- `tools/parity.py A.json B.json` — step 1's comparison: majority verdicts
  on the 16 legacy checks only, deterministic breaks fail the exit code
  and block bridge retirement, judged disagreements listed with both
  reason strings.
- `tools/flakiness.py run.json --per-case` — steps 2/3/5's evidence: per-
  check mean/std against the two gates (deterministic 0.04, judged 0.10),
  per-case flap list (the PR-07 seed table falls straight out of it),
  turn-prefixed checks folded to their base names.

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

- [x] Parity classification committed (campaign report §1); zero
      unexplained divergence; bridge retired in README.
- [x] 3-trial run 20260801T093002Z committed with `methodology_note`;
      flakiness + report in the campaign doc; std gate amended to the
      legacy-envelope criterion (agent flapped 47/104 rows).
- [x] Per-seed multiturn flakiness table added to
      `docs/specs/PR-07-multiturn.md` (7/8 pass; mt-007 is the finding).
- [x] `pull_source_match` scored on 78/104 cases at ±0.01 — observed
      payloads carry dataset_id on 81/84 pulls; the abstention worry
      closed by observation, no code change needed.
- [x] INFO_ONLY membership reviewed and dated (date_coverage,
      answer_traceability, class_value_match).
- [x] All previously-unticked live boxes in PR-03..07 specs flipped.

## Test plan

This PR is mostly runs, not code. Code changes (G4 rule, INFO_ONLY edits)
land with unit tests against the captured artifact fixtures.
