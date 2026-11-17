# Numeric-case generation (CHALLENGE)

This pipeline writes the numeric CHALLENGE cases: the `quantification`,
`comparison` and `trend` sets. It came from `eval-metrics-slice-1` in
gnw-evals, the eval harness this repo replaced (github.com/wri/gnw-evals,
retired); the CHALLENGE store is now the home of these cases.

The cases are generated from the dataset catalogue and an intent taxonomy,
never from stored answers. **The LLM only ever writes prompt wordings.
Every expected value is built mechanically** from the manifest row and
`dataset_config.py`, so a generated case cannot bring in a wrong
expectation.

Hierarchy: CHALLENGE **set = intent** (`quantification`, `trend`,
`comparison`), **cohort = dataset** (short names in `dataset_config.py`).
The generated expectations score retrieval (dataset, area, dates, explicit
parameters) and `data_pull`. Checking the figures in an answer came later,
through `figure` formulas added by hand ([cases/challenge/CHANGELOG.md](../cases/challenge/CHANGELOG.md),
Batch 2 and the draft-5 review).

## The pieces

| Piece | What it is |
|---|---|
| `manifests/<slug>__<intent>.manifest.csv` | the permutation manifest for one dataset and intent: one row per combination a well-tested cell must cover. It is the denominator of prompt coverage |
| `<slug>/_shared.md` and `<slug>/<intent>.md` | the wording rules for each cell, taken from the catalogue's `prompt_instructions` and cautions |
| `dataset_config.py` | per-dataset settings: intents, date mode, canopy default, forest layers, CHALLENGE cohort name |
| `validate_manifest.py` | checks every manifest against the catalogue YAMLs and reports prompt coverage from the store |
| `generate_cases.py` | asks an LLM for the missing wordings of each manifest row and writes them to `scratch/candidates/<slug>__<intent>.candidates.csv` (gitignored) |
| `promote_cases.py` | turns reviewed candidate rows into case files in `cases/challenge/<intent>/<cohort>/` |

## Manifest columns

Each manifest has the columns its dataset needs, so copy the header of the
file you add to. `validate_manifest.py` checks them:

| Column | Holds |
|---|---|
| `manifest_id` | the row's id, unique in its file, in the file's pattern (`m-ialert-trend-01`); it must start with `m-`. Cases record it in `notes.manifest_id` |
| `intent` | the file's intent; it must be one the dataset allows in `dataset_config.py` |
| `eval_subtype` | the question shape, such as `direction`, `monthly_trend` or `two_country`; required |
| `aoi_ids` | one or more ISO3 country codes (GADM level 0), separated by `;` |
| `start_year`, `end_year` | for datasets whose date mode is `years`: 4-digit years inside the catalogue's range |
| `start_date`, `end_date` | for date mode `dates` (alert streams): `YYYY-MM-DD` |
| `date_expression` | how the wording states the window. `years`: `absolute_year` or `absolute_range`. `dates`: `absolute_date`, `absolute_date_range` or `relative_recent`. `blank`: `none` or `fixed` |
| `canopy_cover` | only for datasets with a canopy default: a legal catalogue value. Blank means the default, which the wording must not mention |
| `forest_filter` | one of the dataset's forest layers. Blank means none: the wording opts out, and the case expects `context_layer: no_selection` |
| `intersections`, `crop_types`, `gas_types`, `land_cover_classes` | only for datasets that take that parameter; carried into case notes, not scored |
| `expected_language` | the wording's language code; `en` if blank |
| `phrasing` | `direct`, `conversational` or `imprecise` |
| `n_cases` | how many wordings the row should have (1 or more) |
| `judge_note` | scoring context: the LLM reads it but must not quote it, and it becomes the case's `notes.judge_instruction` |
| `notes` | anything else the LLM should know about the row |
| `evaluators` | optional `;` list of the checks the case keeps. A row whose list leaves out `date` gets no date expectation (used for two-period comparisons) |

**To add a row**, append it to the right manifest with the next
`manifest_id` in that file, run `validate_manifest.py`, and then follow the
workflow below. The validator lists the new row as "below n_cases target"
until its cases are promoted.

## Workflow

```bash
# 1. Validate the manifests against the catalogue (no API, no LLM).
#    --catalog-dir is the catalogue directory of your project-zeno checkout.
uv run python generation/validate_manifest.py \
  --catalog-dir <project-zeno>/src/agent/datasets/catalog

# 2. See which rows need wordings and the prompt the LLM would get (no LLM).
uv run python generation/generate_cases.py --dataset integrated_alerts --intent trend --dry-run

# 3. Generate the wordings (calls the LLM and spends budget).
uv run python generation/generate_cases.py --dataset integrated_alerts --intent trend

# 4. Review every wording in scratch/candidates/ (see the review gate),
#    then check what would be written, and write it.
uv run python generation/promote_cases.py \
  scratch/candidates/integrated_alerts__trend.candidates.csv --dry-run
uv run python generation/promote_cases.py \
  scratch/candidates/integrated_alerts__trend.candidates.csv

# 5. The store's after-edit steps, then commit their output with the cases.
uv run python tools/check.py --fix --suite challenge
uv run python tools/coverage_doc.py --suite challenge
uv run python tools/check_benchmark.py
```

- **Step 3 needs `ANTHROPIC_API_KEY`**, read from the environment or from
  `.env` at the repo root, and spends API budget. The default model is
  `claude-sonnet-5` (`--model`). `--limit N` processes only N rows.
- Step 2 and step 3 count the wordings that already exist, in the store and
  in a pending candidates file, so a rerun fills only the gaps.
- `promote_cases.py` gives each case the set's next free id
  (`ch-quant-NNN`, `ch-comp-NNN`, `ch-trend-NNN`) and the status `ready`
  (`--status` changes it).
- Step 5 is [After an edit](../cases/challenge/README.md#after-an-edit) in
  the CHALLENGE README. New cases are not members of any BENCHMARK version,
  so `check_benchmark.py` should print `ok` for every manifest.

**Review gate.** Read every wording against `_shared.md` and the intent
file. A wording must state its whole permutation without ambiguity, respect
the defaults (the "do not mention" rules), and differ in a real way from
its siblings. Read every `judge_instruction` too. Cases that fail their
first run are triaged as a bad case or a real defect, but the CHALLENGE
doctrine holds: a case that is expected to fail stays in, and a case is
never changed to make it pass.

## Retired cells

- **DIST-ALERT (id 0)**: `dist_alert.yml` left the project-zeno catalogue
  (commit 31a4d1e), and its three cells were retired with it. Alert coverage
  is on `integrated_alerts` (id 11).
- **LGMS (id 12)**: excluded from the default agent profile, and the
  CHALLENGE canonical series runs prod with the default profile, so it has
  no cell.
