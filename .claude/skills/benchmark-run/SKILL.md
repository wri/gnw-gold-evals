---
name: benchmark-run
description: Use when running a BENCHMARK version or finishing a BENCHMARK run ("run the benchmark", "run draft-5", "rerun the revised members", "make the scorecards page data"). Covers preflight, the run, rollup, page data, the commit and the partial rerun. Not for GOLD runs or for plain CHALLENGE runs.
---

# benchmark-run: run a BENCHMARK version and finish the job

BENCHMARK is a uid manifest in `benchmarks/` over `cases/challenge`. Its
verdict is a rate, never a regression count. Read
[benchmarks/README.md](../../../benchmarks/README.md) before the first run.
Terms are in the [README glossary](../../../README.md#glossary).

## 1. Preflight

- **Manifest:** ask which version. List `benchmarks/*.json` and read each
  `status` (`draft`, `frozen`, `retired`). Never run a `retired` version as
  a new trend point. The current versions are in the table in
  `benchmarks/README.md`.
- **Check it:** `uv run python tools/check_benchmark.py benchmarks/<v>.json`.
  An error on a frozen version stops the run. A warning on a draft means a
  member lost its uid or its `ready` status: the run will skip it, so tell
  the user how many members that is.
- **Canonical settings:** `--env prod`, `--trials 3`, no `--ff`,
  `--workers 5`. Anything else is a diagnostic run: it is not a trend point.
- **Tokens:** `PROD_API_TOKEN` (not `API_TOKEN`, which is only a fallback)
  and `ANTHROPIC_API_KEY` for the judge. The CLI loads `.env`.
- **Build label:** a real `--build` label. If check semantics changed since
  the last run, add `--note "<what changed>"` so the diff is not read as
  agent movement.
- **Mac:** run under `caffeinate`. An idle sleep stalls a long run.

## 2. Run

```bash
caffeinate -i uv run evals run --suite benchmark --env prod --trials 3 --workers 5 \
  --benchmark benchmarks/<v>.json --build "<label>"
```

The run goes to `results/benchmark/runs/<run_id>.json`. Watch for `[ERROR]`
rows. If the run is killed, finish it with `uv run evals run --suite benchmark
--resume <run_id>`. The results directory must match the original run.

## 3. After the run (all on the machine that ran it)

1. **Rollup:**
   ```bash
   uv run python tools/challenge_rollup.py --benchmark benchmarks/<v>.json results/benchmark/runs/<run_id>.json
   ```
2. **Page data:**
   ```bash
   uv run python tools/benchmark_page.py results/benchmark/runs/<run_id>.json
   ```
   Do this now. It reads the run's agent artifacts in
   `results/benchmark/artifacts/`, which are gitignored, so another machine
   cannot rebuild the page later.
3. **Recommendations doc:** `results/benchmark/recommendations/<run_id>.md`.
   Every committed run has one, so write one. Look at
   `results/benchmark/recommendations/20261023T094447Z_prod.md` for the shape
   (headline, by question type, by use case, recommendations, next-run
   watchlist). State whether the run is canonical, and the version and its
   status.
4. **Stage, then index:**
   ```bash
   git add results/benchmark/runs/<run_id>.json results/benchmark/pages/<run_id>.json results/benchmark/recommendations/<run_id>.md
   uv run python tools/build_run_index.py
   git add results/index.json
   ```
   The index reads tracked and staged files, so add the run first.
5. **Commit:** stop and show the user `git status` and `git diff --cached
   --stat` first. Commit only after they agree.

## Partial rerun (revised members only)

```bash
caffeinate -i uv run evals run --suite benchmark --env prod --trials 3 --workers 5 \
  --benchmark benchmarks/<v>.json --missing-from results/benchmark/runs/<earlier>.json --build "<label>"
uv run python tools/benchmark_page.py results/benchmark/runs/<rerun>.json --base results/benchmark/runs/<earlier>.json
```

`--missing-from` and `--base` both repeat: for a second round, pass every
earlier run to both. The rerun alone is not canonical. The page combines it
with the earlier runs, and the index judges the combination. The results come
from different dates, so say so in the recommendations doc. Prefer a full run
before a freeze. Then do steps 3 and 4 above.

## Guardrails

- The frontend shows a run only after a frontend release pins it in
  `model/releases.ts` to a gold commit. Committing here does not publish it.
- The frontend parses the page files strictly. A change to the page shape
  (`tools/benchmark_page.py`) is a cross-repo contract change: it needs a
  frontend change in the same cycle.
- Never hand-edit or splice a run file. Never void or edit a member to
  improve a rate: voiding is an erratum (see **challenge-cases**).
