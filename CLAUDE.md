# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The GOLD **capability smoke-test set** for the GNW / Project Zeno agent, as a
versioned repo replacing a live Google Sheet. GOLD answers one question per
release: *did an agent change break a capability that used to work?* It is
not a quality measure — the headline is a **regression count**, never a mean
score, and determinism outranks realism in every design call.

Read `docs/specs/PLAN.md` before proposing changes. The build landed as one PR
per spec (case store → results ledger → harness port → fixes → bucket scoring →
new validators → multiturn). All planning docs — the design plan, PR specs, and
case-set plans — are local-only notes in `docs/specs/`, which is gitignored;
the repo itself carries only `docs/evaluator-map.html`. The parent evidence
base is `gnw-evals/.claude/reports/five-bucket-coverage-plan.md`.

## Commands

```bash
uv sync                                  # install (Python >=3.11, hatchling layout)
uv run pytest                            # full suite
uv run pytest tests/test_canonical.py -q               # one file
uv run pytest tests/test_store.py::test_write_read_round_trip  # one test

# case-store lifecycle
uv run python tools/check.py             # verify uids + manifest (CI gate; nonzero on drift)
uv run python tools/check.py --fix       # REQUIRED after hand-editing any case YAML
uv run python tools/import_sheet.py --csv <export.csv>   # or --url; idempotent; --prune for removals
uv run python tools/export_csv.py --out scratch/gold.csv --status-exclude "not doing"

# coverage doc + dataset catalog snapshot
uv run python tools/coverage_doc.py       # REQUIRED after any case edit, alongside check.py --fix
uv run python tools/sync_zeno_catalog.py  # refresh cases/zeno_catalog.json from project-zeno main
```

