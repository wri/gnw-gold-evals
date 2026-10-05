---
name: release-gate
description: Use when comparing two GOLD runs for a release verdict ("did this build break anything", "gate this release"). Checks comparability preconditions, runs the diff, frames the count against trial noise.
---

# release-gate: the two-run verdict

GOLD's headline is a regression count between two runs. The count is only
meaningful if the two runs are comparable; check that before diffing. Terms
are defined in the [README glossary](../../../README.md#glossary).

## 1. Preconditions (refuse the diff if any fail)

The two runs must be comparable, as defined in
[results/README.md, Comparing two runs](../../../results/README.md#comparing-two-runs).
Check and state each item:

- **Same `ff`:** read it from the run JSON or the run_id suffix
  (`…_prod_experimental` versus `…_prod`). The profiles expose different
  tools, so a cross-profile diff measures the profile, not the release.
- **Same `num_trials`, both 3.** Trial noise alone swamps a 1-trial count.
- **Same `environment`.**
- **uid overlap:** the diff covers only uids present in both runs; report
  that number (the `Shared cases` line). Added or removed cases never count
  as regressions or recoveries, so `caseset_version` may differ, but a small
  overlap means a weak verdict.
- **Methodology notes:** if either run carries a `methodology_note`, the
  checks it names changed meaning, so their movement is not agent movement.

## 2. Run the gate

```bash
uv run python tools/diff_runs.py results/runs/<old>.json results/runs/<new>.json \
  --json scratch/gate.json --fail-on-regression --fail-on-coverage-loss
```

- **Regressions:** pass to fail on a uid present in both runs. Only gating
  checks count (section 3).
- **Recoveries:** fail to pass. Report them, but recoveries never offset
  regressions in the verdict.
- **Coverage loss:** checks that silently stopped evaluating
  (`--fail-on-coverage-loss`). A check that vanished is not a check that
  passed.

## 3. The verdict

Report as: **N regressions / M recoveries / K coverage losses over I shared
uids**. Count gating checks only: take N from the entries under
`regressions` in `scratch/gate.json` with `"info_only": false` (exactly what
`--fail-on-regression` gates on), and M and K the same way from `recoveries`
and `coverage_lost`. Info-only checks never count towards N, M or K, whatever
total the printed headline shows.

Then give the row-level evidence for each regression (check, expected versus
actual, per-trial pattern). Cross-check suspicious regressions against
`flakiness.py --per-case` on the new run before calling them real: a
flapping check is a flake finding, not a release blocker, unless it flapped
into consistent failure.

Zero regressions with material coverage loss is **not a pass**: say what
stopped being measured and why before any green light.

## Hand-offs

- Row-level failure analysis → the **triage-run** skill.
- The verdict plus evidence goes in the new run's
  `results/recommendations/<run_id>.md`.
