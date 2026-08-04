---
name: gold-run
description: Use when running the GOLD eval set or finishing a run — preflight (ff/trials/build), execute the run, then the full after-run ritual (reports, flakiness, diff, recommendations doc, commit).
---

# gold-run — run the set and finish the job

A run is not done when the JSON lands: it is done when someone can act on it.
This skill covers preflight, the run, and CLAUDE.md's four-step after-run
ritual, executed rather than cited.

## 1. Preflight (all of these, every time)

- **Token:** `API_TOKEN` must be set (`.env` holds it; the CLI loads it).
- **Tool profile:** default to `--ff experimental`. Without it, dashboards and
  satellite imagery are *absent* and every dashboard row fails in a way that is
  indistinguishable from the capability being removed (see CLAUDE.md). If the
  user explicitly wants the default profile, say what will fail and why, and
  never compare the result against an experimental run.
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
uv run gold run --env staging --ff experimental --build "<label>"            # smoke
uv run gold run --env staging --ff experimental --trials 3 --build "<label>" # official
```

## 2. During the run

Watch the output for judge errors (rows flagged `JUDGE ERRORS` must be rerun
before being trusted) and for contiguous blocks of timeouts near the end — a
load-shaped signature, not an agent regression.

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
   *Comparable means:* same trial count, same `ff` (check the run_id suffix:
   `…_staging_experimental` vs bare `…_staging`), overlapping caseset. If no
   comparable run exists, say so — do not diff against something else.
3. **Recommendations doc** at `results/recommendations/<run_id>.md`, four
   sections: what to file upstream (agent behaviour, with row lists as
   evidence); what the run says about the case set (stale expectations,
   coverage holes, probation re-admissions); what it says about the harness;
   a next-run watchlist. `results/recommendations/20260801T093002Z.md` is the
   model.
4. **Commit** — but **stop and show the user what will be committed first**
   (run JSON + reports + recommendations in one commit). Never hand-edit a
   run file; a re-ingest after a tooling fix means visibly deleting the file
   in a reviewable commit.

## Guardrails

- Ledger entries are written by the harness only — no backfills, no edits.
- A scoped re-run never gets spliced into an older run file; compose the
  current picture with `tools/compose_runs.py` instead.
- Never trend or diff across a differing `ff`.
