# CHALLENGE case set

The quality and accuracy measure for the GNW / Project Zeno agent.
CHALLENGE answers "how well does the system perform on prompts like X?"
with a **pass rate per cohort**. GOLD, the capability regression suite, is
its counterpart: it answers "did an agent change break a capability that
used to work?" with a regression count. GOLD now lives in project-zeno
`evals/gold/`; `cases/v2` is a legacy copy. BENCHMARK versions
(`benchmarks/`) are frozen subsets of this store.

How each set was built, and every dated review of its cases, is in
[CHANGELOG.md](CHANGELOG.md). Terms are defined in
[docs/glossary.md](../../docs/glossary.md). The plan of record is
`PRDs/challenge-set.md` in the GNW workspace, a separate repository that is
not public.

## Doctrine (deliberately inverted from GOLD where noted)

- **Realism over determinism.** Prompts are phrased the way users phrase
  them. GOLD's depth floor and phrasing rules (`audit_cases.py --strict`)
  do not apply to this store.
- **Failure is data, not a defect.** Cases that do not pass stay `ready` and
  keep running; that is the point. **Never fix a case to make it pass.**
  Change a case only when its expectation is wrong, and say why. There is no
  "verified passing" status ladder here. Statuses: `ready` (runs), `todo`
  (written but held, for example until an expectation is pinned or a test
  account exists), `not doing` (retired).
