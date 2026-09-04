# CHALLENGE case set

The quality and accuracy measure for the GNW / Project Zeno agent. Where GOLD
(`cases/v2`) answers "did an agent change break a capability that used to
work?" with a regression count, CHALLENGE answers "how well does the system
perform on prompts like X?" with a **pass rate per cohort**. Plan of record:
`PRDs/challenge-set.md` in the GNW workspace.

## Doctrine (deliberately inverted from GOLD where noted)

- **Realism over determinism.** Prompts are phrased the way users phrase
  them. GOLD's depth floor and phrasing rules (`audit_cases.py --strict`)
  do not apply to this store.
- **Failure is data, not a defect.** Cases that do not pass stay `ready` and
  keep running; that is the point. There is no "verified passing" status
  ladder here. Statuses: `ready` (runs), `todo` (authored but held, e.g.
  expectation not yet pinned), `not doing` (retired).
- **The store is hierarchical: set → cohort → case.** Each case carries
  `set:` (the level new CHALLENGE sets are added at — `aoi` today; a future
  `dataset`, `custom-areas`, ... sits beside it) and `group:` (its cohort
  within the set); files live at `cases/challenge/<set>/<cohort>/<id>.yaml`.
  Like `group`, `set` is organisational and never hashed into the uid.
- **The headline is a rate, never a regression count.** Verdicts come from
  `tools/challenge_rollup.py`: pass rates overall, per set, and per
  cohort/difficulty within each set, with Wilson 95% confidence intervals,
  against `TARGETS.yml`.
- **Every case still has a defined correct behaviour**, including the ones
  expected to fail today. `notes.behaviour` records it: `select` (right
  AOI(s) chosen), `nudge` (asks with the right options), `clarify` /
  `decline` (asks or explains, never substitutes a wrong area). "Hard" means
  the system currently fails, not that there is no right answer.
- **No unverified expectations.** Every expected id is verified against the
  target environment before it enters the store (`notes.verified` records
  how and when). `todo` rows hold unpinnable expectations until a smoke run
  or DB query pins them.
- **Identity discipline is unchanged from GOLD**: uid content hash,
  caseset_version, immutable run ledger, tri-state checks, majority verdicts.
  After any case edit: `tools/check.py --fix --cases-dir cases/challenge`
  and `tools/coverage_doc.py --cases-dir cases/challenge`, committed with
  the edit.

## Running

Canonical published series: **prod, default profile, 3 trials**. Anything
else (staging, `--ff experimental`, 1 trial) is diagnostic: never published,
never mixed into the canonical trend, never compared across differing
env/ff/trials/caseset_version.

```bash
# canonical (published rates)
uv run gold run --cases-dir cases/challenge --results-dir results/challenge \
  --env prod --trials 3 --status-exclude "not doing,todo" --build "<label>"

# diagnostic smoke (never committed, never published)
uv run gold run --cases-dir cases/challenge --results-dir results/challenge \
  --env staging --status-exclude "not doing,todo" --build "<label>"

# rollup (step 1 of the after-run ritual)
uv run python tools/challenge_rollup.py results/challenge/runs/<run_id>.json
```

The run ledger lives in `results/challenge/` so CHALLENGE runs never enter
GOLD's trend pages, diffs, or CI baseline logic. The ledger contract
(`results/README.md`) applies unchanged: immutable run files, no backfills,
1-trial runs are smoke only.

## After every run (mirrors GOLD's ritual, adapted to rates)

1. **Rollup**: `tools/challenge_rollup.py` as above; read rates against
   `TARGETS.yml`.
2. **Write `results/challenge/recommendations/<run_id>.md`** — the run is
   not done until someone can act on it. Cover: what to file upstream
   (agent behaviour, with failing rows and trace URLs as evidence), what
   the run says about the case set (expectation reviews, scoring gaps,
   todo pinning — remember failures are data, never fix a case to make it
   pass), what it says about the harness, and a next-run watchlist. Frame
   everything as rates vs targets, never regression counts.
   `results/challenge/recommendations/20260901T131519Z_prod.md` is the
   model.
