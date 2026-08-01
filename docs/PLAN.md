# gnw-gold-evals — repo plan

**The GOLD half of the five-bucket coverage plan, operationalised as this
repo.** Parent document: `gnw-evals/.claude/reports/five-bucket-coverage-plan.md`
(2026-07-31), which holds the full evidence base; this file holds only the
decisions that shape *this* repo and the PR sequence that builds it.

---

## 1. Charter

GOLD is a **capability smoke test**. Its one job: fail when a release breaks
a capability that used to work, and pass otherwise.

Three consequences drive every design decision here:

1. **Coverage is the design criterion.** A capability with no case ships
   untested; a coverage gap is a worse defect than a low score.
2. **Determinism outranks realism.** Anything that makes a case fail for
   reasons unrelated to the agent — relative dates, judge flakiness, a sheet
   edited mid-run — disqualifies it.
3. **The headline is a regression count, not a mean score.** "N capabilities
   that passed at release N−1 now fail" is what a smoke test reports.
   Percentages reward adding easy checks; regression counts don't.

Quality/accuracy measurement (ground truth, misleading-answer rate,
intent × dataset scorecard) is the **CHALLENGE** programme and explicitly
out of scope here.

## 2. The case store

### 2.1 Format: one YAML per case, in git

- `cases/<group>/<id>.yaml` — see `schema/case.schema.json`. One case per
  file means one case per diff hunk: PR review, blame, and revert all work
  at the granularity the set is actually edited at.
- `expected:` holds only non-empty expectations, keys without the
  `expected_` prefix, values verbatim strings as the harness consumes them.
- `notes:` holds annotations (`status_reason`, `aoi_type`, the
  `class_*`/`value_*` scratchpads). Never scored, never hashed.

### 2.2 Identity: the uid

`uid = sha256(canonical_json({query, non-empty expected}))[:16]`
(`src/goldset/canonical.py`).

| Edit | uid |
|---|---|
| Prompt wording, any expected value, adding/removing an expectation | **changes** — this is a new version of the test |
| Status, group, notes, key order, surrounding whitespace, CRLF | unchanged — triage must not mint versions |

Design choice: the hash covers **all** expected fields, scored or not
(e.g. `dataset_name`, which the harness treats as reference-only). The
alternative — hashing only scored fields — would churn every uid whenever a
new validator makes a field scored. Stability of the rule beats minimality
of the hash.

