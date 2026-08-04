---
name: new-case
description: Use when authoring a new GOLD case — "add a case for…". Interviews for the capability, maps expected fields to checks, enforces authoring rules and verified answers before done.
---

# new-case — author a case that earns its place

GOLD is a capability smoke test: a case earns its place by failing when a
capability breaks, deterministically. Full authoring rules: `cases/README.md`.

## 1. Interview first

- **Which capability** is being smoke-tested, and which of the five buckets
  (retrieval / analysis / explanation / output / scope) should fail if it
  breaks? One case, one job.
- **Coverage-driven:** check `cases/v2/COVERAGE.md` → Known gaps and the
  dataset-coverage table before inventing a scenario. Current standing gaps:
  unused expected fields (`chart_type`, `suggested_datasets`), unexercised
  dataset parameters and context layers.
- Single-turn or multi-turn (state carried across turns)?

## 2. Map intent → expected fields → checks

Every non-empty `expected` field switches on specific checks — the census
table in COVERAGE.md is the authoritative map (e.g. `aoi_ids` →
`aoi_id_match`, `answer` → `agent_answer`/`charts_answer`/`chart_produced`,
`dataset_parameters` → `dataset_parameter_match`). Only set fields you intend
to be graded on; reference-only context goes in `notes:`. Check semantics:
`src/goldset/evaluators/README.md`.

## 3. Authoring rules (the DON'Ts that bite)

- **Determinism over realism**: no relative dates ("last year"), no phrasing
  the agent can defensibly satisfy two different ways — unless ambiguity *is*
  the capability (nudge/clarification cases), in which case grade the nudge.
- Don't name the dataset in the prompt when dataset *selection* is what's
  being tested; alternatives (`0;11`) are allowed when the answer is
  dataset-independent — record why in notes.
- Numbers in expectations come from code/API verification, never estimated.
- `id` is the lineage handle (`1-NNN` / `mt-NNN`, next free number); group
  slug picks the directory.

## 4. Verify before `done`

- Run it: `uv run gold run --env staging --ff experimental --id <id>
  --verbose` — the expected `answer` must come from a verified measurement
  (this run, or the analytics API directly).
- Status ladder: land as `ready` (or `todo` with a dated blocking note) if
  unverified; `done` only after a **3-trial `--ff experimental`** pass at the
  final uid (cite run_id in `notes.status_reason`).

## 5. Finish with the lifecycle ritual

Hand off to the **case-edit** skill (or do its ritual): `check.py --fix` →
`coverage_doc.py` → `audit_cases.py` → commit case + MANIFEST + COVERAGE
together. `tests/test_schema.py` validates the file shape in CI.
