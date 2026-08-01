# Case-set implementation plan

**The execution layer for `docs/CASESET_PLAN.md`** — that file says *what*
and *why*; this one says *how*, per workstream, with the tooling each step
needs. Two structural pieces land first because everything else uses them:
the v1/v2 store split (done) and the sheet round-trip (specced here).

---

## 0. The v1/v2 store split — DONE 2026-08-01

```
cases/v1/   as-imported baseline (sheet lineage). Changes: re-imports only.
cases/v2/   curated working set. All W1–W6 edits land here as PRs.
```

- The stores are deliberately *not* identical: v1 is the as-imported
  baseline (`185eb0b1bb6ea24a`, pre-H7, pinned by `tests/test_v1_frozen.py`);
  v2 carries the H7 unparking of 1-003 (`d564c1b3b4786bc0`). The delta
  between them is the point. Tools default to `v2`,
  `--cases-dir cases/v1` pins the baseline; CI verifies both.
- **Comparison protocol**: same build, same day —
  `gold run --cases-dir cases/v1 --trials 3` and the same for v2, then
  `tools/report_run.py` on each. The v2-improvement claim is the delta in:
  rows clean, bucket coverage denominators, reconciliation misses, and
  flap count (`tools/flakiness.py`). Because runs record
  `caseset_version`, ledger history stays unambiguous about which store
  produced which numbers.
- v1 is not sacred forever: once v2 has carried two clean release runs,
  v1 collapses to a git tag and the split retires (avoid maintaining two
  sets longer than the comparison needs).

## 1. Sheet round-trip (pull ⇄ push)

The team's authoring surface stays Google Sheets
(`SPREADSHEET_ID=1_G1aq2fSCPqhT6w55_Od6VU7sov76t1lHQTBeZZxbdM`); the repo
stays the source of truth. Direction rules: **pull lands in v2 as a PR
whose diff is the review; push publishes v2 state back so sheet editors
see current truth.**

### 1.1 Pull: new tab → versioned YAML (extend `tools/import_sheet.py`)

New tabs (e.g. a `gold-v2-additions` tab someone authors in Sheets) are
pulled by gid — the number after `#gid=` in the tab's URL:

```bash
uv run python tools/import_sheet.py --gid 123456789   # NEW flag
# expands to https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID/export?format=csv&gid=...
# SPREADSHEET_ID from env/.env; destination defaults to cases/v2
```

Work items:

