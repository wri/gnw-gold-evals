---
name: sync-catalog
description: Use when project-zeno's dataset catalogue may have changed ("did zeno's datasets change", "refresh the catalog"). Syncs the snapshot, regenerates the coverage files for every store CI checks (GOLD and CHALLENGE), summarises coverage impact.
---

# sync-catalog: dataset coverage refresh

The agent's dataset catalogue (`src/agent/datasets/catalog/*.yml` on
`wri/project-zeno` main) defines dataset ids, dataset-specific parameters,
context layers and per-dataset instruction fields. Each store's COVERAGE.md
(`cases/v2` and `cases/challenge`) reports case coverage against a committed
snapshot of it (`cases/zeno_catalog.json`), so CI needs no network, and
explains how cases are counted against it. Terms
are defined in the [README glossary](../../../README.md#glossary).

## Steps

1. **Sync** (reads the sibling checkout's `origin/main` via `git show`; never
   touches its working tree):
   ```bash
   uv run python tools/sync_zeno_catalog.py            # default: ../project-zeno
   # --zeno <path> / --ref <ref> / --no-fetch to override
   ```
2. **Diff the snapshot** (`git diff cases/zeno_catalog.json`) and summarise in
   plain terms: datasets added/removed/renamed, parameters or legal values
   changed, context layers added/removed, instruction fields
   appearing/disappearing, and the new source sha.
3. **Regenerate the coverage files for every store CI checks.** The snapshot
   is shared, so both go stale together:
   ```bash
   uv run python tools/coverage_doc.py --cases-dir cases/v2
   uv run python tools/coverage_doc.py --cases-dir cases/challenge
   ```
   Each writes `COVERAGE.md`, `coverage.json` and `cases_index.json` in its
   store. CI runs `coverage_doc.py --check` on both stores.
4. **Read the coverage impact** from each COVERAGE.md's dataset table and
   Known gaps: new gaps (a new dataset with 0 cases, a new parameter no case
   exercises), disappeared gaps, and any expected `dataset_id` the catalogue
   no longer knows. Those appear on the line "Expected `dataset_id` values
   not in the catalog: ...", which is present only when such cases exist; they
   need attention before the next run. A CHALLENGE case in that list may be a
   BENCHMARK member: run `uv run python tools/check_benchmark.py`.
5. **Commit together** (`cases/zeno_catalog.json` plus, for each store,
   `COVERAGE.md`, `coverage.json` and `cases_index.json`) with a message
   naming the zeno sha synced.

## Follow-ups to propose (not to do silently)

- New catalogue capability with zero coverage: suggest cases via the
  **new-case** skill for GOLD, or **challenge-cases** for CHALLENGE.
- A removed dataset/parameter that active cases still expect: triage those
  cases via **case-edit** (stale expectations park with evidence, not
  silently). In CHALLENGE, a failing case stays `ready` unless its
  expectation is wrong.
