# Case-set plan — making the cases serve GOLD's purpose

**How to evolve the 115 cases so the set actually does its one job: fail
when a release breaks a capability, pass otherwise.** Companion to
`PLAN.md` (which owns harness design); this file owns what's *in*
`cases/`. Numbers below are from a store audit on 2026-08-01
(caseset `185eb0b1bb6ea24a`: 107 single-turn + 8 multiturn).

A good GOLD case has four properties, in priority order:

1. **Capability-anchored** — it exercises one nameable thing the product
   does; if it fails, you know what broke.
2. **Deterministic** — it fails only when the agent changes: no relative
   dates, no expectations that drift with data updates, no judged check
   where a rule suffices.
3. **Checkable in depth** — its expectations imply checks in every bucket
   the capability touches, so the reconciliation line stays at zero and a
   pass measured nothing is impossible.
4. **Honest about environment** — rows for capabilities absent from an
   environment (dashboards, `send_nudge` on prod) carry an `env_gated`
   note so their zeros are never read as agent regressions.

---

## Where the set stands

| Fact | Number | Reading |
|---|---|---|
| Dataset coverage | TCL (id 4): **38** rows; sLUC (9): **1**; fires (10): **1**; GHG flux (6): **3**; tree cover (7): 4; integrated alerts (11): 4 | A capability with one row is one flaky row away from shipping untested. TCL is over-served the way Retrieval was over-served in the old suite — it's the easiest thing to author. |
| No `dataset_id` expectation | 15 rows | Legitimate for metadata/suggestion/nudge rows; audit the remainder. |
| Thin rows (≤1 expectation) | 4 (the `metadata` group, 1-065..068) | Text-only is *correct* for their capability, but they should carry `scope` so Scope coverage includes them. |
| `scope` populated | 82/107 | The 25 without are mostly prose-clarify rows blocked on the S3 prose-nudge detector, plus the metadata group. |
| `chart_type` populated | **0** | Validator shipped in PR-06; population needs a human pass — no mechanical derivation is defensible. |
| `class_values` populated | 4 | The Analysis bucket's only expectation-driven coverage. The `class-comparison` group (9 rows) is exactly the shape A2 wants and is unpopulated. |
| Relative-date queries | 2 (1-011 "past decade", 1-072 "most recent year") | Determinism risk: 1-011's window drifts annually. 1-072 only asserts dataset routing, so it survives — but its pattern shouldn't spread. |
| `not doing` rows | 12 | Dead weight carrying triage gold in `status_reason` (1-106 recommends its own deletion; 1-003 documents a defensible-either-way dataset dispute). |
| Known-flaky rows (run 5, 3 trials) | 19 — concentrated in `charts_answer` (8) and `date_extraction` (5) | Flakiness is where the agent is nondeterministic (chart choice, date windows), not where it's wrong. Cases should not stake pass/fail there. |

## The workstreams

### W1 — Coverage rebalance (a capability with no case ships untested)

- **Floor of 3 rows per capability group.** Today: refusal **1**, ranking
  **1**, imagery **1**, dataset-parameters **1**, context-layer **2**,
  usable nudge rows **2**. Source new rows from the March 156-prompt
  benchmark (`eval-benchmark-prompts.md`) — its guardrail (10),
  parameter (23) and chart-type (7) prompts come with hand-written judge
  instructions that map directly onto `expected_text`; they need only
  expectation-mechanisation, not authoring.
- **Floor of 3 rows per dataset.** sLUC (9) and fires (10) are one row
  each — and the March benchmark has *zero* prompts for ids 10/11, so
  these must be authored. sLUC's crop/gas parameters are its whole point;
  its rows should carry `dataset_parameters` expectations.
- Don't grow TCL. 38 rows re-test the same routing path; cap it and let
  CHALLENGE own TCL depth.

### W2 — Determinism scrub (a flaky case is worse than no case)

- Rewrite 1-011 onto a fixed window ("2015–2024"), or onto an alert
  dataset where date-scoped pulls are real.
- **Strip date expectations from annual-dataset rows** (parent finding
  §6.1: the agent pulls the full range and slices in code; the recorded
  window flips between runs while the answer stays right). Let
  `expected_answer` carry the year; keep date expectations for DIST-ALERT
  / integrated alerts / imagery only.
