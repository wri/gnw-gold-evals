# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The GOLD **capability smoke-test set** for the GNW / Project Zeno agent, as a
versioned repo replacing a live Google Sheet. GOLD answers one question per
release: *did an agent change break a capability that used to work?* It is
not a quality measure — the headline is a **regression count**, never a mean
score, and determinism outranks realism in every design call.

Read `docs/PLAN.md` before proposing changes; `docs/specs/PR-0N-*.md` sequence the
build (case store → results ledger → harness port → fixes → bucket scoring →
new validators → multiturn). Work arrives as one PR per spec, and each spec
states its acceptance criteria. The parent evidence base is
`gnw-evals/.claude/reports/five-bucket-coverage-plan.md`.

## Commands

```bash
uv sync                                  # install (Python >=3.11, hatchling layout)
uv run pytest                            # full suite
uv run pytest tests/test_canonical.py -q               # one file
uv run pytest tests/test_store.py::test_write_read_round_trip  # one test

# case-store lifecycle
uv run python tools/check.py             # verify uids + manifest (CI gate; nonzero on drift)
uv run python tools/check.py --fix       # REQUIRED after hand-editing any case YAML
uv run python tools/import_sheet.py --csv <export.csv>   # or --url; idempotent; --prune for removals
uv run python tools/export_csv.py --out scratch/gold.csv --status-exclude "not doing"
```

Runs execute in-repo (the gnw-evals bridge was retired after the
2026-08-01 parity run; `export_csv.py` remains for triage):

```bash
export API_TOKEN="$STAGING_API_TOKEN"   # .env holds it; the CLI reads API_TOKEN
uv run gold run --env staging --trials 3 --build "<label>"
```

Official runs are **3 trials, always** — the agent flaps on ~45% of rows
between identical trials, so single-trial verdicts are smoke only.

## After every run (do all four, in order)

1. **Render the report**: `uv run python tools/render_html.py
   results/runs/<run_id>.json` → `results/reports/<run_id>.html`
   (the template also accepts a run JSON by drag-and-drop).
2. **Flakiness + diff**: `uv run python tools/flakiness.py
   results/runs/<run_id>.json --per-case`, and `tools/diff_runs.py
   <previous> <current>` against the last comparable run.
3. **Write `results/recommendations/<run_id>.md`** — the run is not done
   until someone can act on it. Cover: what to file upstream (agent
   behaviour, with the flapping/failing row lists as evidence), what the
   run says about the case set (stale expectations, coverage holes,
   probation re-admissions), what it says about the harness, and a
   next-run watchlist. `results/recommendations/20260801T093002Z.md` is
   the model.
4. **Commit** the ledger JSON, the report, and the recommendation doc
   together; use `--note` on the run whenever check semantics changed
   since the previous one.

## The identity system (load-bearing — do not break)

`src/goldset/canonical.py` defines everything downstream trusts:

- **`uid`** = `sha256(canonical_json(query + non-empty expected values))[:16]`.
  Changing the prompt or any `expected` value mints a new uid — that is the
  versioning mechanism, not an error. `status`, `group`, `notes`, key order,
  whitespace, and CRLF never affect it: triage must not mint versions.
- The hash deliberately covers **all** expected fields, scored or not
  (docs/PLAN.md §2.2 has the rationale — don't "optimise" it to scored-only).
- **`caseset_version`** in per-store `MANIFEST.json` (cases/v1, cases/v2) hashes all sorted uids.
  Results (see `results/README.md`) key on uid + caseset_version; regression
  diffs run over uid intersections between runs.
- `id` (the sheet's `test_id`) is the stable lineage handle across versions.

Consequently: any edit to a case file must be followed by
`tools/check.py --fix`, and CI-style verification is plain `check.py`.
`tests/test_schema.py` validates every case file against
`schema/case.schema.json`, so a malformed case fails the suite, not a run.

## Architecture

- `src/goldset/` — the library: `canonical.py` (hashing) and `store.py`
  (frozen `Case` dataclass, YAML read/write, manifest). Tools in `tools/`
  are thin CLIs over it, adding `src/` to `sys.path` directly (the package
  is also installed editable via uv).
- `cases/v{1,2}/<group-slug>/<id>.yaml` (v1 = imported baseline, v2 = curated working set; see cases/README.md) — one case per file so PR review/blame/
  revert work per case. `expected:` = hashed expectations, prefix-stripped;
  `notes:` = unhashed annotations. Unknown top-level keys are rejected on
  read. Import routes sheet columns by prefix: `expected_*` → expected,
  everything else → notes.
- `results/` — committed per-run JSON ledger (contract fixed in
  `results/README.md` even though the ingester lands in PR-02). Checks are
  tri-state `1.0/0.0/null`; **no hand-written or backfilled entries, ever**.
- Sheet relationship is **one-way**: import sheet → repo; the repo is the
  source of truth and re-imports are reviewable PRs whose diff is the sheet
  delta. Import is byte-idempotent on an unchanged sheet.

## Working agreements (from docs/PLAN.md §6)

- Numbers in code; structure and semantics to the judge — no LLM judge is
  ever asked to do arithmetic.
- Every check's spec decides whether an absence scores `null` (n/a) or
  `0.0` (failure), and says why.
- Judged checks run info-only until they show std ≤ 0.10 over 3 trials.
- Judge structured outputs put reasoning before the score field.
