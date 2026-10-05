---
name: gold-run
description: Use when running the GOLD eval set or finishing a run — preflight (ff/trials/build), execute the run, then the full after-run ritual (reports, flakiness, diff, recommendations doc, commit).
---

# gold-run — run the set and finish the job

A run is not done when the JSON lands: it is done when someone can act on it.
This skill covers preflight, the run, and the four-step after-run ritual
([README, After a run](../../../README.md#after-a-run)), executed rather than
cited. Terms are defined in the [README glossary](../../../README.md#glossary).

## 1. Preflight (all of these, every time)

- **Token:** set the token for the target environment: `STAGING_API_TOKEN`
  for `--env staging`, `PROD_API_TOKEN` for `--env prod`, plus
  `ANTHROPIC_API_KEY` for the judge (the CLI loads `.env`). `API_TOKEN` is
  only a fallback (and the one `--env local` reads), so make sure it does not
  hold another environment's token. See [README, Setup](../../../README.md#setup).
- **Tool profile:** run the default profile (no `--ff`). Add
  `--ff experimental` only when the run is about something still behind that
  profile, and then diff it only against other `experimental` runs. Check the
  `ff` of the baseline you will diff against before you start. The rule, and
  what each profile holds: [README, Running the set](../../../README.md#running-the-set).
- **Tier — decide out loud:**
  - *Smoke* (`--trials 1`, the default): minutes-fast iteration. Never
    committed, never diffed, never a baseline.
  - *Official* (`--trials 3`): anything that produces a regression count or
    becomes a baseline. Both sides of any comparison must have the same tier.
- **Build label:** require a meaningful `--build` (agent build string or a
  purpose label like `post-fix-validation`). "unknown" is not acceptable on an
  official run.
- **Methodology note:** if check semantics changed since the previous run,
  pass `--note` so the diff isn't read as agent movement.
- **Workers/timeout:** keep defaults unless investigating load; a change is
  worth calling out (runs record `workers` and `trial_timeout` because a
  timeout block once mimicked a capability loss).

```bash
uv run gold run --env staging --build "<label>"              # smoke
uv run gold run --env staging --trials 3 --build "<label>"   # official
```

## 2. During the run

Watch the progress lines for `[ERROR]` rows and the closing line ("N with
ERRORS (rerun before trusting)"). An error row (a crash, a timeout or a judge
error) is unmeasured, not failed: rerun it before trusting it. A contiguous
block of timeouts near the end is a load signature, not an agent regression.
If the run is killed, finish it with `uv run gold run --resume <run_id>`.

## 3. After the run (official tier; smoke stops here)

Run all four, in order:

1. **Reports:**
   ```bash
   uv run python tools/render_html.py results/runs/<run_id>.json
   uv run python tools/render_html.py --all
   uv run python tools/render_inspector.py --all
   uv run python tools/render_trends.py
   ```
2. **Flakiness + diff:**
   ```bash
   uv run python tools/flakiness.py results/runs/<run_id>.json --per-case
   uv run python tools/diff_runs.py results/runs/<prev>.json results/runs/<run_id>.json
   ```
   Diff only against a comparable run: same `ff` (check the run_id suffix,
   `…_prod_experimental` versus `…_prod`), same trial count, same
   environment. The full definition is in
   [results/README.md, Comparing two runs](../../../results/README.md#comparing-two-runs).
   If no comparable run exists, say so; do not diff against something else.
3. **Recommendations doc** at `results/recommendations/<run_id>.md`: use the
   **triage-run** skill, which classifies the failures and fills the four
   sections listed in [README, After a run](../../../README.md#after-a-run).
4. **Commit** — but **stop and show the user what will be committed first**
   (run JSON + reports + recommendations in one commit). Never hand-edit a
   run file; a re-ingest after a tooling fix means visibly deleting the file
   in a reviewable commit.

## Guardrails

- Ledger entries are written by the harness only — no backfills, no edits.
- A scoped re-run never gets spliced into an older run file; compose the
  current picture with `tools/compose_runs.py` instead.
- Never trend or diff across a differing `ff`.
