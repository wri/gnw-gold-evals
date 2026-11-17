---
name: case-edit
description: Use when changing any case in any store (GOLD cases/v2 or CHALLENGE cases/challenge), whether prompt, expected values, status, notes or park/unpark. Explains uid consequences first, then runs the lifecycle for that store with an explicit --suite, and enforces status-transition rules. For GOLD, also see the legacy-copy note in the body.
---

# case-edit: the case-store lifecycle

One case per YAML file. Every edit ends with the after-edit ritual
(section 5); skipping it fails CI. Terms are defined in
[docs/glossary.md](../../../docs/glossary.md).

## 1. Choose the store (first, out loud)

Ask which store the case lives in, then pass that store's `--suite` to
every command below. Never rely on a default.

| store | `--suite` | notes |
|---|---|---|
| GOLD (legacy copy, `cases/v2`) | `gold` | `cases/v2/<group>/<id>.yaml`; status ladder and audit apply |
| CHALLENGE | `challenge` | `cases/challenge/<set>/<cohort>/<id>.yaml`; no status ladder, no audit; see **challenge-cases** |
| `cases/v1` | none | frozen; never edit it |

## 2. Before touching the file: state the identity consequences

- Editing the **query or any non-empty `expected` value mints a new uid**.
  In a multi-turn case, so does reordering the turns and, where the store's
  MANIFEST.json sets `uid_includes_deltas` (`cases/v2`), changing any turn's
  `deltas`. That is versioning, not an error, but say it out loud: results
  keyed to the old uid drop out of future diffs.
- **`status`, `group`, `set`, `notes`, formatting, key order never affect the
  uid.**
- The uid hashes **all** expected fields, scored or not. Do not move
  expectations into `notes` to avoid uid churn
  (CLAUDE.md, "The identity system").
- **CHALLENGE only:** before the edit, run `grep -l <uid> benchmarks/*.json`
  and report the manifests and their status. A member of a **frozen**
  version is never edited: undo the edit, or void it with an erratum. A
  member of a **draft** keeps its old uid in the manifest until the draft is
  rebuilt, and CI fails until then: section 5 has the steps.

## 3. Make the edit

- `expected:` holds only hashed expectations, keyed by bare field name
  (`answer`, not `expected_answer`); commentary, dates and evidence go in
  `notes:`.
- Multi-turn cases use `turns:` (no top-level query/expected).
- Unknown top-level keys are rejected on read: the schema is the contract.
- If a doc quotes the case, update the quote in the same PR:
  `grep -rn "<id>" README.md CLAUDE.md docs cases/README.md cases/challenge .claude/skills`.

## 4. Status transitions

- **GOLD:** `todo`/`ready` to `done` needs a pass at the case's current uid on
  a 3-trial run with the release baseline's `ff`; cite the run_id and date in
  `notes.status_reason`. Parking (`not doing`) needs a dated `status_reason`
  with evidence. Unparking is probation: re-test it. See
  [cases/README.md, Status lifecycle](../../../cases/README.md#status-lifecycle).
- **CHALLENGE:** statuses are `ready`, `todo` and `not doing`. There is no
  `done`. A failing case stays `ready`. Never change a case to make it pass.

## 5. The ritual (required, in order)

GOLD (`cases/v2`):

```bash
uv run python tools/check.py --fix --suite gold
uv run python tools/coverage_doc.py --suite gold
uv run python tools/audit_cases.py --strict
```

CHALLENGE (no audit):

```bash
uv run python tools/check.py --fix --suite challenge
uv run python tools/coverage_doc.py --suite challenge
uv run python tools/check_benchmark.py
```

If `check_benchmark.py` warns that a member of a draft lost its uid, follow
"After an edit", steps 4 to 9, in
[cases/challenge/README.md](../../../cases/challenge/README.md) (rebuild
the draft, check it, regenerate `results/index.json`, check the plain
overlay, commit together), or hand off to **challenge-cases**.

Stage the case file with the store's `MANIFEST.json`, `COVERAGE.md`,
`coverage.json` and `cases_index.json` in one commit. CI runs the tests,
`audit_cases.py --strict`, `check.py` on all three stores,
`coverage_doc.py --check` on `cases/v2` and `cases/challenge`, and
`check_benchmark.py`.

## Guardrails

- Never edit `cases/v1/`: it is pinned by `tests/test_v1_frozen.py`.
- Never hand-write or backfill results to "confirm" an edit. Run the case:
  `uv run evals run --suite gold --env staging --id <id> --verbose`
  for GOLD, or `uv run evals run --suite challenge --env staging --id <id> --verbose`
  for CHALLENGE (a diagnostic run, never committed as the series).
- An edit that tests a new capability is a new case (new `id`).
