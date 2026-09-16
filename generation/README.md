# Numeric-case generation (CHALLENGE)

Ported from gnw-evals `eval-metrics-slice-1` (the eval-metrics programme's
Phase 2 numeric expansion); the CHALLENGE store is now the home of these
cases. The pipeline is synthetic-first: cases are generated from the dataset
catalog + intent taxonomy, never from stored answers — **the LLM only ever
writes prompt wordings; every expected value is constructed mechanically**
from the manifest row and `dataset_config.py`, so a generated case cannot
smuggle in a wrong expectation.

Hierarchy: CHALLENGE **set = intent** (`quantification`, `trend`,
`comparison`), **cohort = dataset** (short names in `dataset_config.py`).
Scoring is retrieval-first (dataset/aoi/dates/explicit parameters +
`data_pull`); ground-truth numeric fidelity is deliberately not ported —
that is the Phase 2 W1/W2 evaluator work (see the workspace PRD
`eval-phase-2-numeric-expansion.md`).

## The pieces

| Piece | What it is |
|---|---|
| `manifests/<slug>__<intent>.manifest.csv` | Permutation manifest per dataset×intent cell — the prompt-coverage denominator. One row per permutation a well-tested cell must span. |
| `<slug>/_shared.md` + `<slug>/<intent>.md` | Wording rules per cell, derived from the catalog `prompt_instructions`/cautions. |
| `dataset_config.py` | Per-dataset config: intents, date mode, canopy default, forest layers, CHALLENGE cohort name. |
| `validate_manifest.py` | Validates every manifest against the catalog YAMLs and reports prompt coverage from the store. |
| `generate_cases.py` | Asks an LLM for missing wordings per manifest row → `scratch/candidates/*.candidates.csv` (gitignored). |
| `promote_cases.py` | Reviewed CSV rows → YAML cases in `cases/challenge/<intent>/<cohort>/`. |

## Workflow

```bash
# 1. validate manifests against the live catalog (no API, no LLM)
uv run python generation/validate_manifest.py \
  --catalog-dir ../project-zeno/src/agent/datasets/catalog

# 2. generate wordings for one cell (spends LLM tokens; --dry-run first)
uv run python generation/generate_cases.py --dataset integrated_alerts --intent trend

# 3. review every wording in scratch/candidates/ against the cell's
#    instruction files (and 100% of judge_instructions), then promote:
uv run python generation/promote_cases.py \
  scratch/candidates/integrated_alerts__trend.candidates.csv

# 4. the store lifecycle, always:
uv run python tools/check.py --fix --cases-dir cases/challenge
uv run python tools/coverage_doc.py --cases-dir cases/challenge
```

Review gate (inherited from the programme): read every wording against
`_shared.md` + the intent file — a wording must encode its whole permutation
unambiguously, respect defaults ("do not mention" rules), and differ
meaningfully from its siblings. Cases that fail their first run get triaged
(bad case vs real defect) before the set is treated as versioned — but
remember the CHALLENGE doctrine: expected-to-fail cases stay in.

## Retirements

- **DIST-ALERT (id 0)**: `dist_alert.yml` left the catalog (zeno@31a4d1e);
  its three cells were retired with it, alert coverage lives on
  `integrated_alerts` (id 11).
- **LGMS (id 12)**: excluded from the default agent profile, and the
  CHALLENGE canonical series is prod + default — no cell.
