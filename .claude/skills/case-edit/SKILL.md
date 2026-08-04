---
name: case-edit
description: Use when changing any GOLD case — prompt, expected values, status, notes, park/unpark. Explains uid consequences first, then runs the full lifecycle (check --fix, coverage doc, audit) and enforces status-transition rules.
---

# case-edit — the case-store lifecycle

One case per YAML file under `cases/v2/<group>/<id>.yaml`. Every edit ends
with the same ritual; skipping it fails CI.

## 1. Before touching the file: state the identity consequences

- Editing the **query or any non-empty `expected` value mints a new uid**.
  That is versioning, not an error — but say it out loud: results keyed to
  the old uid become `stale_case` in future comparisons, and the case needs
  re-verification at its new uid before it can be trusted (or stay `done`).
- **`status`, `group`, `notes`, formatting, key order never affect the uid.**
  Triage annotations are free.
- The uid hashes **all** expected fields, scored or not — do not "optimise"
  expectations into notes to avoid churn (docs/specs/PLAN.md §2.2 has the
  rationale; it's deliberate).

## 2. Make the edit

- `expected:` holds only hashed expectations (prefix-stripped); commentary,
  dates, and evidence go in `notes:`.
- Multi-turn cases use `turns:` (no top-level query/expected) with optional
  `deltas` (`changed` / `retain` / `absent`) from turn 2 on.
- Unknown top-level keys are rejected on read — the schema is the contract.

## 3. Status transitions (with teeth)

- **`todo`/`ready` → `done`:** requires verification at the case's *current
  uid* on a **3-trial `--ff experimental`** run. Cite the run_id and date in
  `notes.status_reason`. A 1-trial pass is a smoke signal, not verification.
- **Parking (`not doing`):** always a dated `status_reason` carrying the
  evidence (which run, what the agent did, why the case can't earn a verdict).
- **Unparking:** treat as probation re-admission — the reason it was parked
  must be re-tested, not assumed fixed. 1-011 was unparked prematurely once;
  don't repeat it.
- A parked (`not doing`) case is excluded from runs; everything else runs.

## 4. The ritual (required, in order)

```bash
uv run python tools/check.py --fix        # recompute uids + manifest
uv run python tools/coverage_doc.py       # regenerate COVERAGE.md
uv run python tools/audit_cases.py        # hygiene; surface NEW violations
```

Stage the case file, `cases/v2/MANIFEST.json`, and `cases/v2/COVERAGE.md`
**together** in the same commit. CI runs `check.py` and
`coverage_doc.py --check`; either one stale fails the PR.

## Guardrails

- Never edit `cases/v1/` — it is the frozen sheet-lineage baseline, pinned by
  `tests/test_v1_frozen.py`. Curation goes to v2 only.
- Never hand-write or backfill results to "confirm" an edit — run the case:
  `uv run gold run --env staging --ff experimental --id <id> --verbose`.
- If an edit is really a new capability probe, prefer a new case (new `id`)
  over mutating an existing lineage.