| # | Change | Why |
|---|---|---|
| P1 | `--gid` flag + `SPREADSHEET_ID` env; keep `--url`/`--csv` | one-command pull per tab |
| P2 | Record `notes.source_tab: <gid-or-name>` on every imported case | provenance + scoped pruning |
| P3 | **Scope `--prune` to the tab being imported** (only delete cases whose `source_tab` matches) | today's prune deletes *every* orphan in the dir — a partial-tab import into v2 would silently delete the rest of the set. Fix before any new-tab pull. |
| P4 | Id-collision policy: a new-tab row whose `test_id` already exists in v2 **errors** unless `--update` is passed (then it's an edit, visible in the PR diff) | no silent overwrites across tabs |
| P5 | Sheet `uid` column, if present, is ignored on pull (always recomputed) and compared: rows whose sheet-uid ≠ recomputed uid are listed in the import summary as "edited on sheet since last push" | drift visibility for humans |

Every pull ends with `check.py --fix` + a PR. The import diff *is* the
review; conflicts (sheet edited + repo edited) surface as ordinary diff
conflicts on the case file.

### 1.2 Push, phase 1 — CSV for manual upload (`tools/export_sheet_csv.py`, new)

No credentials, works today:

```bash
uv run python tools/export_sheet_csv.py --out scratch/push/
# writes: cases.csv       (the tab replacement)
#         changelog.csv   (append to a 'changelog' tab)
```

- `cases.csv` columns: `test_id, status, status_reason, test_group, query,
  expected_* (re-prefixed, incl. chart_type/scope/class_values), uid,
  last_changed` — `uid` and `last_changed` (last commit date touching the
  file, via `git log -1 --format=%cs -- <path>`) are the row-wise version
  markers sheet editors can see but must not edit.
- `changelog.csv` rows: `test_id, old_uid, new_uid, date, commit,
  subject` — derived from `git log --follow -p` over each case file,
  diffing the stored `uid:` line per commit. Append-only into a dedicated
  changelog tab, so the sheet carries the full version history without
  anyone maintaining it by hand.
- Multi-turn cases export to a separate `cases-multiturn.csv` (turn-per-row
  with a `turn` column) or are skipped with a note — decide when the first
  multiturn row needs sheet visibility; skipping is the phase-1 default.
- Upload is manual: File → Import → Replace current sheet (cases tab),
  and paste-append for the changelog tab.

### 1.3 Push, phase 2 — direct write (`tools/push_sheet.py`, new, optional)

Only worth building if the manual step becomes a drag:

- Auth: Google service account (`google-api-python-client` +
  `GOOGLE_SERVICE_ACCOUNT_JSON` env pointing at the key file; the sheet is
  shared with the SA's email as editor). No OAuth flows in CI.
- Mechanics: `values.batchUpdate` keyed by `test_id`; writes the same
  columns as phase 1; appends changelog rows to the changelog tab.
- Safety: `--dry-run` prints the cell-level diff first; the push **refuses
  rows where the sheet's uid column ≠ the last-pushed uid AND the sheet's
  editable cells differ from repo state** — that's a human edit on the
  sheet that hasn't been pulled; the error says "pull first" (same
  conflict model as git).
- Never runs unattended: manual invocation or `workflow_dispatch` only.

### 1.4 What stays true throughout

- The repo's uid/`caseset_version` remain the only identity that matters;
  sheet columns are projections.
- A tab is an *inbox or a mirror*, never a second source of truth.
- `data/`-style snapshots are unnecessary — the pull PR is the snapshot.

## 2. W1 — Coverage rebalance

Target: every capability group ≥3 rows, every dataset id ≥3 rows, TCL
capped at its current 38.

1. **Mechanise the March benchmark** (`~/Desktop/from bigmac/
   eval-benchmark-prompts.md` + `benchmark-26032026.csv`): select the
   guardrail (10), parameter (23) and chart-type (7) prompts. Conversion
   is a scratch script per batch: query verbatim; judge-instruction →
   `text`; canopy/filter/intersection specs → `dataset_parameters` /
   `context_layer`; chart-type answers → `chart_type` (with
   `;`-alternatives); scope from the prompt's nature (`refuse` for
   guardrails, `analyse` otherwise). New ids in a fresh `2-xxx` range —
   never reuse `1-xxx`. Land as 2–3 PRs of ≤15 cases each so review is
   real, tab-import optional (author straight to YAML; push publishes
   them to the sheet afterwards).
2. **Author the uncovered-dataset rows by hand** — sLUC (9) and fires (10)
   have one row each and *zero* benchmark prompts. Source facts from the
   project-zeno catalog YAMLs (`src/agent/datasets/catalog/*.yml` —
   prompt_instructions/cautions name the parameters that matter). sLUC
   rows must exercise crop/gas parameters; fires rows the fires/non-fires
   split. 3 rows each, quant-shaped, closed windows.
3. **Acceptance**: `tools/audit_cases.py` (new, W3 builds it) shows no
   group and no dataset below 3; the run report's bucket denominators
   move accordingly.

## 3. W2 — Determinism scrub

1. **Enumerate mechanically** (scratch script over the store): rows with
   `start_date`/`end_date` on annual datasets (dataset_id ∈ {2,4,5,6,7,8,
   9,10} where dates aren't the pull's real scope) → strip dates, let
   `answer` carry the year. Rows with relative-date phrasing → rewrite to
   closed windows (1-011 is the known one; the audit greps for the
   pattern list in `cases/README.md`).
