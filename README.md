# gnw-gold-evals

The **GOLD capability smoke-test set** for the Global Nature Watch (GNW) /
Project Zeno agent — as a versioned repo instead of a live spreadsheet.

GOLD answers one question at release time: **did an agent change break a
capability that used to work?** It is not a quality or accuracy measure
(that is the CHALLENGE programme's job). Consequences: coverage across
capabilities is the design criterion, determinism outranks realism, and the
headline number is a **regression count**, not a mean score.

This repo holds the **cases** (one YAML per case, content-addressed), the
**results ledger** (committed per-run JSONs, keyed to exact case versions),
and — incrementally, see `specs/` — the harness that runs them.

## Why a repo and not the sheet

The sheet is live and hand-edited: two runs a week apart are not comparable,
edits land mid-run, and nothing records which version of a test a result was
scored against. Here:

- **Every case has a `uid`** — a truncated SHA-256 of its query + all
  non-empty expected values. Editing the prompt or any expectation mints a
  new uid; annotating triage notes does not. Results key on the uid, so a
  score is always pinned to the exact case content it ran against.
- **The set has a `caseset_version`** (hash of all uids, in
  `cases/MANIFEST.json`) — two runs are comparable iff it matches.
- Case edits arrive as **reviewable PRs**, with `tools/check.py` keeping the
  uids truthful in CI.

## Quickstart

```bash
uv sync
uv run python -m pytest                 # 131 tests

# re-import from the sheet (one-way: sheet -> repo; see PLAN.md §2.4)
uv run python tools/import_sheet.py \
  --url "https://docs.google.com/spreadsheets/d/1_G1aq2fSCPqhT6w55_Od6VU7sov76t1lHQTBeZZxbdM/export?format=csv&gid=0"

# after hand-editing any case YAML:
uv run python tools/check.py --fix      # recompute uids + manifest
uv run python tools/check.py            # verify only (CI mode)

# run the set today, via the existing gnw-evals harness:
uv run python tools/export_csv.py --out scratch/gold.csv --status-exclude "not doing"
# then in ../gnw-evals:
#   uv run gnw_evals --test-file <path to gold.csv> --sample-size -1 \
#     --api-base-url https://api.staging.globalnaturewatch.org --num-workers 5
```

## Layout

```
cases/                  one YAML per case, grouped by capability (test_group)
  MANIFEST.json         generated: caseset_version + id->uid index
results/                committed run ledger (contract in results/README.md)
schema/case.schema.json the case contract; every file is validated in tests
src/goldset/            canonical hashing + store library
tools/                  import_sheet / export_csv / check
specs/                  PR specs — the build sequence, one md per PR
PLAN.md                 the repo plan: design decisions, scoring, roadmap
```

## Status

Initial slice (PR-01): case store imported from the sheet snapshot of
2026-07-31 — 107 cases, `caseset_version 2f8b10272938527c`. The harness
still lives in [gnw-evals](https://github.com/wri/gnw-evals); the export
bridge above runs today's set unchanged. See `PLAN.md` for what lands next.
