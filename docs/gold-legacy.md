# GOLD legacy copy

GOLD is the capability regression suite. It asks one question before each release: did an agent change break a capability that used to work? Its headline is a regression count between two runs, and its cases favour determinism over realism.

GOLD moved to [wri/project-zeno](https://github.com/wri/project-zeno) under `evals/gold/` on 2026-10-27, with its own README, CLAUDE.md, case store and ledger. Run, author and gate GOLD there: its [`evals/gold/README.md`](https://github.com/wri/project-zeno/blob/main/evals/gold/README.md) is the current version of everything below.

The copy in this repo stays until a later pull request deletes it. That waits until its case notes are reconciled with project-zeno. This page is what someone needs to run or gate the copy until then. Terms marked *(GOLD)* in the [glossary](glossary.md) apply here only.

## What is still here

| Item | Where |
|---|---|
| The working case set and the frozen import of the retired Google Sheet | `cases/v2/`, `cases/v1/` |
| How to write a GOLD case, the two stores, the audit gate | [cases/GOLD-AUTHORING.md](../cases/GOLD-AUTHORING.md) |
| The ledger, reports, recommendations docs and campaign write-ups | `results/gold/` |
| Four skills that work on this copy only | `gold-run`, `new-case`, `release-gate`, `triage-run` in `.claude/skills/` |
| A manual release-gate job | `staging-run` in `.github/workflows/ci.yml` |

CI still checks `cases/v1`, `cases/v2` and `results/gold/`. An edit to a GOLD case therefore follows the GOLD note in [cases/README.md, After an edit](../cases/README.md#after-an-edit). The skills use the older command name, `gold run`, which is the same command as `evals run`.

## Running GOLD here

```bash
uv run evals run --suite gold --env staging --trials 3 --build "<label>"
```

The tiers, profile and comparability rules are in [README, Running a suite](../README.md#running-a-suite). Two things apply to GOLD only:

- GOLD cases that need the `experimental` profile are parked (`not doing`) while canonical runs use the default profile. Each one's `status_reason` says when to bring it back.
- Every GOLD run before 2026-08-31 used `ff=experimental`, because dashboards and satellite imagery were only on that profile until then. Do not compare those runs with later default-profile runs.

GOLD's canonical runs are 3-trial, default-profile runs on the environment of their baseline, usually staging. project-zeno's GOLD docs call them official runs.

## Regression diffs

`tools/diff_runs.py <older> <newer>` compares two runs check by check, on every case both runs scored. It reports:

- regressions (pass to fail) and recoveries (fail to pass), counted per check, not per case;
- coverage changes: a check that started or stopped being evaluated;
- data bumps (below).

The count means something only when the two runs are comparable: same `ff`, same trial count of 3, same environment. Check this before you diff, and before you trust a count someone else produced.

The `caseset_version` may differ. The diff covers only the uids present in both runs, so added, removed or edited cases show up as "only in A" or "only in B", never as regressions. Report the number of shared cases with the result, because a small overlap makes a weak verdict. `--strict` refuses any pair whose `caseset_version` differs.

**Info-only checks never gate.** They appear in the diff, but `--fail-on-regression` and `--fail-on-coverage-loss` ignore them, including multi-turn ones under a `t<N>.` prefix. The headline splits regressions and lost checks into gating and info-only counts. The flags read `gating_regressions` and `gating_coverage_lost` in the JSON report.

**Methodology notes.** If the newer run carries a `methodology_note`, movement on the checks it names comes from a harness change, not from the agent.

<a id="data-bumps"></a>
### Data bumps

A ground-truth case is graded against values fetched when the run starts, so a data release can flip it with no agent change. When a ground-truth check flips and the case's `digest` moved, the diff lists it as a data bump. Its cause is one of:

- `data`: the same request returned different numbers;
- `request`: the harness built a different request, so a harness change;
- `fixed_dataset`: a dataset declared never to change has changed.

Bumps are never counted as regressions or recoveries, and never gate. A `ground_truth_match` bump whose agent figure matches neither run's values, or that has no figure, is flagged `possible_hidden_regression`. Review it before you trust the regression count: a break that lands in the same run as a data change would otherwise never be counted.

## The release gate

Before a release, diff a canonical run of the candidate build against the baseline. The baseline is the newest committed canonical run that is comparable with it. If there is none, first make one with the build currently released.

```bash
uv run python tools/diff_runs.py results/gold/runs/<baseline>.json results/gold/runs/<candidate>.json \
  --fail-on-regression --fail-on-coverage-loss
```

`--fail-on-regression` exits 1 on any regression in a gating check. `--fail-on-coverage-loss` also fails when a gating check stopped being evaluated. Review every data bump flagged as a possible hidden regression before you trust the count. The `release-gate` skill walks through the verdict.

**Picking a baseline.** `tools/find_baseline.py <new run>` prints the newest run in `results/gold/runs/` that matches the new run on environment, `ff`, trial count and case store (`caseset`). It exits non-zero with the reason when none does. The CI release gate uses it. Runs from before 2026-08-04 record no `caseset`, so they never match.

## After a GOLD run

A canonical run is finished when someone can act on it. Smoke runs skip these steps and are never committed.

1. **Render the reports.**
   ```bash
   uv run python tools/render_html.py results/gold/runs/<run_id>.json   # results/gold/reports/<run_id>.html
   uv run python tools/render_html.py --all --suite gold        # results/gold/reports/all-runs.html
   uv run python tools/render_inspector.py --all --suite gold   # results/gold/reports/all-runs_inspector.html
   uv run python tools/render_trends.py --suite gold            # results/gold/reports/trends.html
   ```
   For a quick read, `uv run python tools/report_run.py results/gold/runs/<run_id>.json` prints a Markdown summary. Read the trends page within one `ff` only.
2. **Check flakiness and diff.**
   ```bash
   uv run python tools/flakiness.py results/gold/runs/<run_id>.json --per-case
   uv run python tools/diff_runs.py results/gold/runs/<baseline>.json results/gold/runs/<run_id>.json
   ```
   If no comparable run exists, say so in the recommendations doc rather than diff against something else.
3. **Write `results/gold/recommendations/<run_id>.md`** with four sections: what to report to the agent team, with the failing and flapping rows as evidence; what the run says about the case set; what it says about the harness; what to watch on the next run. `results/gold/recommendations/20260801T093002Z.md` shows the shape.
4. **Commit** the run, the reports and the recommendations doc in one commit. Stage the run first, then regenerate `results/index.json` with `uv run python tools/build_run_index.py` and commit it in the same commit.

The `gold-run` skill runs these steps, and the `triage-run` skill helps with step 3.

## Legacy tools

Cases used to live in a Google Sheet, and runs used to go through the gnw-evals harness. Both are retired. [tools/README.md, GOLD legacy copy tools](../tools/README.md#gold-legacy-copy-tools) lists the tools from that period and what each is still for.

## Ledger reset of 2026-08-04

Runs scored against intermediate v2 curation states of 2026-08-02 and 2026-08-03 were deleted, with their reports, so the v2 record starts at the first canonical v2 run. They remain in git history. The v1 runs of 2026-07-31 and 2026-08-01, and the recommendations and campaign docs of that period, were kept.
