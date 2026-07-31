# PR-03 — Harness port (behaviour-preserving)

## Goal

Make this repo self-contained: port the gnw-evals runner and the validators
GOLD needs, reading cases from the store and writing the results ledger
directly — with **zero scoring-behaviour changes** (fixes are PR-04, so
parity stays verifiable).

## Why

The export-CSV bridge works but keeps GOLD's execution coupled to a repo
whose evaluators are evolving for other purposes, and the bridge loses
signals at the CSV boundary (decoded codeact, tool-call sequences, widget
bodies) that PR-06's validators need.

## Scope

**In:** async runner (`POST /api/chat` streamed, `GET /threads/{id}/state`,
dashboard fetch), the validator set below, a `runs` CLI
(`uv run gold run --env staging --trials 3`), direct ledger writing
(PR-02 contract), raw-signal capture (see Design), config via `.env`/flags.

**Out:** any behaviour change to a check (PR-04); new checks (PR-06);
multiturn (PR-07); the sheet loader (the store is the only case source).

## Porting tiers (from the parent plan's inventory)

| Tier | Validators | Adaptation |
|---|---|---|
| Drop-in | `agent_answer`, `expected_text_match`, `clarification`, `suggested_datasets`, `nudge`, `dashboard_created` | state-key names only |
| Adapter | `date_extraction` (tool/arg names into config), `dataset_*`, `data_pull_exists`, `date_coverage` (stays info-only) | small config surface |
| Domain modules | `aoi_id_match` (GADM normaliser), `chart_numeric` + structure-only chart judge, dashboard sub-checks | ported together with their state-shape assumptions, current gnw-evals HEAD (`5a377cd`: 2% tolerance, numeric override in code) |

Known-broken-by-design carryovers ported **verbatim** and listed in the
parity report (fixed in PR-04): the four `None`-instead-of-`0` vanishing
checks, `_widget_is_valid`'s `text` key, judge exception swallowing, the
80k chart-JSON truncation.

## Design

- Evaluators register in a small registry (name, kind, score fields,
  required expectations) — the shape `eval-metrics-slice-1` proved; PR-05
  adds bucket tags to it.
- **Capture more than we score**: persist per-case raw artefacts
  (`results/artifacts/<run_id>/<uid>.json.gz`, gitignored) holding the
  decoded codeact summary, tool-call sequence (name/args/output truncated),
  `statistics[-1]` payload, and dashboard widget bodies. The committed
  ledger stays small; the artefacts make triage and future validators
  possible without re-running.
- Judge model pinned in config (`claude-haiku-4-5`, temp 0); judge prompts
  ported byte-identical this PR.

## Acceptance criteria

- [ ] **Parity run**: same staging build, ledger via PR-02 ingest (old
      path) vs direct write (new path), 3 trials — per-check majority
      verdicts agree on every case, excepting only documented
      judge-sampling noise (list any disagreement with its two reason
      strings).
- [x] All ported validators carry their gnw-evals unit tests, passing.
- [x] No network in unit tests; runner tested against recorded fixtures.
- [x] `uv run gold run --help` documents every flag; no `.env` silently
      overriding CLI defaults (the gnw-evals landmine — flags win, always).

## Test plan

Ported test files per validator + fixture-backed runner tests + the manual
parity run recorded in the PR description.
