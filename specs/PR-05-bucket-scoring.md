# PR-05 — Five-bucket scoring and the release gate

## Goal

Replace the flat-mean `overall_score` with the three-layer GOLD scoring
system: per-row verdicts, per-bucket rates with coverage denominators, and
a per-release **regression count** as the headline.

## Why

The flat mean averages dependent checks (a wrong-dataset row still banks
AOI/date/pull points), scores zero-expectation rows as passing, and its
denominator varies per row — the harness itself prints "experimental and
untested". A smoke test's headline must be "what broke", not a percentage.

## Scope

**In:** bucket tags in the validator registry; row verdict + bucket rollup
+ reconciliation line in the run report; `diff_runs.py` (PR-02) grows the
release-gate summary; ledger schema addition (`buckets` block per run).

**Out:** new validators (PR-06); any change to individual check semantics.

## Design

### Bucket map (dedicated checks only; shared checks report to both, tagged)

| Bucket | Checks after PR-04 |
|---|---|
| Retrieval | aoi_id_match, dataset_id_match, dataset_parameter_match, context_layer_match, date_extraction, data_pull_exists, pull_source_match (G4), answered_without_data (G1) |
| Analysis | *(empty until PR-06 — rendered as "unmeasured", never omitted)* |
| Explanation | expected_text_match, web_fallback (G2) |
| Output | chart_produced (F2), dashboard_aoi_match, dashboard_widgets_match, dashboard_widgets_valid |
| Scope | clarification_requested, suggested_datasets_match, nudge_match, latency_info (G3, info-only) |
| Shared (dual-tagged) | charts_answer → Analysis+Output; agent_answer → Analysis+Explanation; dashboard_created → Output+Scope |

### Report layers

1. **Row verdict**: pass iff every applicable check passes. `rows clean /
   rows run` headline.
2. **Bucket table**: `passed/evaluated` **and** `rows-with-coverage/rows` —
   both, always. An unmeasured bucket prints `— (0 rows covered)`, visually
   distinct from `1.00`.
3. **Reconciliation line**: checks implied by the case set vs evaluated,
   with the delta itemised (which uid, which check, why absent). Target:
   delta explained or zero, every run.
4. **Release gate** (extends `diff_runs.py`): regressions / recoveries /
   coverage changes by bucket; judged-check regressions require majority
   across trials. Exit code reflects `--fail-on-regression` for CI use.

### Rules

- A row with zero applicable checks is reported as **uncovered** (excluded
  from pass denominators, counted loudly in its own line) — never a pass.
- Info-only checks (date_coverage, latency_info, plus any judged check in
  its probation window) appear in reports, never in verdicts.
- Judged-check admission: info-only until std ≤ 0.10 over a 3-trial run
  (PLAN.md §4).

## Acceptance criteria

- [ ] Fixture suite covering: all-pass row, one-fail row, zero-check row,
      unmeasured bucket, dual-tagged check attribution, info-only exclusion.
- [ ] Run report on real staging data shows all four layers; the
      reconciliation delta is zero or itemised.
- [ ] `diff_runs.py --fail-on-regression` exits nonzero on a doctored
      regression fixture and zero on recovery-only changes.
- [ ] `methodology_note` recorded in the first post-PR run.

## Test plan

Pure-function tests over synthetic ledgers (no live API); one real 3-trial
staging run committed with the new report format.
