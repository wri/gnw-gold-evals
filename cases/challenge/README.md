# CHALLENGE case set

The quality and accuracy measure for the GNW / Project Zeno agent.
CHALLENGE answers "how well does the system perform on prompts like X?"
with a **pass rate per cohort**. It is the counterpart of GOLD, the
capability regression suite (now in project-zeno `evals/gold/`; a legacy
copy is in `cases/v2`), which answers "did an agent change break a
capability that used to work?" with a regression count. BENCHMARK versions
(`benchmarks/`) are frozen subsets of this store. Plan of record:
`PRDs/challenge-set.md` in the GNW workspace. How each set was built, and
every dated review of its cases, is in [CHANGELOG.md](CHANGELOG.md).

## Doctrine (deliberately inverted from GOLD where noted)

- **Realism over determinism.** Prompts are phrased the way users phrase
  them. GOLD's depth floor and phrasing rules (`audit_cases.py --strict`)
  do not apply to this store.
- **Failure is data, not a defect.** Cases that do not pass stay `ready` and
  keep running; that is the point. There is no "verified passing" status
  ladder here. Statuses: `ready` (runs), `todo` (authored but held, e.g.
  expectation not yet pinned), `not doing` (retired).
- **The store is hierarchical: set → cohort → case.** Each case carries
  `set:` (the level new CHALLENGE sets are added at; the sets are listed
  under [Sets](#sets)) and `group:` (its cohort within the set); files live
  at `cases/challenge/<set>/<cohort>/<id>.yaml`. Like `group`, `set` is
  organisational and never hashed into the uid.
- **The headline is a rate, never a regression count.** Verdicts come from
  `tools/challenge_rollup.py`: pass rates overall, per set, and per
  cohort/difficulty within each set, with Wilson 95% confidence intervals,
  against `TARGETS.yml`. A case passes when most of its attempts were right
  (AJ, 2026-10-28; before, when each check passed on most attempts), so
  rates in reports written before then are not comparable point for point.
- **Every case still has a defined correct behaviour**, including the ones
  expected to fail today. `notes.behaviour` records it: `select` (right
  AOI(s) chosen), `nudge` (asks with the right options), `clarify` /
  `decline` (asks or explains, never substitutes a wrong area). "Hard" means
  the system currently fails, not that there is no right answer.
- **No unverified expectations.** Every expected id is verified against the
  target environment before it enters the store (`notes.verified` records
  how and when). `todo` rows hold unpinnable expectations until a smoke run
  or DB query pins them.
- **Identity discipline is the same as GOLD's**: uid content hash,
  caseset_version, immutable run ledger, tri-state checks, majority verdicts.
  After any case edit, run the commands in [After an edit](#after-an-edit)
  and commit their output with the edit.

## Running

Canonical published series: **prod, default profile, 3 trials**. Anything
else (staging, `--ff experimental`, 1 trial) is diagnostic: never published,
never mixed into the canonical trend, never compared across differing
env/ff/trials/caseset_version.

```bash
# canonical (published rates)
uv run evals run --suite challenge --env prod --trials 3 \
  --status-exclude "not doing,todo" --build "<label>"

# diagnostic smoke (never committed, never published)
uv run evals run --suite challenge --env staging \
  --status-exclude "not doing,todo" --build "<label>"

# one set only
uv run evals run --suite challenge --set aoi --env staging \
  --status-exclude "not doing,todo" --build "<label>"

# rollup (step 1 of the after-run steps)
uv run python tools/challenge_rollup.py results/challenge/runs/<run_id>.json
```

`--set` is an exact match on the case's `set`. The run ledger lives in
`results/challenge/` so CHALLENGE runs never enter GOLD's trend pages,
diffs, or CI baseline logic. The ledger contract
(`results/README.md`) applies unchanged: immutable run files, no backfills,
1-trial runs are smoke only.

## After every run

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
3. **Commit** the run JSON and the recommendations doc together (the
   run's artifacts are gitignored and stay local). Only canonical runs (prod, default, 3 trials) enter the
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

## Sets

| Set | What it asks | Cohorts | How its cases were made | History |
|---|---|---|---|---|
| `aoi` | Find the place the user means; only `pick_aoi` should run | prompt classes (`acronyms`, `ambiguity`, `designations`, ...) | 131 imported from `seeds/challenge-aoi-v1.csv`; the 22 `designations` cases written directly as case files (from session traces, `notes.origin`); one drafted from the BEF sheet | [Batch 1](CHANGELOG.md#batch-1-the-aoi-set) |
| `dataset` | Pick the right layer ("show X on the map"); only `pick_dataset` should run | ten datasets, plus `multilingual`, `context-layer`, `ambiguous`, `unmappable` | imported from `seeds/challenge-dataset-v1.csv` | [Batch 3](CHANGELOG.md#batch-3-the-dataset-set) |
| `quantification`, `comparison`, `trend` | How much; places or periods compared; change over time | datasets, plus `method`, `many-areas` and others from the sheets | generated by the `generation/` pipeline (the 90 slice-1 tree cover loss cases were ported through `promote_cases.py`); area-level and other rows drafted from benchmark sheet rows | [Batch 2](CHANGELOG.md#batch-2-the-numeric-sets-quantification-trend-comparison), [4](CHANGELOG.md#batch-4-the-benchmark-v2026-cases-monitoring-causal-aoi-level), [5](CHANGELOG.md#batch-5-the-v2026-bef-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |
| `monitoring` | Recent alerts in an area, and follow-up questions on them | question shapes (`recent-area`, `alert-followup`, ...) | drafted from benchmark sheet rows | [Batch 4](CHANGELOG.md#batch-4-the-benchmark-v2026-cases-monitoring-causal-aoi-level), [5](CHANGELOG.md#batch-5-the-v2026-bef-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |
| `causal` | Why it happened: drivers, fires, premise checks | question shapes (`why-country`, `premise-check`, ...) | drafted from benchmark sheet rows | [Batch 4](CHANGELOG.md#batch-4-the-benchmark-v2026-cases-monitoring-causal-aoi-level), [5](CHANGELOG.md#batch-5-the-v2026-bef-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |
| `portfolio` | Many areas at once | `many-areas`, `saved-areas`, `uploaded-sites` | drafted from the BEF sheet rows | [Batch 5](CHANGELOG.md#batch-5-the-v2026-bef-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |

Case counts per set and cohort are in [COVERAGE.md](COVERAGE.md). Known
scoring gaps for each set are recorded with its batch in the changelog.

## How cases get here

Three paths have brought cases into the store. Once a case lands, its YAML
file is the source of truth: none of the inputs below is read again, and
later edits are made to the case files.

| | Seed CSV | Generation pipeline | Benchmark sheet rows |
|---|---|---|---|
| Input | `seeds/challenge-aoi-v1.csv`, `seeds/challenge-dataset-v1.csv`: one row per case, sheet columns (`test_id`, `status`, `test_group`, `query`, `expected_*`, note columns) | `generation/manifests/<dataset>__<intent>.manifest.csv`, plus the wording rules in `generation/<dataset>/` | `seeds/benchmark-v2026-proposed.csv`, `seeds/benchmark-v2026-bef-2026-10-22.csv`: one row per BENCHMARK question |
| Steps | `tools/import_sheet.py --csv <seed> --cases-dir cases/challenge`, with `--set <set>` to add the set level | `generation/generate_cases.py` writes wordings to `scratch/candidates/*.candidates.csv` (gitignored); a person reviews every wording; `generation/promote_cases.py` writes the cases | a row that names an existing case (by `challenge_id` or exact query) needs no new case. For the other rows the case was drafted from the row in a Claude Code session and committed (63 on 2026-10-01, 168 on 2026-10-23); no committed tool writes them. Then `tools/benchmark_from_sheet.py` tags the members and writes the manifest |
| Sets | `aoi`, `dataset` | `quantification`, `comparison`, `trend` | `monitoring`, `causal`, `portfolio`, and area-level rows in the numeric sets |
| Record on the case | `notes.source_tab` names the CSV | `notes.lineage` names the manifest | `notes.expectations` says who drafted it from which CSV |
| Details | [seeds/README.md](../../seeds/README.md) | [generation/README.md](../../generation/README.md) | [seeds/README.md](../../seeds/README.md), [benchmarks/README.md](../../benchmarks/README.md) |

The seed CSV path is established from the cases and git history: every case
from those CSVs carries `notes.source_tab` with the CSV's name, which is
what `tools/import_sheet.py --csv` writes, and the import commit of the
`dataset` set (2026-09-25) names `--set map`, the set's name before it was
renamed `dataset` on 2026-09-29. `tools/import_sheet.py` is listed with the
[legacy tools](../../tools/README.md#legacy-tools) and writes to `cases/v2`
unless you pass `--cases-dir`. `tools/benchmark_from_sheet.py` stops on a
sheet row that no case answers, so write the new cases first.

## After an edit

After any change to a case file, run these and commit their output with
the edit:

```bash
uv run python tools/check.py --fix --suite challenge      # uids and MANIFEST.json
uv run python tools/coverage_doc.py --suite challenge     # COVERAGE.md, coverage.json, cases_index.json
uv run python tools/check_benchmark.py                    # BENCHMARK members still match their cases
```

`check_benchmark.py` comes last because editing the query or an expected
value of a `ready` case that a draft BENCHMARK version lists gives the case
a new uid, so the draft no longer runs it; the tool warns. On a frozen
version it fails: never edit a frozen version's members (see
[benchmarks/README.md](../../benchmarks/README.md)). CI runs all three
(without `--fix`).

## Pinning the todo rows

`ch-aoi-095/098/099/101` (expansion id lists) and `ch-aoi-108` (Lahti,
unreachable via name search): run each once with
`--id <id> --status-exclude "not doing"`, read the selected ids from the run
artifact (`results/challenge/artifacts/<run_id>/<uid>.json.gz`), verify them,
move the expectation into the case, and flip the status to `ready`.

## Comparing two builds locally

Used for the `dataset` set's jev and RAG comparison (2026-09-25; [CHANGELOG.md](CHANGELOG.md#batch-3-the-dataset-set)).

Comparison protocol: prod, default profile, 3 trials is the published
reference series. The jev verdict is read from a **local-main vs local-jev**
pair (same commit, same stack, same trials, same `--workers`), never prod
vs local.

Latency is half of that verdict, so:

- The rollup reports median, p90 and mean per set and cohort from
  `stream_s` (POST /api/chat to the last stream line: the agent turn; no
  state GET, no judge time). Older runs only carry `latency_s`, which also
  spans the state GET; the rollup says which basis it used.
- Run both local sides with `--workers 1` (the CLI's concurrency knob,
  recorded on the run as `workers`): concurrent turns contend for one local
  API and inflate each other's latency.
- Compare with `tools/challenge_rollup.py <local-main>.json <local-jev>.json`:
  the cross-run latency table gives both runs side by side with median
  deltas and flags any env, workers or basis mismatch.
- **Prod latency is reference only.** It includes internet round-trips and
  prod infrastructure (autoscaling, other users' load), so a prod vs local
  gap says nothing about the selector.