2. **Work the flakiness table, not the old list**: the PR-08 campaign's
   3-trial `tools/flakiness.py --per-case` output supersedes run-5's
   19-row list. For every flapping row: chart-choice flap → add
   `chart_type` alternatives or move the assertion to `class_values`;
   date flap → apply rule 1; AOI flap (1-112 class) → name the admin
   level in the query or drop the AOI expectation to country level.
3. **Acceptance**: next 3-trial run's flap list contains no case that was
   scrubbed (new flappers get triaged, not batched in).

## 4. W3 — Expectation depth

1. **`class_values` for the class-comparison group** (9 rows): values come
   from the rows' own expected answers/notes where present, else one
   fact-finding staging run to read the observed per-class figures, then
   human sign-off that they're right (never auto-promote observed values
   — that's testing the agent against itself).
2. **`chart_type` human pass**: generate a candidates CSV from the latest
   run's artifacts — `id, query, observed chart types across trials,
   proposed expectation` (propose only where all trials agreed;
   `;`-alternatives otherwise). Team reviews the CSV; a scratch script
   applies the approved column. This is the one workstream step that
   cannot be automated honestly.
3. **`tools/audit_cases.py`** (new): per-case implied-check depth (the
   ≥2-checks-in-≥2-buckets rule), group/dataset coverage counts, DON'T
   violations (relative dates, annual-dataset dates, judged-only rows).
   Runs in CI as a report step (non-blocking until W1–W4 land, then the
   depth rule becomes blocking).
4. **Scope finish** blocked on S3 (prose-nudge detection) for the
   prose-clarify rows; metadata rows get scope when the classifier grows
   a `metadata` observable class — until then they stay the sanctioned
   judged-only exception.

## 5. W4 — Dead-weight triage

Mechanical first pass: script lists the 12 `not doing` rows with their
`status_reason`. Then one short review session assigns each of the three
outcomes (unpark / rewrite / delete) from `docs/CASESET_PLAN.md` §W4:

- Already done: 1-003 (unparked via H7 alternatives).
- Known deletes: 1-106 (its own note recommends it).
- The rest get a one-line decision recorded in `status_reason` and land
  as a single triage PR — deletions are just file removals + `check.py
  --fix`, visible in the diff.

## 6. W5 — Multiturn growth

Gated on the PR-08 campaign's seed flakiness table (in flight). Then:

1. Any seed with a flapping deterministic check: loosen or demote to
   `todo` before growing.
2. One new case per stable scenario class, authored per the multiturn
   DON'Ts in `cases/README.md` (fixed turn text; deltas over exact
   values where AOI ids are unverifiable).
3. `env_gated` notes mandatory for dashboard/nudge turns.
4. Re-audit with `flakiness.py --per-case` on the next 3-trial run before
   the next growth round. Three-turn conversations stay out (CHALLENGE).

## 7. W6 — Process

- `cases/README.md` is the authoring guide (done, 2026-08-01).
- `.github/pull_request_template.md` (new, small): the mechanics
  checklist from the README's last section.
- CI already gates `check.py` on both stores; `audit_cases.py` joins it
  as a report (W3), then as a gate.
- Standing target: a release run whose reconciliation line is zero and
  whose report needs no footnotes.

## 8. Sequencing

| Order | Work | Depends on | Size |
|---|---|---|---|
| 1 | P1–P5 sheet-pull hardening (P3 prune-scoping before any new-tab pull) | — | S |
| 2 | W4 triage + W2 mechanical scrub | campaign flakiness table (in flight) | S |
| 3 | `audit_cases.py` + PR template (W3.3, W7) | — | S |
| 4 | W3 depth (class_values, chart_type pass) | 3, one staging run | M |
| 5 | W1 rebalance (benchmark mechanisation + sLUC/fires authoring) | 3 | M–L |
| 6 | Push phase 1 (export_sheet_csv) | stable v2 | S |
| 7 | W5 multiturn growth | campaign seed table | S |
| 8 | Push phase 2 (service account) | 6 proving tedious | M |
| 9 | v1 retirement to a tag | two clean v2 release runs | XS |
