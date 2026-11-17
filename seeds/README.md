# Seeds

CSV files that CHALLENGE cases and BENCHMARK versions were built from. No
run reads them. Once a case is in the store, its YAML file is the source
of truth, and later edits go to the case files, not to these CSVs. How the
three import paths fit together: [cases/challenge/README.md, How cases get
here](../cases/challenge/README.md#how-cases-get-here).

Two layouts appear here:

- **Sheet layout** (the `challenge-*` files): one row per case, with
  `test_id`, `status`, `test_group`, `query`, `expected_*` columns that
  become the case's `expected` block, and other columns that become
  `notes`. `tools/import_sheet.py --csv` reads it.
- **Benchmark sheet layout** (the `benchmark-*` files): one row per
  BENCHMARK question, naming its CHALLENGE case by `challenge_id` or by
  exact query text, plus the facets the scorecards page groups by.
  `tools/benchmark_from_sheet.py --seed` reads it and tells the two
  versions apart by their type column: `benchmark_query_type` (the
  proposed set) or `query_type` (the BEF sheet).

## The files

| File | What it is | Suite | Read by | Status |
|---|---|---|---|---|
| `challenge-aoi-v1.csv` | 131 AOI prompts in the sheet layout, with expected ids verified against prod `/api/aois` on 2026-09-01 | CHALLENGE `aoi` set | `tools/import_sheet.py --csv`, on 2026-09-01: each of those cases has `notes.source_tab: challenge-aoi-v1` | History. The draft-5 review (2026-10-27) changed five of its cases since (`ch-aoi-028`, `-091`, `-116`, `-118`, `-119`), so it no longer matches the store |
| `challenge-dataset-v1.csv` | 200 dataset-selection prompts ("show X on the map") in the sheet layout, with expected values from the project-zeno catalogue at `e2fb83f` | CHALLENGE `dataset` set | `tools/import_sheet.py --csv --set map`, on 2026-09-25, when it was `challenge-map-v1.csv`; the set and the file were renamed on 2026-09-29 | History. One case changed since (`ch-dataset-171` gained `accept_nudge_offering`) |
| `benchmark-v2026-proposed.csv` | The proposed v2026 BENCHMARK set: 199 rows in the older benchmark layout (JTBD jobs, impact pathways, user groups) | BENCHMARK `2026-draft-2`; CHALLENGE Batch 4 | `tools/benchmark_from_sheet.py --seed` built `2026-draft-2`. A Claude Code session drafted 63 CHALLENGE cases from its NEW rows on 2026-10-01 (`notes.expectations` says so); one of them, `ch-mon-028`, was later removed from the CSV | History: `2026-draft-2` is retired |
| `benchmark-v2026-bef-2026-10-22.csv` | The BEF benchmark sheet exported on 2026-10-22: 299 rows in the BEF layout (use cases UC1 to UC6, engagement, AOI type, capability, grounding, fixture) | BENCHMARK `2026-draft-3`; CHALLENGE Batch 5 | `tools/benchmark_from_sheet.py --seed` built `2026-draft-3`. A Claude Code session drafted 168 CHALLENGE cases from its rows on 2026-10-23 | History (`2026-draft-3` is retired), and the file to restore the Ghana questions from once PZB-1408 is fixed. **Do not rename it**: 168 case files record this file name in `notes.expectations` |
| `benchmark-v2026-bef-2026-10-26.csv` | The 22 October export with the queries of eight Ghana questions moved to Côte d'Ivoire, because the analytics API rejects Ghana's sub-national GADM ids (PZB-1408) | BENCHMARK `2026-draft-4` | `tools/benchmark_from_sheet.py --seed` | History: `2026-draft-4` is retired |
| `benchmark-v2026-bef-2026-10-27.csv` | The 26 October file with four more queries changed in the draft-5 review (two moved off Ghana, two reworded) and one row's dates | BENCHMARK `2026-draft-5` | `tools/benchmark_from_sheet.py --seed` | **Input.** Rebuilding `2026-draft-5`, or building the `2026` version from it, reads this file |

## Rules

- **Do not import a seed CSV again.** `tools/import_sheet.py` writes the
  CSV's values over the cases it imported before, so a second import
  would undo every edit made to those cases since.
- **Do not rename a seed.** Case notes and BENCHMARK manifests
  (`sampling.seed_file`) record seed file names.
- `cases/challenge/MANIFEST.json` still names `challenge-map-v1.csv` in its
  `source` field: `tools/check.py --fix` keeps the `source` it finds, and
  the last import before the rename wrote that name. It is a label, not a
  path, and nothing else reads it.
