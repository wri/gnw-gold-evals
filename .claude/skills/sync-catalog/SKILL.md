---
name: sync-catalog
description: Use when project-zeno's dataset catalog may have changed — "did zeno's datasets change", "refresh the catalog". Syncs the snapshot, regenerates COVERAGE.md, summarises coverage impact.
---

# sync-catalog — dataset coverage refresh

The agent's dataset catalog (`src/agent/datasets/catalog/*.yml` on
`wri/project-zeno` main) defines dataset ids, dataset-specific parameters,
context layers, and per-dataset instruction fields. COVERAGE.md reports case
coverage against a committed snapshot of it (`cases/zeno_catalog.json`) so CI
needs no network. Background: CLAUDE.md §"Dataset coverage against
project-zeno".

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
3. **Regenerate the doc:**
   ```bash
   uv run python tools/coverage_doc.py
   ```
4. **Read the coverage impact** from COVERAGE.md's dataset table and Known
   gaps: new gaps (a new dataset with 0 cases, a new parameter no case
   exercises), disappeared gaps, and any expected `dataset_id` in cases that
   the catalog no longer knows (that line names the ids — those cases need
   attention before the next run).
5. **Commit both files together** (`cases/zeno_catalog.json` +
   `cases/v2/COVERAGE.md`) with a message naming the zeno sha synced.

## Follow-ups to propose (not to do silently)

- New catalog capability with zero coverage → suggest cases via the
  **new-case** skill.
- A removed dataset/parameter that active cases still expect → triage those
  cases via **case-edit** (stale expectations park with evidence, not
  silently).
