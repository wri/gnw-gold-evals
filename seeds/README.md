# Seeds

CSV files that CHALLENGE cases and BENCHMARK versions were built from. No
run reads them. They are used in two ways:

- The `challenge-*` files were each **imported once** into case files.
  Since then the case YAML files are the source of truth, and edits go to
  them, never to these CSVs.
- The `benchmark-*` files are **read again** by
  `tools/benchmark_from_sheet.py` every time a curated BENCHMARK version is
  built or rebuilt. Each manifest names the file it was built from in
  `sampling.seed_file`.

How the ways cases come into the store fit together:
[cases/challenge/README.md, How cases get
here](../cases/challenge/README.md#how-cases-get-here).

## Layouts

- **Case sheet layout** (the `challenge-*` files): one row per case, with
  `test_id`, `status`, `test_group`, `query` and `expected_*` columns that
  become the case's `expected` block, and other columns that become
  `notes`. `tools/import_sheet.py --csv` reads it.
- **Benchmark sheet layout** (the `benchmark-*` files): one row per
  BENCHMARK question. A row names its CHALLENGE case by `challenge_id` or by
  exact query text, and carries the facets the scorecards page groups by.
  `tools/benchmark_from_sheet.py --seed` reads it and tells two versions of
  the layout apart by their type column: `benchmark_query_type` (the
  proposed set) or `query_type` (the later sheet, whose exports carry `bef`
  in their file names).

## The files

| File | What it is | Status |
|---|---|---|
| `challenge-aoi-v1.csv` | 131 area prompts in the case sheet layout | imported once (2026-09-01) into the `aoi` set; history |
| `challenge-dataset-v1.csv` | 200 "show X on the map" prompts in the case sheet layout | imported once (2026-09-25) into the `dataset` set; history |
| `benchmark-v2026-proposed.csv` | the proposed v2026 BENCHMARK set, 199 rows, with Jobs to be Done numbers, impact pathways and user groups | built `2026-draft-2`; history |
| `benchmark-v2026-bef-2026-10-22.csv` | the benchmark sheet exported on 2026-10-22, 299 rows, with use cases UC1 to UC6 and other facets | built `2026-draft-3`; history. It holds the original wording of the questions later moved off Ghana |
| `benchmark-v2026-bef-2026-10-26.csv` | the 2026-10-22 export with eight Ghana questions moved to Côte d'Ivoire | built `2026-draft-4`; history |
| `benchmark-v2026-bef-2026-10-27.csv` | the 2026-10-26 file with four more queries and one row's dates changed | **input**: rebuilding `2026-draft-5` reads it |

The Ghana questions moved because the analytics API rejects Ghana's
sub-national GADM ids; the fix is the project-zeno Jira ticket PZB-1408
([cases/challenge/CHANGELOG.md](../cases/challenge/CHANGELOG.md)).

## Rules

- **Do not import a `challenge-*` seed again.** `tools/import_sheet.py`
  writes the CSV's values over the cases it imported before, so a second
  import would undo every edit made to those cases since.
- **Do not edit a committed seed.** When a member's query changes, copy the
  input seed to a new dated file (`benchmark-v2026-bef-<YYYY-MM-DD>.csv`),
  change that row, and rebuild the draft from the new file
  ([After an edit](../cases/challenge/README.md#after-an-edit)). The old
  file becomes history, and each manifest keeps naming the exact input it
  was built from.
- **Do not rename a seed.** Case notes and BENCHMARK manifests
  (`sampling.seed_file`) record seed file names: for example, every case
  drafted from `benchmark-v2026-bef-2026-10-22.csv` names it in
  `notes.expectations`.
- `cases/challenge/MANIFEST.json` still names `challenge-map-v1.csv`, the
  dataset seed's name before the set was renamed, in its `source` field.
  `tools/check.py --fix` keeps the `source` it finds. It is a label, not a
  path, and nothing else reads it.
