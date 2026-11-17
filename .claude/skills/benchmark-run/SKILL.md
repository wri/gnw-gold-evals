---
name: benchmark-run
description: Use when running a BENCHMARK version or finishing a BENCHMARK run ("run the benchmark", "run draft-5", "rerun the revised members", "make the scorecards page data"). Covers preflight, the run, rollup, page data, the index, the commit and the partial rerun. Not for GOLD runs or for plain CHALLENGE runs.
---

# benchmark-run: run a BENCHMARK version and finish the job

BENCHMARK is a uid manifest in `benchmarks/` over `cases/challenge`. Its
verdict is a rate, never a regression count.
[benchmarks/README.md](../../../benchmarks/README.md) owns the procedures:
this skill follows its "After a run" and "Rerunning revised members only"
steps in the same order. Terms are defined in
[docs/glossary.md](../../../docs/glossary.md).

## 1. Preflight

- **Manifest:** ask which version. List `benchmarks/*.json` and read each
  `status` (`draft`, `frozen`, `retired`). Never run a `retired` version as
  a new trend point. The current versions are in the table in
  `benchmarks/README.md`.
- **Check it:** `uv run python tools/check_benchmark.py`. An error on a
  frozen version stops the run. A warning on a draft means a member's case
  was edited or is no longer `ready`, so the run would leave it out: tell
  the user how many members, and offer to rebuild the draft first (the
  draft-member steps in the **challenge-cases** skill).
- **Canonical settings:** `--env prod`, `--trials 3`, no `--ff`, `--workers`
  left at its default (10). Anything else is a diagnostic run: it is not a
  trend point. `--workers` does not affect the canonical flag.
- **Tokens:** `PROD_API_TOKEN` (not `API_TOKEN`, which is only a fallback)
  and `ANTHROPIC_API_KEY` for the judge. The CLI loads `.env`.
- **Build label:** a real `--build` label. If check semantics changed since
  the last run, add `--note "<what changed>"` so the change is not read as
  agent movement.
- **Checkout:** run in the checkout that will write the page. The raw
  artifacts stay in the checkout that ran the run. For a partial rerun, use
  the checkout that ran the earlier runs.
- **Mac:** run under `caffeinate -i`. An idle sleep stalls a long run.

## 2. Run (After a run, steps 1 and 2)

```bash
caffeinate -i uv run evals run --env prod --trials 3 \
  --benchmark benchmarks/<v>.json --build "<label>"
```

`--benchmark` implies `--suite benchmark`. The run goes to
`results/benchmark/runs/<run_id>.json`. Watch for `[ERROR]` rows. If the
run is killed, finish it with `uv run evals run --resume <run_id>`: with no
other flag the CLI looks in all three ledgers and uses the one match.

## 3. After the run (After a run, steps 3 to 9)

3. **Roll up:**
   ```bash
   uv run python tools/challenge_rollup.py --benchmark benchmarks/<v>.json \
     results/benchmark/runs/<run_id>.json
   ```
4. **Page data:**
   ```bash
   uv run python tools/benchmark_page.py results/benchmark/runs/<run_id>.json
   ```
   Do this now, in this checkout: it reads the run's artifacts in
   `results/benchmark/artifacts/<run_id>/`, which are gitignored.
5. **Stage the run and its page:**
   ```bash
   git add results/benchmark/runs/<run_id>.json results/benchmark/pages/<run_id>.json
   ```
6. **Index:** `uv run python tools/build_run_index.py`. It reads tracked and
   staged files only, so stage first. Read the run's entry in
   `results/index.json` and tell the user whether it says `canonical: true`.
7. **Recommendations doc:** `results/benchmark/recommendations/<run_id>.md`.
   Every committed run has one. Copy the shape of
   `results/benchmark/recommendations/20261023T094447Z_prod.md` (headline,
   by question type, by use case, recommendations, next-run watchlist).
   State whether the run is canonical, and the version and its status.
8. **Commit:**
   ```bash
   git add results/index.json results/benchmark/recommendations/<run_id>.md
   ```
   Then stop and show the user `git status` and `git diff --cached --stat`.
   Commit the run, page, index and doc in one commit only after they agree.
9. **Push** only when the user asks. The page reaches users only when a
   frontend release pins the commit.

## Partial rerun (revised members only)

Follow "Rerunning revised members only" in `benchmarks/README.md`:

1. **The draft must already be rebuilt** with the revised members' new
   uids. If it is not, `--missing-from` says "nothing to run".
2. **List the runs behind the version's latest result:**
   ```bash
   uv run python -c "import json,sys; e=[r for r in json.load(open('results/index.json'))['sets']['benchmark'] if r['benchmark']['version']==sys.argv[1] and 'page' in r][-1]; print(*e.get('composed_with', []), e['run_id'])" <v>
   ```
3. **Dry run** with every listed run as `--missing-from`; it must list
   exactly the revised members:
   ```bash
   uv run evals run --env prod --trials 3 --benchmark benchmarks/<v>.json \
     --missing-from results/benchmark/runs/<run1>.json \
     --missing-from results/benchmark/runs/<runN>.json --dry-run
   ```
4. **Run** the same command without `--dry-run`, with `--build "<label>"`,
   under `caffeinate -i`.
5. **Combined page**, with every listed run as `--base`:
   ```bash
   uv run python tools/benchmark_page.py results/benchmark/runs/<rerun>.json \
     --base results/benchmark/runs/<run1>.json \
     --base results/benchmark/runs/<runN>.json
   ```
   It needs the artifacts of the rerun and of every base, and it prints the
   combined rate: report that number, not the rerun's own rollup. Do not
   rebuild the manifest between the rerun and this step.
6. **Continue at step 5 of section 3.** In the recommendations doc, say that
   the results come from different dates. Prefer a full run before a freeze.

## Guardrails

- The frontend shows a run only after a frontend release pins it in
  `src/features/ai-accuracy-scorecards/model/releases.ts`
  (wri/project-zeno-next) to a commit of this repo. Never rebase, squash or
  force-push a commit that is pinned.
- The frontend parses the page files strictly. A change to the page shape
  (`tools/benchmark_page.py`, `schema/benchmark_page.schema.json`) is a
  cross-repo contract change: it needs a frontend change in the same cycle.
- Never hand-edit or splice a run file. Never edit or void a member to
  improve a rate: an erratum voids a broken member of a frozen version only
  (see **challenge-cases**).
- Do not run `evals prune-artifacts --suite benchmark` while a page you may
  rebuild, or the plain baseline, still needs a run's artifacts.
