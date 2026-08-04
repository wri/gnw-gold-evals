---
name: release-gate
description: Use when comparing two GOLD runs for a release verdict — "did this build break anything", "gate this release". Checks comparability preconditions, runs the diff, frames the count against trial noise.
---

# release-gate — the two-run verdict

GOLD's headline is a regression count between two runs. The count is only
meaningful if the two runs are comparable; check that before diffing.

## 1. Preconditions (refuse the diff if any fail)

- **Same `ff`** — read it from the run JSON and the run_id suffix
  (`…_staging_experimental` vs `…_staging`). A differing `ff` makes dashboard
  and imagery rows incomparable by construction.
- **Same `num_trials`, and both official tier (3 trials).** Measured on real
  runs: two trials *of the same run* differ by 18–29 spurious regressions —
  more than the 15 real ones between genuinely different builds (CLAUDE.md).
  A 1-trial side poisons the count.
- **Caseset overlap:** the diff runs over the **uid intersection** — report
  its size. Set growth/shrinkage never counts as regression or recovery, but
  a small intersection means a weak verdict. `caseset`/`caseset_version`
  fields say which store and content each run measured.
- Same environment; note any `methodology_note` (check semantics changed →
  those checks' movements are not agent movement).

## 2. Run the gate

```bash
uv run python tools/diff_runs.py results/runs/<old>.json results/runs/<new>.json \
  --fail-on-regression --fail-on-coverage-loss
```

- **Regressions:** pass→fail on a shared uid, excluding info-only checks.
- **Recoveries:** fail→pass — report, but recoveries never offset
  regressions in the verdict.
- **Coverage loss:** checks that silently stopped evaluating (`--fail-on-
  coverage-loss`) — a check that vanished is not a check that passed.

## 3. The verdict

Report as: **N regressions / M recoveries / K coverage losses over I shared
uids**, then the row-level evidence for each regression (check, expected vs
actual, per-trial pattern). Cross-check suspicious regressions against
`flakiness.py --per-case` on the new run before calling them real — a
flapping check is a flake finding, not a release blocker, unless it flapped
into consistent failure.

Zero regressions with material coverage loss is **not a pass** — say what
stopped being measured and why before any green light.

## Hand-offs

- Row-level failure analysis → the **triage-run** skill.
- The verdict plus evidence goes in the new run's
  `results/recommendations/<run_id>.md`.