- **The store is hierarchical: set, then cohort, then case.** Each case
  carries `set:` (the sets are listed under [Sets](#sets)) and `group:` (its
  cohort within the set). Files live at
  `cases/challenge/<set>/<cohort>/<id>.yaml`. Like `group`, `set` is
  organisational and never hashed into the uid.
- **The headline is a rate, never a regression count.** Verdicts come from
  `tools/challenge_rollup.py`: pass rates overall, per set, and per cohort
  and difficulty within each set, with Wilson 95% confidence intervals,
  against `TARGETS.yml`. A case passes when most of its scored attempts were
  right. This rule dates from 2026-10-28, so rates in earlier reports are
  not comparable point for point.
- **Every case still has a defined correct behaviour**, including the ones
  expected to fail today. `notes.behaviour` records it: `select` (the right
  areas chosen), `nudge` (asks with the right options), `clarify` or
  `decline` (asks or explains, never substitutes a wrong area). "Hard"
  means the system fails today, not that there is no right answer.
- **No unverified expectations.** Every expected id is verified against the
  target environment before it enters the store, and `notes.verified`
  records how and when. A `todo` case holds an expectation that cannot be
  pinned yet.
- **Identity discipline is the same as GOLD's**: uid content hash,
  `caseset_version`, immutable run ledger, tri-state checks, majority
  verdicts. After any case edit, follow [After an edit](#after-an-edit).

## Running

The canonical series, and the only one published, is **prod, default
profile, 3 trials**. Any other run (staging, `--ff experimental`, 1 trial,
a local stack) is a diagnostic run: never published, never mixed into the
canonical trend, never compared across a different environment, profile,
trial count or `caseset_version`.

```bash
# canonical run (published rates)
caffeinate -i uv run evals run --suite challenge --env prod --trials 3 --build "<label>"

# diagnostic run: staging, 1 trial
uv run evals run --suite challenge --env staging --build "<label>"

# one set only
uv run evals run --suite challenge --set aoi --env staging --build "<label>"
```

- `--suite challenge` skips `todo` and `not doing` cases by default
  (`--status-exclude` overrides it).
- `--set` is an exact match on the case's `set`. `--id <id>` runs one
  case; repeat the flag for more.
- `--dry-run` lists the selected cases without calling the API.
- Runs go to `results/challenge/`, so they never enter GOLD's or
  BENCHMARK's trends and diffs. The ledger contract is in
  [results/README.md](../../results/README.md).

**The committed runs.** All six runs in `results/challenge/runs/` are
diagnostic runs. Four are prod, 1-trial runs of 2026-09-01: one of the `aoi`
set and one each of the trend, quantification and comparison cases. Two are
local, 3-trial runs of 2026-09-25 that compared two dataset pickers on the
`dataset` set. No canonical (prod, 3-trial) CHALLENGE run exists yet.

## After every run

Do these in order. They are the only CHALLENGE after-run steps; other docs
point here.

1. **Run it** ([Running](#running)). On a Mac, run under `caffeinate -i`:
   an idle sleep stalls a long run. If the run is killed, finish it with
   `uv run evals run --resume <run_id>`.
2. **Roll it up** and read the rates against `TARGETS.yml`:
   ```bash
   uv run python tools/challenge_rollup.py results/challenge/runs/<run_id>.json
   ```
3. **Write `results/challenge/recommendations/<run_id>.md`**: the run is
   not done until someone can act on it. Cover what to file upstream (agent
   behaviour, with failing rows and trace URLs as evidence), what the run
   says about the case set (expectation reviews, scoring gaps, `todo` rows to
   pin; never fix a case to make it pass), what it says about the harness,
   and what to watch on the next run. Frame everything as rates against
   targets, never regression counts. A diagnostic run's doc says so in its
   header and treats its rates as directional.
   `results/challenge/recommendations/20260901T131519Z_prod.md` shows the
   sections; it is itself a 1-trial diagnostic run of the `aoi` set, which
   its header says.
4. **Stage the run and the doc**:
   ```bash
   git add results/challenge/runs/<run_id>.json results/challenge/recommendations/<run_id>.md
   ```
5. **Regenerate the index**: `uv run python tools/build_run_index.py`. It
   lists tracked and staged files only, so stage first. CI fails on a stale
   index.
6. **Commit** the run, the doc and `results/index.json` in one commit. The
   raw artifacts in `results/challenge/artifacts/<run_id>/` are gitignored
   and stay in this checkout; the rollup output is not committed.

## Targets

Targets work as a loop of objectives and key results. `TARGETS.yml`
mirrors the store hierarchy: a challenge-wide `overall`, then per-set
blocks (`sets.<set>.overall` and `sets.<set>.targets.<cohort>`). Each cycle, add or extend a cohort whose prompts do not yet pass, set its
target, and commit the baseline rollup showing the rate below target: that
commit is the commitment. At the end of the cycle, one canonical run and its
rollup answer "the system now handles N% of prompts of this type".

## Sets

| Set | What it asks | Cohorts | How its cases were made | History |
|---|---|---|---|---|
| `aoi` | Find the place the user means; only `pick_aoi` should run | prompt classes (`acronyms`, `ambiguity`, `designations`, ...) | imported from `seeds/challenge-aoi-v1.csv`; the `designations` cohort written by hand from session traces | [Batch 1](CHANGELOG.md#batch-1-the-aoi-set) |
| `dataset` | Pick the right layer ("show X on the map"); only `pick_dataset` should run | ten datasets, plus `multilingual`, `context-layer`, `ambiguous`, `unmappable` | imported from `seeds/challenge-dataset-v1.csv` | [Batch 3](CHANGELOG.md#batch-3-the-dataset-set) |
| `quantification`, `comparison`, `trend` | How much; places or periods compared; change over time | datasets, plus `method`, `many-areas` and others | the `generation/` pipeline; area-level and method rows written by hand from benchmark sheet rows | [Batch 2](CHANGELOG.md#batch-2-the-numeric-sets-quantification-trend-comparison), [4](CHANGELOG.md#batch-4-the-benchmark-v2026-cases-monitoring-causal-aoi-level), [5](CHANGELOG.md#batch-5-the-v2026-benchmark-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |
| `monitoring` | Recent alerts in an area, and follow-up questions on them | question shapes (`recent-area`, `alert-followup`, ...) | written by hand from benchmark sheet rows | [Batch 4](CHANGELOG.md#batch-4-the-benchmark-v2026-cases-monitoring-causal-aoi-level), [5](CHANGELOG.md#batch-5-the-v2026-benchmark-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |
| `causal` | Why it happened: drivers, fires, premise checks | question shapes (`why-country`, `premise-check`, ...) | written by hand from benchmark sheet rows | [Batch 4](CHANGELOG.md#batch-4-the-benchmark-v2026-cases-monitoring-causal-aoi-level), [5](CHANGELOG.md#batch-5-the-v2026-benchmark-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |
| `portfolio` | Many areas at once | `many-areas`, `saved-areas`, `uploaded-sites` | written by hand from benchmark sheet rows | [Batch 5](CHANGELOG.md#batch-5-the-v2026-benchmark-sheet-portfolio-set-plus-monitoring-numeric-and-causal-rows) |

Case counts per set and cohort are in [COVERAGE.md](COVERAGE.md). Known
scoring gaps for each set are recorded with its batch in the changelog.

## How cases get here

Cases have come into the store in three ways. Once a case is in the store,
its YAML file is the source of truth: no input below is read again, and
later edits are made to the case file.

| | Seed CSV import | Generation pipeline | Written by hand |
|---|---|---|---|
| Use it for | a new set written as a sheet, imported once; never import an existing seed again ([seeds/README.md](../../seeds/README.md)) | new numeric cases (quantification, comparison, trend) from the dataset catalogue | any other case |
| Steps | `tools/import_sheet.py --csv <seed> --cases-dir cases/challenge --set <set>` | [generation/README.md](../../generation/README.md) | [Writing a case by hand](#writing-a-case-by-hand) |
| Sets made this way | `aoi`, `dataset` | `quantification`, `comparison`, `trend` | `monitoring`, `causal`, `portfolio`, the `aoi` `designations` cohort, area-level numeric rows |
| Record on the case | `notes.source_tab` names the CSV | `notes.manifest_id` and `notes.lineage` name the manifest row | `notes.lineage`, plus `notes.expectations` or `notes.origin` saying who drafted it from what |

A curated BENCHMARK version is built from cases already in the store:
`tools/benchmark_from_sheet.py` matches each sheet row to a case and stops
on a row that no case answers, so write the case first
([benchmarks/README.md](../../benchmarks/README.md)).

### Writing a case by hand

1. **Pick the set and cohort, and start from a copy** of an existing case in
   the same cohort directory. The directory is
   `cases/challenge/<set>/<cohort>/`, where `<cohort>` is the case's `group`
   in lower case with `_` and spaces turned into `-` (group `recent_area`
   lives in `recent-area/`). A file anywhere else is not moved: `check.py
   --fix` writes a second copy at the right path, and the next check fails
   on a duplicate id.
2. **Choose the id**: the set's prefix and the next free number, in three
   digits. Find the highest number in use, of any status, and add 1. Never
   reuse a number.
   ```bash
   ls cases/challenge/monitoring/*/ | grep -o 'ch-mon-[0-9]*' | sort | tail -1
   ```

   | Set | Prefix |
   |---|---|
   | `aoi` | `ch-aoi` |
   | `dataset` | `ch-dataset` |
   | `quantification` | `ch-quant` |
   | `comparison` | `ch-comp` |
   | `trend` | `ch-trend` |
   | `monitoring` | `ch-mon` |
   | `causal` | `ch-causal` |
   | `portfolio` | `ch-port` |

3. **Fill in the fields.** The tools require `id`, `status`, `set`,
   `group`, `query` and `expected`. Every value is a string, so quote
   numbers and flags (`dataset_id: '11'`, `data_pull: 'TRUE'`). **Leave
   `uid` out**: `check.py --fix` writes it. Which expected field switches on
   which check is in `src/goldset/evaluators/README.md`; field syntax (what
   `;`, `|` and `/` mean) is in [cases/README.md](../README.md). A `todo`
   case also needs `notes.status_reason`.
4. **Add the notes this store requires**: `behaviour` (the correct
   behaviour), `verified` (how and when each expected id was checked) and
   `lineage` (where the prompt came from). Add `difficulty` (`easy`,
   `medium` or `hard`): rollups group by it, and a case without it is
   "unlabelled". The schema is `schema/case.schema.json`.
5. **Run [After an edit](#after-an-edit).**
6. **Check that it runs**:
   `uv run evals run --suite challenge --env staging --id <id> --dry-run`
   lists it with its uid. Then a diagnostic run without `--dry-run` and with
   `--verbose` shows how it scores.

## After an edit

After any change to a case file, run these and commit their output with the
edit. CI runs all three (without `--fix`).

```bash
uv run python tools/check.py --fix --suite challenge      # uids and MANIFEST.json
uv run python tools/coverage_doc.py --suite challenge     # COVERAGE.md, coverage.json, cases_index.json
uv run python tools/check_benchmark.py                    # BENCHMARK members still match their cases
```

Editing the query or an expected value of a case gives it a new uid. If the
case is a member of a BENCHMARK version, `check_benchmark.py` reports it:

- **Frozen version**: an error. Never edit a frozen version's members: undo
  the edit, or void the member with an erratum and add a new case
  ([benchmarks/README.md](../../benchmarks/README.md)).
- **Draft version**: a warning. The tool exits 0, but CI fails until the
  draft is rebuilt. Continue with the steps below.
- **Retired version**: nothing to do.

For a member of a draft (the live draft is curated from a seed CSV):

4. **Rebuild the draft** from the seed its manifest names in
   `sampling.seed_file`:
   ```bash
   uv run python tools/benchmark_from_sheet.py \
     --seed seeds/benchmark-v2026-bef-2026-10-27.csv --version 2026-draft-5
   ```
   If you changed a query, the tool stops with "query differs from the
   sheet's" (the row names its case by `challenge_id`) or "no CHALLENGE
   case has this query" (the row is matched by its text). Then copy the seed
   to a new dated file, `seeds/benchmark-v2026-sheet-<YYYY-MM-DD>.csv`, put
   the new query in that row, and rebuild with `--seed` set to the new file.
   Never edit or rename the old seed ([seeds/README.md](../../seeds/README.md)).
   The rebuild also rewrites each member's sheet notes in its case file:
   read `git diff` for changes you did not expect.
5. **Check it**: `uv run python tools/check_benchmark.py` must print `ok`
   for every manifest, with no warning.
6. **Regenerate the index**: `uv run python tools/build_run_index.py`. The
   rebuilt manifest changes the `canonical` flags of earlier runs, and CI
   fails on a stale index.
7. **Check the plain baseline's overlay.** If
   `benchmarks/overlays/2026-draft-5.plain.json` has an entry for the old
   uid, every `tools/plain_baseline.py` step that reads it stops with "uids
   are not draft-5 members". Move the entry to the new uid and have the repo
   owner review the call, which was made for the old wording. See
   [results/plain/README.md](../../results/plain/README.md).
8. **Commit** the case edit, the store files, the manifest, any new seed and
   `results/index.json` together.
9. **Rerun the revised members**: [benchmarks/README.md, Rerunning revised
   members only](../../benchmarks/README.md#rerunning-revised-members-only).
