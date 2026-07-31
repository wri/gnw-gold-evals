# PR-06 — Bucket-filling validators

## Goal

Give Analysis its first dedicated checks and extend Explanation, Output and
Scope beyond their current slivers — deterministic wherever possible, per
the working agreement: numbers in code, structure to the judge.

## Why

After PR-05 the bucket table will show it plainly: Analysis unmeasured,
Output covering only dashboard rows, Scope resting on the suite's two
flakiest judges. The parent plan's evidence (run 6): 15 of 63 extractable
headline numbers were **not derivable from the agent's own charts**, and all
of them passed `agent_answer`.

## Scope — six validators + two expected fields

| # | Validator | Bucket | Mechanism |
|---|---|---|---|
| A2 | `class_value_match` | Analysis | **Rules.** New expected fields `class_values` (promoted from the sheet's `note_class_*`/`note_value_*` scratchpads where trustworthy): named per-class values compared against chart/statistics data in code, 2% tolerance, reusing `chart_candidate_values()`. Catches wrong sub-totals hiding under a correct headline. |
| A3 | `chart_integrity` | Analysis | **Rules.** Mis-join detection over `charts_json`: record arrays with parallel columns null-padded against each other; axis fields absent from data records. Catches run-6's 1-060 (two unrelated tables zipped row-wise) at source. |
| E1 | `answer_traceability` | Explanation | **Rules.** Extract headline number(s) from the prose (same parser discipline as `chart_numeric`: scale words, unit multipliers, ambiguous-decimal → abstain); each must be derivable from the chart data within 2% (leaf/sum/max/share). The deterministic "does the answer mislead" check — catches 1-027 (679.16 ha appears nowhere in its own chart), 1-006, 1-009. |
| O2 | `chart_well_formed` | Output | **Rules.** Axis fields exist in `data`; `data` non-empty; pie-slice sanity (info-only threshold first). Deliberately overlaps A3 — different attribution (broken spec vs wrong join). |
| O3 | `chart_type_match` | Output | **Rules.** New expected field `chart_type` (`;`-alternatives). Port from `eval-metrics-slice-1`; seed values for the rows the parent plan names (1-002, 1-052) plus the March benchmark's 7 chart-type prompts. |
| S1 | `scope_match` | Scope | **Rules.** New expected field `scope` ∈ {analyse, suggest, clarify, refuse}. Actual scope classified from state: pulled data → analyse; suggested_datasets ∧ no pull → suggest; nudge/question ∧ no pull → clarify; else refuse. Demotes the ±0.29/±0.23 judges to info-only. Catches 1-085 (ran a full analysis when asked to suggest datasets). |

**Case-set work in the same PR** (each edit mints new uids — that is the
system working): populate `scope` on every case (mostly `analyse`; the
guardrail/suggestion/nudge groups carry the others), `chart_type` where the
expectation is defensible, `class_values` where the scratchpad columns held
real per-class figures.

## Out of scope

Codeact-method judging (CHALLENGE's job — too noisy for a smoke test);
multilingual number-parsing beyond the abstain rule; multiturn (PR-07).

## Acceptance criteria

- [ ] Each validator: unit tests from real run-6 fixtures (1-060 for A3,
      1-027/1-006/1-009 for E1, 1-085 for S1) plus clean-row negatives.
- [ ] E1 abstains (null, counted in reconciliation) on ambiguous-decimal
      multilingual rows rather than guessing.
- [ ] 3-trial staging run: every new deterministic check at std ≤ 0.04;
      zero false positives on run-6's known-clean rows; Analysis bucket
      shows nonzero coverage in the bucket table.
- [ ] Bucket coverage after this PR: every bucket ≥ 20 rows with ≥ 1
      dedicated check (Analysis exempt from the row target until
      `class_values` population completes; actual number stated in the PR).

## Test plan

Fixture-driven unit tests per validator; the 3-trial validation run
committed to the ledger; `check.py` green after the case-set edits.
