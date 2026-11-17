## GOLD (legacy copy)

GOLD asks one question before each release: did an agent change break a capability that used to work? Its headline is a regression count between two runs, and its cases favour determinism over realism. On 2026-10-27 it moved to [wri/project-zeno](https://github.com/wri/project-zeno) under `evals/gold/` (project-zeno PR #874), with its own README, CLAUDE.md, case store (`evals/gold/cases/v2`) and ledger (`evals/gold/results/`). Run, author and gate GOLD there.

The copy here stays until a later PR deletes it, after its case notes are reconciled with project-zeno. Until then:

- CI still checks `cases/v1`, `cases/v2` and `results/gold/` (uids, manifests, COVERAGE.md, the audit and the run index), so an edit to them follows [Changing cases](#changing-cases).
- The authoring rules for `cases/v2`, the two stores and the audit gate are in [cases/GOLD-AUTHORING.md](cases/GOLD-AUTHORING.md).
- The six Claude Code skills under `.claude/skills/` and the manual `staging-run` CI job work on this copy only. The skills use the older `gold` command name. They are not yet ported to project-zeno.
- Its other records: [cases/v2/COVERAGE.md](cases/v2/COVERAGE.md) (generated coverage report), [results/gold/recommendations/](results/gold/recommendations/) (action docs written after official runs) and [results/gold/campaigns/](results/gold/campaigns/) (write-ups of multi-run validation efforts).

The sections below are what someone needs to run or gate this copy before it is deleted. The current versions are in project-zeno's [`evals/gold/README.md`](https://github.com/wri/project-zeno/blob/main/evals/gold/README.md).

### The release gate

Before a release, diff an official run of the candidate build against the baseline: the most recent committed official run that is comparable with it. If there is none, first make one with the build currently released.

```bash
uv run python tools/diff_runs.py results/gold/runs/<baseline>.json results/gold/runs/<candidate>.json \
  --fail-on-regression --fail-on-coverage-loss
```

`--fail-on-regression` exits 1 on any regression in a gating check; `--fail-on-coverage-loss` also fails when a gating check stopped being evaluated. The count only means something if the two runs are comparable: same `ff`, same trial count (3) and same environment. [Comparing two runs](results/README.md#comparing-two-runs) gives the conditions and the evidence behind them; the `release-gate` skill walks through the verdict. Ground-truth flips caused by a data change are reported as [data bumps](#data-bump), not regressions; review any flagged as a possible hidden regression before trusting the count.

### After a run

An official run is not finished when its JSON lands; it is finished when someone can act on it. Smoke runs skip these steps and are never committed. If check semantics changed since the previous run, the run should already carry `--note` (see [Running a suite](#running-the-set)).

1. **Render the reports.**
   ```bash
   uv run python tools/render_html.py results/gold/runs/<run_id>.json   # results/gold/reports/<run_id>.html
   uv run python tools/render_html.py --all        # results/gold/reports/all-runs.html
   uv run python tools/render_inspector.py --all   # results/gold/reports/all-runs_inspector.html
   uv run python tools/render_trends.py            # results/gold/reports/trends.html
   ```
   For a quick read, `uv run python tools/report_run.py results/gold/runs/<run_id>.json` prints a Markdown summary, and `render_inspector.py results/gold/runs/<run_id>.json` builds a matrix of every case against every check for one run. Read the trends page within one `ff` only.
2. **Check flakiness and diff.**
   ```bash
   uv run python tools/flakiness.py results/gold/runs/<run_id>.json --per-case
   uv run python tools/diff_runs.py results/gold/runs/<baseline>.json results/gold/runs/<run_id>.json
   ```
   Diff only against a comparable run ([Comparing two runs](results/README.md#comparing-two-runs)). If none exists, say so in the recommendations doc rather than diffing against something else.
3. **Write `results/gold/recommendations/<run_id>.md`** with four sections:
   - what to report to the agent team, with the failing and flapping rows as evidence;
   - what the run says about the case set (stale expectations, coverage gaps, cases ready to leave probation);
   - what it says about the harness;
   - what to watch on the next run.

   `results/gold/recommendations/20260801T093002Z.md` shows the shape.
4. **Commit** the run JSON, the rendered reports and the recommendations doc together, in one commit. After `git add`-ing the run JSON, regenerate the run index (`uv run python tools/build_run_index.py`; it enumerates tracked and staged files, so add the run first) and commit `results/index.json` in the same commit; CI gates its freshness.

The `gold-run` skill runs these steps, and the `triage-run` skill helps fill in step 3.

### Claude Code skills

The repo commits [Claude Code](https://claude.com/claude-code) skills under `.claude/skills/`, so anyone using Claude Code here gets the same workflows. All six are for the GOLD legacy copy. Invoke one by name (`/gold-run`) or describe the task and the matching skill loads. Each skill follows the procedures in this README and the rules in CLAUDE.md, step by step.

| Skill | Use it when |
|---|---|
| [`gold-run`](.claude/skills/gold-run/SKILL.md) | running the set: preflight (profile, trials, build label), the run, and the after-run steps through to the commit |
| [`case-edit`](.claude/skills/case-edit/SKILL.md) | changing any case: the uid consequences first, then the after-edit steps, with the status rules enforced |
| [`triage-run`](.claude/skills/triage-run/SKILL.md) | analysing a finished run: failures classified as agent, stale expectation, harness or flake, and a filled-in recommendations doc |
| [`new-case`](.claude/skills/new-case/SKILL.md) | writing a new case: an interview about the capability, which expected field switches on which check, and verified answers before `done` |
| [`release-gate`](.claude/skills/release-gate/SKILL.md) | the two-run release verdict: comparability checks, the `diff_runs.py` gate, and reading the count against trial noise |
| [`sync-catalog`](.claude/skills/sync-catalog/SKILL.md) | refreshing the snapshot of project-zeno's dataset catalogue and reading what it changes in coverage |

### Legacy tools

Cases used to live in a Google Sheet, and runs used to go through the gnw-evals harness. Both are retired: the case store is the source of truth, and `evals run` is the only runner. A few tools from that period remain for occasional use: `import_sheet.py` and `export_sheet_csv.py` (move cases between a sheet tab and the store), `export_csv.py` (write cases as a gnw-evals test CSV), `ingest_run.py` (import an old gnw-evals run into the ledger) and `parity.py` (the one-off check that the harness scored the same as gnw-evals). None of them is part of the normal GOLD workflow, though `import_sheet.py` also imported CHALLENGE's seed CSVs ([seeds/README.md](seeds/README.md)). [tools/README.md](tools/README.md#legacy-tools) says what each is still for.
