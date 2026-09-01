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
- **The headline is a rate, never a regression count.** Verdicts come from
  `tools/challenge_rollup.py`: pass rate per group and per difficulty with
  Wilson 95% confidence intervals, against `TARGETS.yml`.
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

# rollup (the after-run ritual)
uv run python tools/challenge_rollup.py results/challenge/runs/<run_id>.json
```

The run ledger lives in `results/challenge/` so CHALLENGE runs never enter
GOLD's trend pages, diffs, or CI baseline logic. The ledger contract
(`results/README.md`) applies unchanged: immutable run files, no backfills,
1-trial runs are smoke only.

## Targets (the OKR loop)

`TARGETS.yml` maps cohort to target pass rate. Each cycle: add or extend a
cohort whose prompts do not yet pass, set its target, and commit the baseline
rollup showing the sub-target rate; that commit is the commitment. At cycle
end, one canonical run plus rollup answers "the system now handles N% of
prompts of this type".

## Batch 1: the AOI picker set

131 prompts across 11 cohorts (`aoi-*`), every prompt isolated in scope so
only `pick_aoi` executes. Seed and per-case lineage:
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

Deferred (see the PRD): custom-areas cohort (needs seeded areas under the
run token's user), multi-turn AOI refinement, coordinate support.

### Pinning the todo rows

`ch-aoi-095/098/099/101` (expansion id lists) and `ch-aoi-108` (Lahti,
unreachable via name search): run each once with
`--id <id> --status-exclude "not doing"`, read the selected ids from the run
artifact (`results/challenge/artifacts/<run_id>/<uid>.json.gz`), verify them,
move the expectation into the case, and flip the status to `ready`.