**COVERAGE.md must move with the case set.** Any change to a case —
prompt, expected values, status, group, a new or deleted case — is
incomplete until `tools/check.py --fix` *and* `tools/coverage_doc.py` have
run and both results are committed with the edit. The doc carries a
`Last updated` stamp (date-only differences don't trip the gate) and CI
fails the PR via `coverage_doc.py --check` if the content is stale.

## Dataset coverage against project-zeno

COVERAGE.md's "Dataset coverage" section reports the case set against the
**agent's dataset catalog**: `src/agent/datasets/catalog/*.yml` on
`wri/project-zeno` main. Each catalog YAML defines the `dataset_id`/name, any
dataset-specific `parameters` (e.g. `canopy_cover` with its legal values),
`context_layers`, and four per-dataset instruction fields
(`prompt_instructions`, `selection_hints`, `code_instructions`,
`presentation_instructions`).

To get this info next time: the sibling checkout lives at
`../project-zeno`; `tools/sync_zeno_catalog.py` runs `git fetch origin main`
there and reads the files with `git show origin/main:<path>` — the working
tree is never touched (override with `--zeno <path>` / `--ref <ref>`). It
writes the trimmed, committed snapshot `cases/zeno_catalog.json` (source sha
+ sync date recorded), and `coverage_doc.py` renders only from that snapshot
so CI's freshness gate needs no network and no sibling repo. When zeno's
catalog changes: re-run the sync, regenerate COVERAGE.md, and commit both
together. Coverage semantics: a case counts toward every dataset its
`dataset_id` accepts; `answer`/`text`-graded cases are the ones that exercise
a dataset's prompt/code/presentation instructions, while any `dataset_id`
check exercises its `selection_hints`.

Runs execute in-repo (the gnw-evals bridge was retired after the
2026-08-01 parity run; `export_csv.py` remains for triage):

```bash
export API_TOKEN="$STAGING_API_TOKEN"   # .env holds it; the CLI reads API_TOKEN

uv run gold run --env staging --ff experimental --build "<label>"              # iteration (1 trial, 10 workers)
uv run gold run --env staging --ff experimental --trials 3 --build "<label>"   # official / gate
```

**`--ff experimental` is required on any run whose verdict you intend to trust.**
`ff` is the agent's tool profile, passed through in the request payload and
omitted entirely when unset, so the agent runs its **default** toolset. Two
capabilities live behind the experimental profile and are simply *absent* without
it: **dashboards** and **satellite imagery**. Every historical run in
`results/runs/` used `ff=experimental`.

Without the flag, all seven `dashboard` rows plus mt-008 fail `dashboard_created`
on every trial — the agent never calls a dashboard tool at all, and the artifacts
show `dashboard_widgets: null`. That is *indistinguishable from the capability
having been removed* unless you check `ff`, and it cost a full misdiagnosis on
2026-08-03 (see `results/recommendations/20260803T201245Z.md` item 1). With
`--ff experimental` on the same case set and harness, those rows pass immediately.

**The tell is the run_id**: `…_staging_experimental` versus a bare `…_staging`.
`make_run_id` encodes `ff` in the filename, so a run whose name lacks the suffix
was not exercising those capabilities — check this before comparing two runs, and
never diff across a differing `ff`.

**Two tiers, deliberately (set 2026-08-03).** The CLI defaults to
`--trials 1 --workers 10` for fast iteration — answering "did my prompt rewrite
stop the nudge?" in minutes. Those runs are **smoke only**: not committed, not
diffed, never a baseline.

**Anything that produces a regression count stays `--trials 3`.** Measured on
the two 3-trial runs: comparing two trials *of the same run* — same build, same
cases, nothing changed — reports **18–29 spurious regressions**, which is larger
than the **15** real regressions between two genuinely different runs. A
single-trial diff cannot separate a clean release from a broken one, and
`diff_runs.py --fail-on-regression` would fail on nearly every run. A 1-trial run
compared against a 3-trial baseline is worse still, so the two sides of any
comparison must carry the same trial count.

Runs now record `workers` and `trial_timeout`, because the 2026-08-02 run's 19
`ReadTimeout`s arrived as one contiguous block across the final quarter of the
run — a load-shaped signature that cannot be diagnosed without knowing the
concurrency that produced it. Raising workers is the main suspect to watch.

## After every run (do all four, in order)

1. **Render the report**: `uv run python tools/render_html.py
   results/runs/<run_id>.json` → `results/reports/<run_id>.html`
   (the template also accepts a run JSON by drag-and-drop). Refresh the
   cross-run pages too: `render_html.py --all`, `render_inspector.py --all`
   (one file each, run-selector dropdown, deep-linkable via `#<run_id>`)
   and `render_trends.py` (pass-rate ticker; never trends across a
   differing `ff`).
2. **Flakiness + diff**: `uv run python tools/flakiness.py
   results/runs/<run_id>.json --per-case`, and `tools/diff_runs.py
   <previous> <current>` against the last comparable run.
3. **Write `results/recommendations/<run_id>.md`** — the run is not done
   until someone can act on it. Cover: what to file upstream (agent
   behaviour, with the flapping/failing row lists as evidence), what the
   run says about the case set (stale expectations, coverage holes,
   probation re-admissions), what it says about the harness, and a
   next-run watchlist. `results/recommendations/20260801T093002Z.md` is
   the model.
4. **Commit** the ledger JSON, the report, and the recommendation doc
   together; use `--note` on the run whenever check semantics changed
   since the previous one.

## The identity system (load-bearing — do not break)

`src/goldset/canonical.py` defines everything downstream trusts:

- **`uid`** = `sha256(canonical_json(query + non-empty expected values))[:16]`.
  Changing the prompt or any `expected` value mints a new uid — that is the
  versioning mechanism, not an error. `status`, `group`, `notes`, key order,
  whitespace, and CRLF never affect it: triage must not mint versions.
- The hash deliberately covers **all** expected fields, scored or not
  (docs/specs/PLAN.md §2.2 has the rationale — don't "optimise" it to scored-only).
- **`caseset_version`** in per-store `MANIFEST.json` (cases/v1, cases/v2) hashes all sorted uids.
  Results (see `results/README.md`) key on uid + caseset_version; regression
  diffs run over uid intersections between runs.
- `id` (the sheet's `test_id`) is the stable lineage handle across versions.

Consequently: any edit to a case file must be followed by
`tools/check.py --fix` **and** `tools/coverage_doc.py` (COVERAGE.md derives
from the store), and CI-style verification is plain `check.py` plus
`coverage_doc.py --check`.
`tests/test_schema.py` validates every case file against
`schema/case.schema.json`, so a malformed case fails the suite, not a run.

## Architecture

- `src/goldset/` — the library: `canonical.py` (hashing) and `store.py`
  (frozen `Case` dataclass, YAML read/write, manifest). Tools in `tools/`
  are thin CLIs over it, adding `src/` to `sys.path` directly (the package
  is also installed editable via uv).
- `cases/v{1,2}/<group-slug>/<id>.yaml` (v1 = imported baseline, v2 = curated working set; see cases/README.md) — one case per file so PR review/blame/
  revert work per case. `expected:` = hashed expectations, prefix-stripped;
  `notes:` = unhashed annotations. Unknown top-level keys are rejected on
  read. Import routes sheet columns by prefix: `expected_*` → expected,
  everything else → notes.
- `results/` — committed per-run JSON ledger (contract fixed in
  `results/README.md` even though the ingester lands in PR-02). Checks are
  tri-state `1.0/0.0/null`; **no hand-written or backfilled entries, ever**.
- Sheet relationship is **one-way**: import sheet → repo; the repo is the
  source of truth and re-imports are reviewable PRs whose diff is the sheet
  delta. Import is byte-idempotent on an unchanged sheet.

## Working agreements (from docs/specs/PLAN.md §6)

- Numbers in code; structure and semantics to the judge — no LLM judge is
  ever asked to do arithmetic.
- Every check's spec decides whether an absence scores `null` (n/a) or
  `0.0` (failure), and says why.
- Judged checks run info-only until they show std ≤ 0.10 over 3 trials.
- Judge structured outputs put reasoning before the score field.
