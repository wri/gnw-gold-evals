---
name: case-edit
description: Use when changing any GOLD case — prompt, expected values, status, notes, park/unpark. Explains uid consequences first, then runs the full lifecycle (check --fix, coverage doc, audit) and enforces status-transition rules.
---

# case-edit — the case-store lifecycle

One case per YAML file under `cases/v2/<group>/<id>.yaml`. Every edit ends
with the after-edit ritual (section 4); skipping it fails CI. Terms are
defined in the [README glossary](../../../README.md#glossary).

## 1. Before touching the file: state the identity consequences

- Editing the **query or any non-empty `expected` value mints a new uid**.
  In a multi-turn case, so does reordering the turns and, in `cases/v2`,
  changing any turn's `deltas`. That is versioning, not an error, but say it
  out loud: results keyed to the old uid drop out of future diffs (no later
  run shares that uid), so the case needs re-verification at its new uid
  before it can be trusted (or stay `done`).
- **`status`, `group`, `notes`, formatting, key order never affect the uid.**
  Triage annotations are free.
- The uid hashes **all** expected fields, scored or not (for example
  `dataset_name`, which no check reads). This is deliberate: a result stays
  pinned to the exact case content it ran against. Do not move expectations
  into `notes` to avoid uid churn. The identity rules are in CLAUDE.md ("The
  identity system").

## 2. Make the edit

- `expected:` holds only hashed expectations, keyed by bare field name
  (`answer`, not `expected_answer`); commentary, dates and evidence go in
  `notes:`.
- Multi-turn cases use `turns:` (no top-level query/expected) with optional
  `deltas` (`changed` / `retain` / `absent`) from turn 2 on.
- Unknown top-level keys are rejected on read: the schema is the contract.
- If a doc quotes the case, update the quote in the same PR:
  `grep -rn "<id>" README.md CLAUDE.md cases/README.md src/goldset/evaluators/README.md .claude/skills`.

## 3. Status transitions (with teeth)

What each status means: [cases/README.md, Status lifecycle](../../../cases/README.md#status-lifecycle).

- **`todo`/`ready` → `done`:** requires a pass at the case's *current uid* on
  a 3-trial run with the same `ff` as the release baseline (the default
  profile, no `--ff`, unless the case tests something behind
  `experimental`). Cite the run_id and date in `notes.status_reason`. A
  1-trial pass is a smoke signal, not verification.
- **Parking (`not doing`):** always a dated `status_reason` carrying the
  evidence (which run, what the agent did, why the case can't earn a verdict).
- **Unparking:** treat it as probation. Re-test the reason it was parked on a
  real run; never assume it was fixed.
- A parked (`not doing`) case is excluded from runs; everything else runs.

## 4. The ritual (required, in order)

```bash
uv run python tools/check.py --fix           # recompute uids and the manifest
uv run python tools/coverage_doc.py          # regenerate cases/v2/COVERAGE.md
uv run python tools/audit_cases.py --strict  # CI's audit gate: exits 1 on any depth or DON'T violation
```

Stage the case file, `cases/v2/MANIFEST.json` and `cases/v2/COVERAGE.md`
**together** in the same commit. CI runs the test suite (including
`tests/test_schema.py`), `audit_cases.py --strict`, `check.py` on both stores
and `coverage_doc.py --check`; any one failing fails the PR. The ritual is
described in [README, Changing cases](../../../README.md#changing-cases).

## Guardrails

- Never edit `cases/v1/`: it is the frozen baseline, pinned by
  `tests/test_v1_frozen.py`. Curation goes to v2 only
  ([cases/README.md, The two stores](../../../cases/README.md#the-two-stores)).
- Never hand-write or backfill results to "confirm" an edit. Run the case:
  `uv run gold run --env staging --id <id> --verbose`.
- If an edit really tests a new capability, write a new case (new `id`)
  rather than changing what an existing `id` tests.
