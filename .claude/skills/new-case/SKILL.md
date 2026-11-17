---
name: new-case
description: Use when authoring a new GOLD case ("add a case for…"). Interviews for the capability, maps expected fields to checks, enforces authoring rules and verified answers before done.
---

# new-case: author a case that earns its place

GOLD is a capability smoke test: a case earns its place by failing when a
capability breaks, deterministically. Full authoring rules:
[cases/README.md](../../../cases/README.md). Terms are defined in the
[README glossary](../../../README.md#glossary).

## 1. Interview first

- **Which capability** is being smoke-tested, and which of the five buckets
  (retrieval / analysis / explanation / output / scope) should fail if it
  breaks? One case, one job.
- **Coverage-driven:** read `cases/v2/COVERAGE.md` (Known gaps and the
  dataset-coverage table) before inventing a scenario. First check the
  catalogue snapshot's sync date (in COVERAGE.md's dataset section); if it
  is old, run the **sync-catalog** skill so you do not fill gaps for
  datasets the agent no longer has.
- Do not author cases on `suggested_datasets`: the agent replaced that state
  field with `nudge`, so test dataset suggestions with
  `nudge_type: dataset_choice` and `nudge_options` (or `scope: suggest`).
- Single-turn or multi-turn (state carried across turns)?

## 2. Map intent → expected fields → checks

Every non-empty `expected` field switches on specific checks.
`implied_checks()` in `src/goldset/buckets.py` is the authoritative map; the
census table in COVERAGE.md summarises it. For example, `aoi_ids` switches on
`aoi_id_match`, and `answer` switches on `agent_answer`, `chart_produced`,
`data_pull_exists` and `answered_without_data`. Only set fields you intend to
be graded on; reference-only context goes in `notes:`. What each check
measures: [evaluators README index](../../../src/goldset/evaluators/README.md#index).

## 3. Authoring rules (the DON'Ts that bite)

- **Determinism over realism**: no relative dates ("last year"), no phrasing
  the agent can defensibly satisfy two different ways, unless ambiguity *is*
  the capability (nudge/clarification cases), in which case grade the nudge.
- Don't name the dataset in the prompt when dataset *selection* is what's
  being tested. `dataset_id: "<a>;<b>"` accepts either dataset; use it only
  when both give the same answer, and record why in notes. (`;` means
  "either" in `dataset_id` and `scope`, but "all of these" in `aoi_ids`.)
- Numbers in expectations come from code/API verification, never estimated.
- `id` is the lineage handle (`1-NNN` / `mt-NNN`, next free number); group
  slug picks the directory.

## 4. Verify before `done`

- Run it: `uv run gold run --env staging --id <id> --verbose`. The expected
  `answer` must come from a verified measurement (this run, or the analytics
  API directly).
- Status ladder: land as `ready` (or `todo` with a dated blocking note) if
  unverified; `done` only after a pass at the final uid on a 3-trial run with
  the release baseline's `ff` (the default profile unless the case tests
  something behind `experimental`); cite the run_id in `notes.status_reason`.
  What each status means:
  [cases/README.md, Status lifecycle](../../../cases/README.md#status-lifecycle).

## 5. Finish with the lifecycle ritual

Hand off to the **case-edit** skill, or run its ritual yourself:
`check.py --fix`, then `coverage_doc.py`, then `audit_cases.py --strict`,
then commit the case, `MANIFEST.json` and `COVERAGE.md` together.
`tests/test_schema.py` validates the file shape in CI.
