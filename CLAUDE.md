# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The GOLD **capability smoke-test set** for the GNW / Project Zeno agent, as a
versioned repo replacing a live Google Sheet. GOLD answers one question per
release: *did an agent change break a capability that used to work?* It is
not a quality measure — the headline is a **regression count**, never a mean
score, and determinism outranks realism in every design call.

Read `PLAN.md` before proposing changes; `specs/PR-0N-*.md` sequence the
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

Runs currently execute via the **gnw-evals bridge**: export a CSV (above),
then in `../gnw-evals` run `uv run gnw_evals --test-file <abs path> ...`.
The exported `uid` column rides along ignored and keys results back here.
The harness moves in-repo at PR-03.

## The identity system (load-bearing — do not break)

`src/goldset/canonical.py` defines everything downstream trusts:

- **`uid`** = `sha256(canonical_json(query + non-empty expected values))[:16]`.
  Changing the prompt or any `expected` value mints a new uid — that is the
  versioning mechanism, not an error. `status`, `group`, `notes`, key order,
  whitespace, and CRLF never affect it: triage must not mint versions.
- The hash deliberately covers **all** expected fields, scored or not
  (PLAN.md §2.2 has the rationale — don't "optimise" it to scored-only).
- **`caseset_version`** in `cases/MANIFEST.json` hashes all sorted uids.
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
- `cases/<group-slug>/<id>.yaml` — one case per file so PR review/blame/
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

## Working agreements (from PLAN.md §6)

- Numbers in code; structure and semantics to the judge — no LLM judge is
  ever asked to do arithmetic.
- Every check's spec decides whether an absence scores `null` (n/a) or
  `0.0` (failure), and says why.
- Judged checks run info-only until they show std ≤ 0.10 over 3 trials.
- Judge structured outputs put reasoning before the score field.
