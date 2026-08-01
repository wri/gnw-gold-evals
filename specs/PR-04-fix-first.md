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
| F3 | Empty dashboard → widget checks **0.0** (was `None`); `_widget_is_valid` reads `config.text` (was `widget["text"]`, unfulfillable) | rows 1-096, 1-100, 1-101 measured correctly |
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
- [ ] A 3-trial staging run shows every guard at std ≤ 0.04 and zero false
      positives on the known-clean rows from run 6 (69 rows).
- [ ] The run report explicitly lists which checks changed semantics, and
      the first post-PR ledger entry records a `methodology_note` so PR-02
      diffs don't read the fix as agent movement.

## Test plan

Unit tests per fix/guard + the 3-trial validation run committed to the
ledger with its diff-vs-previous annotated.
