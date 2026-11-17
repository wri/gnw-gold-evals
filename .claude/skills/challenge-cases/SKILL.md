---
name: challenge-cases
description: Use when adding, revising or running CHALLENGE cases ("add challenge cases", "write a case by hand", "generate numeric cases", "promote the candidates", "I edited a benchmark member", "run CHALLENGE", "roll up the run"). Covers the ways in, the after-edit steps including members of a draft BENCHMARK version, and the canonical CHALLENGE run and rollup. Not for GOLD cases.
---

# challenge-cases: grow and run the CHALLENGE store

CHALLENGE (`cases/challenge/`) measures how well the agent does, as a pass
rate per set and cohort. Many cases are expected to fail.
[cases/challenge/README.md](../../../cases/challenge/README.md) owns the
procedures; this skill follows them. Terms are defined in
[docs/glossary.md](../../../docs/glossary.md).

## 1. Rules that differ from GOLD

- **GOLD's audit rules do not apply.** Do not run `audit_cases.py --strict`
  here, and do not use GOLD's depth floor or phrasing rules. The doctrine is
  realism: prompts read the way users write them.
- **Never fix a case to make it pass.** A failing case stays `ready`: the
  failure is the data. Change a case only when its expectation is wrong, and
  say why.
- Statuses: `ready` runs, `todo` is held (give `notes.status_reason`),
  `not doing` is retired. Expected ids must be verified against prod before
  they enter the store (`notes.verified`).
- **Uid warning.** Editing a case's query or any expected value gives it a
  new uid. Before the edit, run `grep -l <uid> benchmarks/*.json` and tell
  the user which BENCHMARK versions hold it, with their status.
- **Never edit a member of a frozen version.** Undo the edit, or void the
  member with an entry in that manifest's `errata` list (`uid`, `date`,
  `reason`) and add a new case. See
  [benchmarks/README.md](../../../benchmarks/README.md).

## 2. Ways in

- **Generation pipeline** (new numeric cases: quantification, trend,
  comparison). Steps in [generation/README.md](../../../generation/README.md).
  `--catalog-dir` is the catalogue directory of the user's project-zeno
  checkout: ask for the path, because `../project-zeno` does not exist from
  a worktree.
  ```bash
  uv run python generation/validate_manifest.py --catalog-dir <project-zeno>/src/agent/datasets/catalog
  uv run python generation/generate_cases.py --dataset <slug> --intent <intent> --dry-run
  uv run python generation/generate_cases.py --dataset <slug> --intent <intent>
  ```
  The last command calls the LLM (`ANTHROPIC_API_KEY`) and spends budget:
  say so and get a yes first. Then review every wording in
  `scratch/candidates/` against the cell's `_shared.md` and intent file, and
  promote only the reviewed CSV:
  `uv run python generation/promote_cases.py scratch/candidates/<file>.csv --dry-run`,
  then again without `--dry-run`.
- **Written by hand** (any other case). Follow "Writing a case by hand" in
  the CHALLENGE README: copy a case from the same cohort directory, take the
  set's prefix and the next free number, quote every value as a string,
  leave `uid` out, give `notes.behaviour`, `notes.verified`,
  `notes.lineage` and `notes.difficulty`, then run section 3.
- **Seed CSV** (a new set written as a sheet, imported once). The CSV uses
  the case sheet columns (`test_id`, `status`, `test_group`, `query`,
  `expected_*`; other columns go to notes):
  `uv run python tools/import_sheet.py --csv seeds/<file>.csv --cases-dir cases/challenge --set <set>`.
  Without `--cases-dir` it writes to `cases/v2`, so always pass it. Never
  import an existing seed again: it would overwrite every edit since.

A curated BENCHMARK version needs its cases first:
`tools/benchmark_from_sheet.py` matches sheet rows to existing cases and
stops on a row that no case answers.

## 3. After any edit (in order)

```bash
uv run python tools/check.py --fix --suite challenge
uv run python tools/coverage_doc.py --suite challenge
uv run python tools/check_benchmark.py
```

Stage the case files with `cases/challenge/MANIFEST.json`, `COVERAGE.md`,
`coverage.json` and `cases_index.json`. CI checks all of them.

If `check_benchmark.py` warns that a member of a **draft** lost its uid,
CI fails until the draft is rebuilt. Follow "After an edit", steps 4 to 9,
in the CHALLENGE README:

4. Rebuild the draft from the seed its manifest names in
   `sampling.seed_file`:
   `uv run python tools/benchmark_from_sheet.py --seed <seed> --version <v>`.
   If a query changed, the tool stops ("query differs from the sheet's" or
   "no CHALLENGE case has this query"): copy the seed to a new dated file
   `seeds/benchmark-v2026-bef-<YYYY-MM-DD>.csv`, put the new query in that
   row, and rebuild from the new file. Never edit or rename the old seed.
   Read `git diff` on the case files: the rebuild rewrites members' sheet
   notes.
5. `uv run python tools/check_benchmark.py` prints `ok` with no warning.
6. `uv run python tools/build_run_index.py`: the rebuild changes the
   `canonical` flags of earlier runs.
7. If `benchmarks/overlays/2026-draft-5.plain.json` has an entry for the old
   uid, tell the user: it must move to the new uid, and the repo owner
   reviews the call.
8. Show the user what will be committed, then commit the case edit, store
   files, manifest, any new seed and `results/index.json` together.
9. Offer the rerun of the revised members (the **benchmark-run** skill).

## 4. Run and roll up

Follow "After every run" in the CHALLENGE README. Canonical series: prod,
default profile (no `--ff`), 3 trials. Any other run is a diagnostic run:
never published, and committed only with a recommendations doc that says it
is diagnostic.

```bash
caffeinate -i uv run evals run --suite challenge --env prod --trials 3 --build "<label>"
uv run python tools/challenge_rollup.py results/challenge/runs/<run_id>.json
```

`--suite challenge` skips `todo` and `not doing` cases by default. Run one
set with `--set <name>`. Read rates against `cases/challenge/TARGETS.yml`.
Then write `results/challenge/recommendations/<run_id>.md` (upstream
issues, case-set notes, harness notes, next-run watchlist; rates, never
regression counts; `20260901T131519Z_prod.md` shows the sections). Then:

```bash
git add results/challenge/runs/<run_id>.json results/challenge/recommendations/<run_id>.md
uv run python tools/build_run_index.py
git add results/index.json
```

Show the user what will be committed, then commit run, recommendations and
index together. For BENCHMARK members use **benchmark-run**.
