# tools/ — the CLI surface

Thin CLIs over `src/goldset/` (they add `src/` to `sys.path` directly).
Everything runs as `uv run python tools/<tool>.py`; the live harness itself
is the `gold` entry point (`uv run gold run …`, see the root README and
CLAUDE.md). Tools never hand-write ledger entries — see `results/README.md`
for the contract they all respect.

## Case store

| tool | what it does |
|---|---|
| `check.py` | Verify (or `--fix`: repair) case-store integrity: uids, schema validity, manifest. **`--fix` is required after hand-editing any case YAML**; plain `check.py` is the CI gate. |
| `audit_cases.py` | Case-set hygiene audit: depth, coverage floors, DON'T violations. Report-only by default; `--strict` to gate. |
| `coverage_doc.py` | Regenerate `cases/v2/COVERAGE.md` from the store + catalog snapshot. **Required after any case edit**; `--check` is the CI freshness gate. |
| `sync_zeno_catalog.py` | Refresh `cases/zeno_catalog.json` from project-zeno `origin/main` (dataset ids, dataset-specific parameters, context layers, instruction fields). Follow with `coverage_doc.py`. |

## Sheet bridge (one-way each direction)

| tool | what it does |
|---|---|
| `import_sheet.py` | Import a GOLD Google-Sheet tab (CSV export or `--url`) into the case store. Idempotent; `--prune` for removals. |
| `export_sheet_csv.py` | Export the case store as sheet-uploadable CSVs. |
| `export_csv.py` | Export the store to a gnw-evals-compatible CSV (kept for triage). |

## Results ledger

| tool | what it does |
|---|---|
| `diff_runs.py` | Regression diff between two runs over their uid intersection. `--fail-on-regression` / `--fail-on-coverage-loss` to gate. Only compare runs with the same trial count and `ff`. |
| `flakiness.py` | Flakiness table from a multi-trial run (`--per-case` for detail); flags partial samples as INSUFFICIENT DATA. |
| `compose_runs.py` | Compose a current picture from a primary run plus scoped supplements — analysis-side only, never writes to `results/runs/` (see results/README.md §Composing). |
| `ingest_run.py` | Ingest a legacy gnw-evals `*_detailed.csv` into the ledger (historical runs only; in-repo runs write the ledger directly). |
| `parity.py` | Old-path vs new-path parity for the 2026-08-01 harness port (PR-08 step 1; historical). |

## Reports

| tool | what it does |
|---|---|
| `report_run.py` | Markdown four-layer GOLD report for one run (PR-05). |
| `render_html.py` | Standalone stakeholder HTML report; `--all` builds the cross-run page with a run-selector dropdown. |
| `render_inspector.py` | Per-check inspection matrix; `--all` for the cross-run page. |
| `render_trends.py` | Pass-rate ticker across all ledger runs — never read trends across a differing `ff`. |

## After-run ritual

After every run, in order: `render_html.py` (+ `--all`, `render_inspector.py
--all`, `render_trends.py`), then `flakiness.py` + `diff_runs.py` against the
last comparable run, then write `results/recommendations/<run_id>.md`, then
commit run + report + recommendation together. CLAUDE.md has the full
checklist.