The lineage id (`id:`, the sheet's `test_id`) survives edits, so a test's
history is `id` + the sequence of uids git records for it.

### 2.3 Set identity

`caseset_version = sha256(sorted uids)` in `cases/MANIFEST.json`. Two runs
are comparable iff it matches; when it doesn't, comparisons run over the
intersection of uids (see `results/README.md`).

### 2.4 Relationship to the sheet

Import is **one-way and destructive-by-agreement**: sheet → repo via
`tools/import_sheet.py`, after which *this repo is the source of truth* and
edits happen as PRs (`check.py --fix` keeps uids honest, CI runs `check.py`).
The sheet remains the team's staging/triage surface for as long as they want
it; a re-import is a reviewable PR whose diff *is* the sheet delta. If both
were edited, the PR diff surfaces the conflict — there is no silent merge.

### 2.5 Running today

`tools/export_csv.py` emits a gnw-evals-compatible CSV (uid in a trailing
column, which gnw-evals ignores). Until PR-03 lands the ported harness, runs
execute in gnw-evals against that export, and PR-02's ingester carries
results back here keyed by uid.

## 3. Results ledger

Committed per-run JSONs under `results/runs/` — contract in
`results/README.md`, fixed from day one so early runs stay comparable.
Key properties: results key on `uid` + `caseset_version`; checks are
tri-state (`1.0`/`0.0`/`null`); regression diffs run over uid
intersections; no hand-written entries.

## 4. Scoring system (lands in PR-05)

1. **Per row**: binary verdict — every applicable check passes.
2. **Per bucket** (Retrieval / Analysis / Explanation / Output / Scope):
   checks passed / evaluated, always printed **beside the coverage
   denominator** (rows with ≥1 applicable check). An unmeasured bucket must
   be visibly different from a passing one.
3. **Per release — the gate**: diff per-uid-per-check against the previous
   run. Regression = pass→fail (majority across 3 trials for judged checks;
   single trial for deterministic — they hold ±0.00–0.04 std). Headline:
   **"N regressions, M new coverage holes."**
4. **Reconciliation line** every run: checks implied by the case set vs
   checks actually evaluated. The parent plan documents four ways checks
   silently vanish today; this line makes that class of bug self-announcing.

Admission rules for new checks: deterministic checks ship after a clean run
against known-good rows; judged checks run **info-only** until they show
std ≤ 0.10 over 3 trials (the two flakiest sheet-era judges sat at ±0.29 and
±0.23 — the cautionary precedent).

## 5. Roadmap — the PR sequence

| PR | Spec | What lands | Depends on |
|---|---|---|---|
| 01 | `docs/docs/specs/PR-01-case-store.md` | **This initial commit** — case store, uid identity, import/export/check tools | — |
| 02 | `docs/docs/specs/PR-02-results-ledger.md` | Run-ingest from gnw-evals outputs, `diff_runs.py` regression tool | 01 |
| 03 | `docs/docs/specs/PR-03-harness-port.md` | Runner + validators ported from gnw-evals, behaviour-preserving | 01 |
| 04 | `docs/docs/specs/PR-04-fix-first.md` | The six inherited harness debts + four trivial deterministic guards | 03 |
| 05 | `docs/docs/specs/PR-05-bucket-scoring.md` | Five-bucket registry, row verdicts, regression gate, reconciliation line | 02, 04 |
| 06 | `docs/docs/specs/PR-06-new-validators.md` | The bucket-filling validators (A2, A3, E1, O2, O3, S1) + new expected fields | 05 |
| 07 | `docs/docs/specs/PR-07-multiturn.md` | Multi-turn runner + 8 scripted 2-turn cases + state-delta checks | 05 |
| 08 | `docs/docs/specs/PR-08-live-validation.md` | The staging campaign clearing every live-run acceptance box (parity, guard stds, seed flakiness, G4 pinning, judge probation review) | 02–07, staging token |
| 09 | `docs/docs/specs/PR-09-hardening-and-ci.md` | CI workflow + defects found while building 02–07 (ingest drift re-keying, merge_trials error loss, multiturn reconciliation, dataset_id alternatives) | 07 |

Ordering rationale: results tracking (02) and a faithful port (03) can
proceed in parallel; fixes (04) deliberately land *after* the
behaviour-preserving port so parity is verifiable; scoring (05) needs both
the ledger and honest checks; new validators (06) and multiturn (07) extend
a system that can already measure itself; 08 is runs rather than code and
09 can land in parallel with it.

The case set itself has its own plan: **`docs/CASESET_PLAN.md`** (strategy)
and **`docs/caseset-implementation-plan.md`** (execution: v1/v2 stores,
sheet round-trip, per-workstream steps) — coverage
rebalance, determinism scrub, expectation depth, dead-weight triage, and
the authoring checklist. Harness design lives here; what's *in* `cases/`
lives there.

## 6. Working agreements

- **Numbers in code; structure and semantics to the judge.** No LLM judge is
  ever asked to do arithmetic (gnw-evals' `chart_numeric` precedent).
- **Every check decides deliberately whether an absence is `null` (not
  applicable) or `0.0` (failure)** — and the spec for the check must say
  which and why.
- Judge prompts put **reasoning before score** in their structured output.
- Case edits and re-imports are PRs; `tools/check.py` gates CI.
- Env-gated capabilities (dashboards and `send_nudge` are absent on prod as
  of 2026-07-30) are marked in case `notes`, and runs record `environment` +
  `build` so their zeros are never read as agent regressions.
