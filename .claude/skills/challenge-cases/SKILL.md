---
name: challenge-cases
description: Use when adding, revising or running CHALLENGE cases ("add challenge cases", "generate numeric cases", "promote the candidates", "import the seed CSV", "run CHALLENGE", "roll up the run"). Covers the three ways in, the store lifecycle, the BENCHMARK check, and the canonical CHALLENGE run and rollup. Not for GOLD cases.
---

# challenge-cases: grow and run the CHALLENGE store

CHALLENGE (`cases/challenge/`) measures how well the agent does, as a pass
rate per set and cohort. Many cases are expected to fail. Read
[cases/challenge/README.md](../../../cases/challenge/README.md) first. Terms
are in the [README glossary](../../../README.md#glossary).

## 1. Rules that differ from GOLD

- **GOLD's audit rules do not apply.** Do not run `audit_cases.py --strict`
  here, and do not use GOLD's depth floor or phrasing rules. The doctrine is
  realism: prompts read the way users write them.
- **Never "fix" a case to make it pass.** A failing case stays `ready`: the
  failure is the data. Change a case only when its expectation is wrong, and
  say why.
- Statuses: `ready` runs, `todo` is held, `not doing` is retired. Expected
  ids must be verified against prod before they enter the store
  (`notes.verified`).
- **Uid warning.** Editing a `ready` case's query or any expected value mints a
  new uid. The old uid then drops out of every draft manifest that used it
  (`check_benchmark.py` warns). Tell the user which manifests lose a member.
- **A member of a frozen version is never edited.** Void it with an entry in
  that manifest's `errata` list (`uid`, `date`, `reason`), and add a new case
  if a replacement is needed. See [benchmarks/README.md](../../../benchmarks/README.md).

## 2. Three ways in

- **Generation pipeline** (numeric sets: quantification, trend, comparison).
  Steps are in [generation/README.md](../../../generation/README.md):
  ```bash
  uv run python generation/validate_manifest.py --catalog-dir ../project-zeno/src/agent/datasets/catalog
  uv run python generation/generate_cases.py --dataset <slug> --intent <intent> --dry-run
  uv run python generation/generate_cases.py --dataset <slug> --intent <intent>
  ```
  Then review every wording in `scratch/candidates/` against the cell's
  `_shared.md` and intent file, and promote only the reviewed CSV:
  `uv run python generation/promote_cases.py scratch/candidates/<file>.csv --dry-run`,
  then again without `--dry-run`. Without `--dry-run`, `generate_cases.py`
  spends LLM tokens: say so first.
- **Seed CSV** (hand-authored sets such as `dataset`, in `seeds/`). The CSV
  uses the sheet columns (`test_id`, `status`, `test_group`, `query`,
  `expected_*`; other columns go to notes):
  `uv run python tools/import_sheet.py --csv seeds/<file>.csv --cases-dir cases/challenge --set <set>`.
  Without `--cases-dir` it writes to `cases/v2`. Always pass it.
- **Benchmark sheet rows** (curated BENCHMARK versions).
  `uv run python tools/benchmark_from_sheet.py --seed seeds/<file>.csv --version <v>`
  tags existing cases and writes `benchmarks/<v>.json`. It does not create
  cases, so a new row needs its case first, by one of the two ways above.

## 3. Lifecycle after any edit (in order)

```bash
uv run python tools/check.py --fix --cases-dir cases/challenge
uv run python tools/coverage_doc.py --cases-dir cases/challenge
uv run python tools/check_benchmark.py
```

Stage the case files, `cases/challenge/MANIFEST.json`, `COVERAGE.md`,
`coverage.json` and `cases_index.json` together. CI checks all of them.

## 4. Run and roll up

Canonical series: prod, default profile (no `--ff`), 3 trials. Diagnostic runs
(staging, 1 trial, any `ff`) are never published or committed as the series.

```bash
caffeinate -i uv run evals run --suite challenge --env prod --trials 3 \
  --status-exclude "not doing,todo" --build "<label>"
uv run python tools/challenge_rollup.py results/challenge/runs/<run_id>.json
```

Run one set with `--set <name>`. Read rates against `cases/challenge/TARGETS.yml`.
Then write `results/challenge/recommendations/<run_id>.md` (upstream issues,
case-set notes, harness notes, next-run watchlist; framed as rates, never
regression counts; model: `20260901T131519Z_prod.md`). Then:

```bash
git add results/challenge/runs/<run_id>.json results/challenge/recommendations/<run_id>.md
uv run python tools/build_run_index.py
git add results/index.json
```

Show the user what will be committed, then commit run, recommendations and
index together. For BENCHMARK members use **benchmark-run**.
