---
name: sync-catalog
description: Use when project-zeno's dataset catalogue may have changed ("did zeno's datasets change", "refresh the catalog"). Syncs the snapshot, regenerates the coverage files for every store CI checks (CHALLENGE and the GOLD legacy copy), summarises coverage impact.
---

# sync-catalog: dataset coverage refresh

The agent's dataset catalogue (`src/agent/datasets/catalog/*.yml` on
`wri/project-zeno` main) defines dataset ids, dataset-specific parameters,
context layers and per-dataset instruction fields. Each store's
COVERAGE.md (`cases/challenge` and `cases/v2`) reports case coverage
against a committed snapshot of it (`cases/zeno_catalog.json`), so CI needs
no network. Terms are defined in
[docs/glossary.md](../../../docs/glossary.md).

## Steps

1. **Find the project-zeno checkout.** The tool's default, `--zeno`, is the
   `project-zeno` directory next to this checkout. From a worktree under
   `worktrees/` that directory does not exist, so ask the user for the path.
2. **Sync.** The tool reads the checkout's `origin/main` with `git show` and
   never touches its working tree. By default it first runs
   `git fetch origin main` in that checkout, which needs the network:
   ```bash
   uv run python tools/sync_zeno_catalog.py --zeno <path-to-project-zeno>
   # --no-fetch: use origin/main as last fetched; --ref <ref>: another ref
   ```
3. **Diff the snapshot** (`git diff cases/zeno_catalog.json`) and summarise
   in plain terms: datasets added, removed or renamed, parameters or legal
   values changed, context layers added or removed, instruction fields
   appearing or disappearing, and the new source sha.
4. **Regenerate the coverage files for every store CI checks.** The snapshot
   is shared, so both go stale together:
   ```bash
   uv run python tools/coverage_doc.py --suite challenge
   uv run python tools/coverage_doc.py --suite gold
   ```
   Each writes `COVERAGE.md`, `coverage.json` and `cases_index.json` in its
   store. CI runs `coverage_doc.py --check` on both stores.
5. **Read the coverage impact** from each COVERAGE.md's dataset table and
   Known gaps: new gaps (a new dataset with 0 cases, a new parameter no case
   exercises), gaps that disappeared, and any expected `dataset_id` the
   catalogue no longer knows. Those appear on the line "Expected
   `dataset_id` values not in the catalog: ...", which is present only when
   such cases exist; they need attention before the next run. A CHALLENGE
   case in that list may be a BENCHMARK member: run
   `uv run python tools/check_benchmark.py`.
6. **Commit together** (`cases/zeno_catalog.json` plus, for each store,
   `COVERAGE.md`, `coverage.json` and `cases_index.json`) with a message
   naming the project-zeno sha synced. Show the user what will be committed
   first.

## Follow-ups to propose (not to do silently)

- A new catalogue capability with no coverage: suggest cases via the
  **challenge-cases** skill. GOLD cases are written in project-zeno
  `evals/gold/` now; the **new-case** skill covers only the legacy copy.
- A removed dataset or parameter that active cases still expect: triage
  those cases via **case-edit** (stale expectations are parked with
  evidence, not silently). In CHALLENGE, a failing case stays `ready` unless
  its expectation is wrong.
