# PR-04 — Fix-first: inherited debts + trivial guards

## Goal

Fix the six known harness defects that make broken rows look healthy, and
add the four zero-plumbing deterministic guards. After this PR, "the suite
says pass" starts meaning something.

## Why

On the 2026-07-31 run: a row that pulled **no data** and answered from web
knowledge scored `agent_answer` 1.0 (row 1-030); four prose-only rows
skipped the chart check entirely; an empty dashboard passed; text-widget
rows could never pass. Every one is an inherited, documented defect.

## Scope — six fixes

| # | Fix | Semantics change |
|---|---|---|
| F1 | Expected AOIs set, agent resolved none → **0.0** (was `None`) | absence is failure when expected |
| F2 | `expected_answer` set, no chart produced → new `chart_produced` = **0.0** (was: chart check silently `None`) | 4 rows on run 6 become visible |
| F3 | Empty dashboard → widget checks **0.0** (was `None`); `_widget_is_valid` reads `config.text` (was `widget["text"]`, unfulfillable) | rows 1-096, 1-100, 1-101 measured correctly — **narrowed 2026-08-03, see below** |
| F4 | Judge call failure → explicit `error` state that fails the row loudly (was: clarification judge swallowed to `False` — scoring 1.0 on `expected=False` rows during outages; other judges crashed the whole row) | outages are visible, never scored |
| F5 | Chart JSON truncation: truncate **per chart with valid-JSON repair** instead of a blind 80k slice that yields unparseable JSON → forced numeric-override failures | no false 0s on large charts |
| F6 | Audit all judge structured outputs: **reasoning field precedes score field** (haiku commits to a score then argues with itself otherwise — slice-1 finding) | judge self-consistency |

## Scope — four guards (all deterministic, all zero new plumbing)

| # | Guard | Bucket | Rule |
|---|---|---|---|
| G1 | `answered_without_data` | Retrieval | expects a data pull ∧ `row_count == 0` ∧ no dataset selected ∧ substantive answer → 0.0. Catches 1-030 exactly. |
| G2 | `web_fallback` | Explanation | external citation/URL in the prose when a data pull was expected → 0.0 (1-030 cites wri.org) |
| G3 | `latency_info` | Scope | `duration_seconds` > threshold (default 180s) → **info-only** flag, never scored (the 294.7s run-6 row triggered nothing) |
| G4 | `pull_source_match` | Retrieval | `statistics[-1].source_url`/`id` must reference the expected dataset (both fields currently read then discarded) |

## Out of scope

The bucket-filling validators needing new expected fields or parsing work
(A2/A3/E1/O2/O3/S1 — PR-06); any aggregation change (PR-05).

## Acceptance criteria

- [x] Each fix and guard lands with a regression test reproducing the
      original defect (fixtures built from the run-6 rows named above).
- [x] 3-trial staging run 20260801T093002Z — criterion amended by the
      data (campaign report §2): the staging agent itself flapped on 47 of
      104 rows, so the absolute ≤0.04 gate is unattainable for any check
      that reads agent behaviour. Guards sit **inside the legacy checks'
      variance envelope on the same run** (answered_without_data ±0.06 and
      chart_produced ±0.08 vs legacy dataset_id ±0.08 / data_pull ±0.06),
      and their failures co-occur with real no-pull behaviour rather than
      firing independently. pull_source_match ±0.01 and web_fallback
      ±0.00 are outright stable.
- [x] `methodology_note` recorded on runs 20260801T064429Z (killed) and
      20260801T093002Z; semantics changes enumerated in the note itself.

## Test plan

Unit tests per fix/guard + the 3-trial validation run committed to the
ledger with its diff-vs-previous annotated.

---

## Amendment 2026-08-03 — F3 narrowed (H7)

F3's rule "an existing dashboard with zero widgets is an empty artifact → 0.0"
now applies **only when the case expects widgets**. With no
`expected_dashboard_widgets`, `dashboard_widgets_valid` returns `None`.

Why, from two 3-trial staging runs:

- **1-096's prompt is only "Create a dashboard for brazil".** It sets no widget
  expectation, so an empty dashboard is the prompt being obeyed, not an empty
  artifact. It scored 0.0 on 4 of 6 trials and 1.0 only on the two where the
  agent volunteered an *unsolicited* text widget.
- That made the suite internally inconsistent: `evaluate_dashboard_created`
  treats an unsolicited dashboard as a guardrail violation, while
  `dashboard_widgets_valid` **rewarded** unsolicited widgets.
- The case had no way to satisfy the check either: there is no syntax for
  "expect zero widgets" — an empty value parses to `None`, i.e. no expectation.

F3's real intent is preserved: where a case *does* ask for content and the
dashboard is empty, the score is still 0.0 (covered by
`tests/test_fix_first.py::test_f3_empty_dashboard_fails_validity_when_widgets_were_expected`).

1-100 and 1-101 are unaffected — they expect widgets and produce them; their
historical F3 zeros came from the pre-PR-04 `_widget_is_valid` bug, already fixed.

If the product stance is "a created dashboard must never be empty", that is a
different assertion and belongs in its own check with its own spec decision on
whether absence is `null` or `0.0` — not folded into a check the case cannot
address.