3. **Commit** the run JSON, artifacts, and the recommendations doc
   together. Only canonical runs (prod, default, 3 trials) enter the
   published series; a diagnostic run's recommendations doc must say so in
   its header and treat its rates as directional. After `git add`-ing the
   run JSON, regenerate `results/index.json`
   (`uv run python tools/build_run_index.py`) and commit it in the same
   commit; CI gates its freshness.

## Targets (the OKR loop)

`TARGETS.yml` mirrors the store hierarchy: a challenge-wide `overall`, then
per-set blocks (`sets.<set>.overall` and `sets.<set>.targets.<cohort>`).
Each cycle: add or extend a
cohort whose prompts do not yet pass, set its target, and commit the baseline
rollup showing the sub-target rate; that commit is the commitment. At cycle
end, one canonical run plus rollup answers "the system now handles N% of
prompts of this type".

## Batch 1: the `aoi` set

131 prompts across 11 cohorts (`cases/challenge/aoi/<cohort>/`), every
prompt isolated in scope so
only `pick_aoi` executes. Run it alone with `--set aoi` (the run CLI's
exact-match filter on `case.set`). Seed and per-case lineage:
`seeds/challenge-aoi-v1.csv`; PZB tickets and specs in `notes.lineage`.
Expectations verified against prod `/api/aois` on 2026-09-01 (121 rows), or
structural GADM id ranges (5 expansion rows).

Known scoring gaps accepted for batch 1 (candidates for future evaluators):

- `aoi_ids` is all-of exact set match; there is no any-of. Cases with more
  than one defensible answer either expect a nudge or pin the most defensible
  id, with the alternative recorded in `notes.lineage`.
- No `aoi_absent` check: "must not substitute a wrong area" is approximated
  with `clarification` and `text` judges.
- The scope classifier has no class for "resolved an AOI and stopped", so
  cases omit `scope`.

Deferred (see the PRD): a custom-areas set (needs seeded areas under the
run token's user), multi-turn AOI refinement, coordinate support.

## Batch 2: the numeric sets (quantification, trend, comparison)

Ported from gnw-evals `eval-metrics-slice-1` (the eval-metrics programme's
Phase 2 numeric expansion; rationale in its `PHASE2_HANDOFF.md` and the
workspace PRDs). Set = intent, cohort = dataset (short names in
`generation/dataset_config.py`): quantification and comparison cells for
the 11 default-profile catalog datasets, trend for the time-series five.
The 90 slice-1 TCL cases came over with reviewed wordings; the other cells'
wordings were generated per the held Phase 2 manifests. Authoring machinery
and workflow: `generation/README.md`.

Scoring is **retrieval-first**: dataset/AOI/date checks, explicit
(non-default) canopy as `dataset_parameters`, forest-filter behaviour as
`context_layer` (explicit opt-outs score `no_selection`, which is the
primary-forest-substitution detector), and `data_pull` on every row.
Ground-truth numeric fidelity — the slice-1 `data_fidelity`/`number_usage`
machinery — is deliberately NOT ported: it was TCL-hardwired, and
generalising it is the Phase 2 W1/W2 evaluator work. Until then the
Explanation bucket rides in `notes.judge_instruction`, unscored, and no
case stores an expected number (ground truth must be computed at run time
so it survives data-version bumps).

Known coverage informed by live bugs: primary-forest substitution
(`no_selection` rows), the canopy-default quirk (explicit-canopy rows),
date-scoping flakiness (the biggest slice-1 retrieval drag; every dated
row scores `date_extraction`), and alert routing after DIST-ALERT's
removal (all alert cells expect integrated alerts, id 11).

### Pinning the todo rows

`ch-aoi-095/098/099/101` (expansion id lists) and `ch-aoi-108` (Lahti,
unreachable via name search): run each once with
`--id <id> --status-exclude "not doing"`, read the selected ids from the run
artifact (`results/challenge/artifacts/<run_id>/<uid>.json.gz`), verify them,
move the expectation into the case, and flip the status to `ready`.