- Work the 19-row flaky list from run 5: where the flap is `charts_answer`
  (8 rows), the fix is usually moving the load off the judge — add
  `chart_type` (accepting alternatives: `bar;table`) and `class_values`
  so the deterministic checks carry the verdict; where it's
  `date_extraction` (5 rows), it's usually W2's annual-dataset rule.
- 1-112-class AOI ambiguity (BRA vs BRA.14.8_2 on identical input):
  either the query names the admin level explicitly or the row's AOI
  expectation is dropped to the country level the GADM normaliser
  already collapses to.

### W3 — Expectation depth (kill the measured-nothing pass)

- **Populate `class_values` on the class-comparison group** (9 rows) from
  their own queries' per-class figures — takes dedicated Analysis coverage
  from 4 rows to ~13, the single cheapest bucket win left.
- **`chart_type` human pass**: seed from what run 6 actually produced on
  rows where the choice was uncontroversial (trend → `line`, share of a
  whole → `pie;table`, ranking → `bar;table`), and set expectations only
  where the team would defend them in review. Accepting alternatives is
  the point — a single-value expectation on a genuinely-multiple-valid
  row is W2 debt.
- Finish `scope`: metadata rows → `analyse`-without-pull is wrong, so
  these need the S3 prose-clarify/none distinction or a `metadata` scope
  value — decide when S3 lands; prose-clarify rows stay unpopulated until
  then.
- Adopt a **row minimum**: every `ready`/`done` case implies ≥2 checks in
  ≥2 buckets (the reconciliation tooling from PR-05 makes this a one-line
  audit). The metadata group is the only sanctioned exception.

### W4 — Dead-weight triage (12 rows, each fix-or-retire)

Every `not doing` row gets exactly one of three outcomes, recorded in its
`status_reason`:

1. **Unpark** — the blocker is harness-side and now fixed or specced:
   1-003's dataset dispute is resolved by PR-09 H7 (`dataset_id: "0;11"`
   alternatives); re-status to `ready`.
2. **Rewrite** — the intent is right but the row breaks a determinism
   rule; author a compliant replacement under the same lineage id.
3. **Delete** — 1-106 ("call send_nudge directly") tests plumbing, not
   capability, and its own status_reason recommends deletion. Deleting a
   case is a reviewable PR like any other edit.

### W5 — Multiturn growth (gated on PR-08 data)

Hold at the 8 seeds until the PR-08 flakiness table exists. Then: one
additional case per scenario class that proved stable; drop-or-loosen any
seed with a flapping deterministic check. The `env_gated` note (mt-002,
mt-008 carry it) becomes mandatory for any row touching dashboards or
nudges. Three-turn conversations remain out of scope — CHALLENGE territory.

### W6 — Process (how edits stay honest)

- **Authoring checklist** in the PR template: capability named; no
  relative dates; no expectation that drifts with data versions;
  expectations imply ≥2 checks in ≥2 buckets; env-gating noted; judged
  checks only where no rule can serve.
- Every case PR runs `check.py` (CI, PR-09 H1) — uid truthfulness is
  non-negotiable; uid churn is *expected* on semantic edits and the PR
  description says why the semantics changed.
- **Reconciliation zero** is the standing target: any run whose report
  itemises a MISSING implied check is either a harness bug or a case bug,
  and it gets an owner before the next release run.
- Re-import from the sheet remains one-way and becomes rarer as the repo
  is edited directly; when it happens, the import diff *is* the review.

## Sequencing and measures of done

| Order | Work | Done when |
|---|---|---|
| 1 | W4 triage + W2 scrub (small, unblocks trust) | 0 rows in `not doing` without a recorded outcome; 0 relative-date windows; annual-date expectations stripped |
| 2 | W3 depth (class_values, chart_type pass, scope finish) | Analysis ≥13 dedicated rows; reconciliation delta = 0 on a full run; every ready row meets the 2×2 minimum |
| 3 | W1 rebalance | every capability group ≥3 rows; every dataset id ≥3 rows; TCL capped |
| 4 | W5 multiturn growth | gated on PR-08 flakiness table |

The measure that matters at the end: **a release run whose report needs no
footnotes** — verdict counts with zero uncovered rows, five bucket lines
each with real denominators, reconciliation at zero, and a regression
count someone can act on without opening a single trace.
