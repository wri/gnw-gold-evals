# PR-01 — Content-addressed case store

**Status: implemented by the initial commit.** Kept as a spec so the repo's
first PR is reviewable against stated intent like every later one.

## Goal

Replace the live Google Sheet as GOLD's source of truth with a versioned,
PR-reviewable case store in which every case version and every set version
is content-addressed.

## Why

- The sheet drifts under runs (it changed between the 2026-07-31 morning
  snapshot and the same afternoon's pull), edits are unreviewed, and no
  record ties a result to the version of the test it scored.
- 43 sheet edits landed between two runs on 2026-07-30; the score movement
  was uninterpretable. Content-addressing makes "same test?" a mechanical
  question.

## Scope

**In:** `src/goldset/` (canonical hashing, store), `tools/import_sheet.py`,
`tools/export_csv.py`, `tools/check.py`, `schema/case.schema.json`, tests,
the imported 2026-07-31 case set (107 cases), `cases/MANIFEST.json`.

**Out:** running anything (export bridges to gnw-evals), results
(PR-02), any validator or scoring change.

## Design

- `uid = sha256(canonical_json({query, non-empty expected}))[:16]`;
  metadata/notes excluded. Rationale for hashing *all* expected fields
  (scored or not): PLAN.md §2.2.
- `caseset_version = sha256(sorted uids)[:16]` in a generated, committed
  manifest.
- One YAML per case at `cases/<group-slug>/<id>.yaml`; unknown top-level
  keys rejected on read; import is idempotent (unchanged sheet ⇒
  byte-identical files) so re-import diffs are pure sheet deltas.
- Import column routing: `expected_*` → hashed expectations; everything
  else (`status_reason`, `AOI type`, `note_*`) → unhashed notes. Duplicate
  test_ids abort; empty-query rows are skipped and counted.

## Acceptance criteria

- [x] Re-running the importer on the same CSV changes no files.
- [x] `check.py` fails on a hand-edited case until `--fix` recomputes its
      uid; CI can run `check.py` verbatim.
- [x] `export_csv.py --status-exclude "not doing"` produces a CSV the
      gnw-evals loader accepts unchanged (header-compatible, uid trailing).
- [x] Every committed case validates against `schema/case.schema.json`
      (parametrised test, 107 files).
- [x] Unit tests cover: uid stability (key order, whitespace, CRLF, empty
      fields), uid movement (query/expectation edits), set-version
      order-insensitivity, round-trip fidelity, duplicate detection,
      header-scan with preamble rows, prune behaviour.

## Test plan

`uv run python -m pytest` — 131 tests (24 unit + 107 schema conformance).
Manual: import → check → export → run 3 exported rows through gnw-evals
against staging and confirm the loader's `✓ Expected fields detected` line
lists the same fields the sheet run showed.
