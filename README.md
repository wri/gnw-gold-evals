# gnw-gold-evals

The **GOLD capability smoke-test set** for the Global Nature Watch (GNW) /
Project Zeno agent — cases, harness, and results ledger in one versioned
repo instead of a live spreadsheet.

GOLD answers one question at release time: **did an agent change break a
capability that used to work?** It is not a quality or accuracy measure
(that is the CHALLENGE programme's job). Consequences: coverage across
capabilities is the design criterion, determinism outranks realism, and the
headline number is a **regression count**, not a mean score.

## Why a repo and not the sheet

The sheet is live and hand-edited: two runs a week apart are not comparable,
edits land mid-run, and nothing records which version of a test a result was
scored against. Here:

- **Every case has a `uid`** — a truncated SHA-256 of its query + all
  non-empty expected values. Editing the prompt or any expectation mints a
  new uid; annotating triage notes does not. Results key on the uid, so a
  score is always pinned to the exact case content it ran against. A result
  carrying a uid the store no longer holds is recorded `stale_case`, never
  re-keyed.
- **Each store has a `caseset_version`** (hash of all uids, in its
  `MANIFEST.json`) — two runs are comparable iff it matches.
- Case edits arrive as **reviewable PRs**, with `tools/check.py` and the
  schema tests keeping uids truthful in CI.

## The two case stores

```
cases/v1/   frozen as-imported baseline (sheet lineage) — re-imports only
cases/v2/   the curated working set — all improvement work lands here
```

Tools default to `v2`. v1 is pinned by `tests/test_v1_frozen.py` (the
caseset_version is recomputed from the case files, so curation leaking into
v1 fails CI). Run the same build against both stores and diff the reports to
measure what curation bought. See `cases/README.md` for authoring rules.

## Quickstart

```bash
uv sync
uv run python -m pytest -q              # 475 tests, no network

# secrets: API_TOKEN (environment-specific) and ANTHROPIC_API_KEY (judge)
# may live in .env — loaded before the token check.

# run the GOLD set against staging (the harness lives here now):
uv run gold run --env staging --trials 3
uv run gold run --env staging --id 1-030 --verbose   # one case
# writes results/runs/<run_id>.json + gzipped raw artifacts

# reports from a ledger run:
uv run python tools/report_run.py results/runs/<run_id>.json   # markdown
uv run python tools/render_html.py results/runs/<run_id>.json  # stakeholder HTML

# regression gate between two runs:
uv run python tools/diff_runs.py results/runs/A.json results/runs/B.json \
  --fail-on-regression            # exit 1 on any real (non-info-only) regression
# add --fail-on-coverage-loss to also fail when checks silently stop evaluating

# after hand-editing any case YAML:
uv run python tools/check.py --fix      # recompute uids + manifest (defaults to v2)
uv run python tools/check.py            # verify only (CI mode)

# case-set hygiene (report-only in CI; --strict to gate):
uv run python tools/audit_cases.py

# sheet bridge (one-way each direction):
uv run python tools/import_sheet.py --gid 0        # sheet -> repo (safe tab imports)
uv run python tools/export_sheet_csv.py            # repo -> sheet-uploadable CSVs
uv run python tools/ingest_run.py --detailed <gnw-evals _detailed.csv> ...  # legacy runs
```

## Layout

```
cases/v1, cases/v2      one YAML per case, grouped by capability; MANIFEST.json each
results/                committed run ledger + reports (contract: results/README.md)
schema/case.schema.json the case contract; every file validated in tests
src/goldset/            store, canonical hashing, ledger, adapter, buckets,
                        evaluator registry, runner/ (API + multiturn), cli (gold)
tools/                  check / audit_cases / import_sheet / export_csv /
                        export_sheet_csv / ingest_run / diff_runs / report_run /
                        render_html / parity / flakiness
docs/                   plans + PR specs (PLAN, CASESET_PLAN, docs/specs/)
.github/workflows/ci.yml  lint + tests + store integrity on PRs; manual staging run
```

## How scoring reads

- Checks are tri-state (`1.0` / `0.0` / `null` = not evaluated) and roll up
  into **five buckets** (retrieval, analysis, explanation, output, scope);
  a run's verdict comes from per-row verdicts and per-bucket tallies, never
  a flat mean. Errored rows are errors, not measurements — they are excluded
  from tallies rather than banking partial passes.
- **Which check answers for which bucket** (full map with descriptions and
  case examples: [`docs/evaluator-map.html`](docs/evaluator-map.html);
  † = shared between two buckets, ° = info-only, never gates):

  | Bucket — the question it answers | Checks |
  |---|---|
  | **Retrieval** — did it understand the question? | `aoi_id_match` `dataset_id_match` `dataset_parameter_match` `context_layer_match` `date_extraction` `data_pull_exists` `pull_source_match` `answered_without_data` `state_delta` |
  | **Analysis** — right numbers? | `chart_integrity` `class_value_match`° `charts_answer`† `agent_answer`† |
  | **Explanation** — prose faithful to the data? | `expected_text_match` `web_fallback` `answer_traceability`° `agent_answer`† |
  | **Output** — artifacts presented correctly? | `chart_produced` `chart_well_formed` `chart_type_match` `dashboard_aoi_match` `dashboard_widgets_match` `dashboard_widgets_valid` `charts_answer`† `dashboard_created`† |
  | **Scope** — right amount of work? | `scope_match` `clarification_requested` `suggested_datasets_match` `nudge_match` `dashboard_created`† |

  `date_coverage` is also info-only (annual datasets always pull their full
  range, so the recorded window flips without the answer being wrong).
- **Multi-turn cases** share one thread; per-turn checks flatten to
  `t<N>.<check>` plus `state_delta` assertions between turns. A turn that
  errors aborts its conversation rather than polluting later turns.
- Gates are built to fail loudly on emptiness: `parity.py` exits nonzero
  when nothing was comparable, `flakiness.py` flags partial samples as
  INSUFFICIENT DATA instead of "stable", and `diff_runs.py` can gate on
  silent coverage loss.

## Status (2026-08-01)

The 12-PR build-out is merged: harness ported from
[gnw-evals](https://github.com/wri/gnw-evals) (behaviour-preserving, then
six inherited scoring defects fixed), bucket scoring + release gate + HTML
report, six new validators, multi-turn support, live-validation campaign
tooling, hardening + CI, sheet pull/push bridges, and the v1/v2 split.
Baseline 3-trial staging campaign committed as run
`20260801T093002Z_staging_experimental` (104 cases; see
`results/campaigns/` and `results/recommendations/`).

Known open items (tracked in specs/case notes, deliberately not papered
over):

- `chart_type` seeding is deferred until live chart types are verified
  (`docs/specs/PR-06-new-validators.md`) — the validator is wired but no
  case exercises it yet.
- `1-062` and `mt-007` are held at `todo`: each needs its dropped/pending
  expectation resolved before activation (see their `status_reason`).
- `1-072` / `1-011` carry relative-date phrasing pending a team call;
  `audit_cases.py` now flags 1-072.
- No per-case info-only mechanism exists yet for judged checks on
  probation (mt-007's caveat) — probation is currently handled by holding
  the case at `todo`.
