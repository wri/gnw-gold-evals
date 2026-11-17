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

153 prompts across 12 cohorts (`cases/challenge/aoi/<cohort>/`), every
prompt isolated in scope so
only `pick_aoi` executes. Run it alone with `--set aoi` (the run CLI's
exact-match filter on `case.set`). Seed and per-case lineage:
`seeds/challenge-aoi-v1.csv`; PZB tickets and specs in `notes.lineage`.
Expectations verified against prod `/api/aois` on 2026-09-01 (121 rows), or
structural GADM id ranges (5 expansion rows).
The `designations` cohort (22 rows, added 2026-09-15, lineage PZB-1392) names
protected areas and indigenous lands with an English designation where the
WDPA or Landmark row stores a French, Spanish or Portuguese one, plus two
designation-in-leaf controls; its ids were verified against prod `/api/aois`
on 2026-09-15.

Known scoring gaps accepted for batch 1 (candidates for future evaluators):

- `aoi_ids` is all-of exact set match. Until 2026-10-24 there was no any-of,
  so cases with more than one defensible answer either expect a nudge or pin
  the most defensible id, with the alternative recorded in `notes.lineage`.
  `|` now separates alternative sets (`555697863|10906`; see
  `src/goldset/evaluators/README.md`, `aoi_id_match`), and `/` lists one
  area's equivalent records within a set (`555697863/10906;2017`); batch 1
  rows keep their pinned ids.
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

## Batch 3: the `dataset` set

200 dataset-selection prompts (`cases/challenge/dataset/<cohort>/`, ids
`ch-dataset-001..200`; named `map` until 2026-09-29, ids `ch-map-NNN`), each
phrased as asking only to see a layer on the map, with no place, no quantity and no
date, so the one tool that should run is `pick_dataset` (the FE draws the
tile layer from `state.dataset`; there is no separate add-to-map tool).
Built to compare project-zeno's RAG + LLM selector with the jev decision
model (project-zeno PR #841). Seed and per-row lineage:
`seeds/challenge-dataset-v1.csv`; expectations from the zeno catalog at
e2fb83f (`selection_hints`, `context_layers`, `parameters`).

| cohort | n | scored |
|---|---|---|
| 10 dataset cohorts (land-cover, grasslands, natural-lands, tcl, tc-gain, ghg-flux, tree-cover, tcl-drivers, tcl-fires, integrated-alerts; ids 1-8, 10, 11) | 13 each (easy/medium/hard 4/5/4) | `dataset_id` (five rows add an explicit non-default `dataset_parameters` canopy) |
| multilingual (es, pt, fr, id, sw) | 25 | `dataset_id` (two rows add `context_layer`) |
| context-layer | 15 | `dataset_id` + `context_layer` (primary/intact asks, and `no_selection` opt-outs) |
| ambiguous | 15 | 11 pinned `select` rows with `;` alternatives, 4 pinned `nudge` rows (`dataset_choice` + options) |
| unmappable (sLUC, climate and other out-of-catalog asks) | 15 | `dataset_id: no_selection` (sLUC `9;no_selection`) + `text` |

Every row also sets `forbidden_tools` (pull_data, generate_insights,
create_dashboard, add_to_dashboard, add_map_widget, search_blogs,
search_insights, show_imagery), which gates `forbidden_tools_absent`: the
set's scope-isolation assertion. The list is hashed; changing it re-mints
all 200 uids. `pick_aoi` is deliberately **not** forbidden (decided
2026-09-25): the set tests the dataset picker only, and picking a layer
then asking "where?" via `pick_aoi` (seen on 3 of 31 smoke trials) is
acceptable behaviour, not a scope leak.

Scoring decisions and gaps:

- Plain dataset cohorts do **not** score `context_layer`. With no AOI the
  selector sees every layer unfiltered, and the TCL and fires primary-forest
  descriptions say to default to that layer for general forest loss, so a
  primary pick on "show tree cover loss" is policy, not error. Only the
  context-layer cohort scores it.
- The ambiguous cohort cannot say "select X **or** nudge": each row pins one
  behaviour (`notes.behaviour`), with the alternative in `notes.lineage`.
- **The four nudge rows are structurally unwinnable for jev v1**: jev
  returns one choice plus a confidence, and `none` goes down the no-match
  path with no suggestions, so it never emits a `dataset_choice` nudge.
  They stay in: the ambiguous cohort failing under jev is a finding. Read
  them separately when comparing selectors.
- Unmappable rows pass on "no dataset selected + honest text"; a nudge is
  neither required nor penalised.
- `text` is the only judged check (15 rows, one Haiku call each per trial).
- Dates are deliberately unscored (the set is date-free).

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

## Batch 4: the benchmark v2026 cases (`monitoring`, `causal`, AOI-level)

63 cases from the proposed BENCHMARK v2026 set
(`seeds/benchmark-v2026-proposed.csv`, rows marked NEW), written from
GFW/LCL user stories rather than observed traffic, so every one is tagged
`notes.synthetic: TRUE`. Expectations were **drafted, not reviewed**
(`notes.expectations`); AOI ids were resolved against prod `/api/aois` on
2026-10-01. Review them before the November freeze.

| set | n | what it adds |
|---|---|---|
| `monitoring` (new) | 30 | near-real-time integrated alerts (dataset 11) for parks, Indigenous territories, states and districts; rolling windows use run-relative date tokens (`{run-30d}`, `{last_month_start}`, `{current_year}-01-01`) with `date_tolerance_days`; 4 non-English; 3 scope rows (no area given, email subscription, coordinate buffer) judged by `text` |
| `causal` (new) | 18 | driver and fire attribution; judged `text` checks for not over-claiming a commodity, checking the question's premise, and the selective-logging caveat |
| quantification / comparison / trend | 15 | the same analyses at protected-area, Indigenous-territory and sub-national level (every earlier analytic row is country-level) |

- Questions that name no dates carry no expected window: the window is
  the agent's call, and an expected one would fail correct answers.
- `ch-mon-028` (triage across a user's saved areas) is `todo`: it needs a
  seeded test account.
- Protected-area (WDPA) analytics fail upstream while PZB-1406 is open;
  those rows count as failures, as any user would see them.

## Batch 5: the v2026 BEF sheet (`portfolio` set, plus monitoring, numeric and causal rows)

168 cases from the BEF benchmark sheet of 2026-10-22
(`seeds/benchmark-v2026-bef-2026-10-22.csv`, 299 rows): the rows that no
existing case answers. The sheet's other 131 rows reuse existing cases (98
real-traffic cases by `challenge_id`, 33 earlier synthetic cases by query
text). Every new case is synthetic and its expectations are **drafted, not
reviewed** (`notes.expectations`); AOI ids were resolved against prod
`/api/aois` on 2026-10-23, with doubtful or unpinned ones explained in
`notes.verified`. Review them before the November freeze.

| set | new | what it adds |
|---|---|---|
| `portfolio` (new) | 27 | many areas at once (ranking every state, screening uploaded sites, saved-area triage), judged by `text`; drafted as redirects to one to three named areas, revised 2026-10-24 to the real limits (below); `notes.reclassify_when` says when the fixture rows flip to "answer with data" |
| `monitoring` | 36 | alert follow-up (imagery, clusters, coordinates, prioritising), alert context (natural lands, primary forest, mangroves, park buffers), alert method questions, unsupported actions and fixture rows |
| `quantification` / `comparison` / `trend` | 93 | subnational, protected-area and Indigenous-territory analyses, two-to-three-area comparisons, and data or method questions (`method` cohort, `text` only), unavailable data (`unavailable`) and many-area redirects (`many-areas`) |
| `causal` | 11 | alert causes, driver shares, commodity over-claims and premise checks |
| `aoi` | 1 | an ambiguous Amazon question |

- **Fixture rows are `todo`.** 29 new rows (plus `ch-mon-028`) need a seeded
  test account with a custom area or a 25-polygon portfolio; their
  `status_reason` names the fixture, and BENCHMARK `2026-draft-3` lists them
  as excluded (AJ, 2026-10-23).
- **Unconfirmed capabilities run now.** Rows the sheet marks "Confirm with
  engineering" (imagery, alert clusters, coordinate export, VIIRS, concession
  and buffer analysis, production forests) carry an either/or `text`
  expectation that accepts a correct answer or an honest "not available";
  `notes.capability_check` marks them for engineering to confirm (AJ,
  2026-10-23). Concession areas (logging, mining, oil palm) are in the AOI
  index, so the Lomié and mining-overlay rows may deserve a firmer
  expectation once confirmed.
- **Open-ended windows end in 2025.** Tree cover loss, fires, drivers and
  flux run to 2025 (catalog `content_date`), so "since 2021" expects
  2021-01-01 to 2025-12-31 where the sheet wrote 2024-12-31; each case says
  so in `notes.build_notes`. Questions that name no window carry none, as in
  Batch 4.
- Each member's sheet facets (use cases, engagement, AOI type, capability,
  grounding) are case notes written by `tools/benchmark_from_sheet.py`.

### Expectation review after the first draft-3 run (2026-10-24)

The first `2026-draft-3` run (`20261023T094447Z_prod`; recommendations in
`results/benchmark/recommendations/`) showed some drafted expectations were
wrong. AJ's decisions, applied to 44 cases (26 run, 18 fixture rows); each
case's `notes.review` gives its evidence:

- **Many areas: the real limits.** `pick_aoi` takes up to 1,000 admin
  sub-units of one GADM parent, but only 50 protected areas, KBAs,
  Indigenous lands or concessions (project-zeno
  `src/agent/subagents/pick_aoi/tool.py`). Rows within the limit now expect
  an answer with data (every municipality of Pará, every department of
  Bolivia, African countries, Brazilian states, districts of two countries);
  the rest keep a redirect worded to the real limit, never "one to three
  named areas". The sheet's `capability` facet still says "Not yet" for the
  reclassified rows; fix it in the sheet before the next curation.
- **Either/or rows** whose decline branch selects no dataset carry no
  dataset or date checks.
- **Defensible alternatives:** emissions from loss accept tree cover loss
  (`6;4`), land cover accepts natural lands (`1;3`), and four AOIs use the
  `|` any-of syntax (Salonga, Kakataibo, Mahakam Delta).
- **Confirmed capability:** alerts on natural lands (`ch-mon-058`) now expect
  data with `context_layer: natural_lands`.
- **Method questions:** three judged texts were relaxed where careful
  answers failed on an optional detail (`ch-quant-194`, `-197`, `-205`), and
  `ch-quant-184`'s premise was fixed. Printable maps (`ch-mon-047`) stay
  strict: a dashboard is not a printable map.
- **After the first rerun** (`20261024T133644Z_prod`), two texts were
  reworded again: `ch-quant-194` drops its optional "may point to" clause,
  which the judge read as required, and `ch-port-011` accepts either an
  honest "cannot select these sites as a group" or a ranking cited from
  published research.

### Clarifying dataset choices (2026-10-26)

Reviewing the draft-4 failures, AJ decided that asking which dataset to use
is a right answer when the choice offered is the right one. Sixteen members
asked back on every attempt. Fourteen of them now carry
`accept_nudge_offering` (their `dataset_id` set): an attempt that ends in a
`dataset_choice` nudge offering every listed dataset passes, extra options
allowed, and a correct pull still passes. The check and the attempt-majority
verdict are documented in `src/goldset/evaluators/README.md`
(`accepted_nudge_match`). The other two are not dataset choices and are
unchanged: `ch-aoi-090` asks which Pará and `ch-mon-027` never nudges.
Replayed on their 23 and 24 Oct attempts, 9 of the 14 would pass; the 5 that
still fail never offered SBTN Natural Lands (`ch-comp-154`, `-157`,
`ch-quant-175`, `-180`) or offered only the sLUC emission factors
(`ch-comp-155`). The members' new uids are unmeasured until rerun.

AJ then reviewed the 18 members that pulled on some attempts and asked on
others, and opted in three more: `ch-causal-025` (`4;8`) and `ch-causal-015`
(`8;10`) accept a dataset choice, and `ch-quant-188` accepts an area choice
through `accept_aoi_nudge_offering` (`BRA.14`): asking which Pará is meant is
fine as long as Pará, Brazil is offered. Replayed, `ch-causal-025` would pass
(it failed) and the other two still pass. The other 15 keep their
expectations: their failures are agent fixes or correct as they stand.

### "Why" questions answered from blogs (2026-10-26)

Nineteen members answered from `search_blogs` instead of the data. A search of
the corpus the tool reads (WRI and Land & Carbon Lab Insights; the list is in
the GNW workspace, `experiments/2026-10-26-search-blogs-corpus/`) found posts
that fairly answer three of them. AJ decided those three may pass on a blog
answer and the rest must be answered from data, then kept four as they
were:

- `ch-causal-002` (Bolivia 2024), `ch-causal-003` (Brazil 2016) and
  `ch-causal-022` (Riau) carry `accept_blog_sources`, the slugs of the posts
  that answer them; an answer from `search_blogs` that links one passes, and
  `web_fallback` ignores those posts on a pull (`accepted_blog_match` in
  `src/goldset/evaluators/README.md`).
- Ten of the other 16 already required a pull. Two now do: `ch-trend-081`
  (pull flag added) and `ch-quant-173` (Brazil, sLUC and a pull). AJ kept
  `ch-causal-029`, `ch-quant-166`, `ch-aoi-155` and `ch-quant-190` as they
  were (text expectations only); a data requirement was drafted for each and
  dropped in review.

### Ghana questions moved to Côte d'Ivoire (2026-10-26)

The analytics API rejects every Ghana sub-national GADM id: GADM 4.1 writes
them without the dot (`GHA15_2`), and the fix is PZB-1408, planned for the
next sprint. Until then AJ moved the eight Ghana members to similar areas in
Côte d'Ivoire, Ghana's cocoa-belt neighbour: Western region to Cavally
(`ch-causal-001`), Western North to Nawa (`ch-comp-149`, `ch-mon-011`),
Western North and Ashanti to Nawa and Haut-Sassandra (`ch-comp-150`), the
Offinso districts to Cavally, Guémon and Tonkpi (`ch-comp-163`) and to
San-Pédro (`ch-mon-041`, `ch-mon-045`), and the Ghana Cocoa Belt to Côte
d'Ivoire's cocoa belt (`ch-causal-026`). Each case keeps its Ghana version
in `notes.ghana_original`. The benchmark sheet matches these rows by query
text, so `seeds/benchmark-v2026-bef-2026-10-26.csv` is the 22 October export
with those eight queries substituted, and `2026-draft-4` is built from it.
Restore the Ghana versions, and the 22 October seed, once PZB-1408 is fixed.

### Draft-5 review: could this answer mislead the user? (2026-10-27)

Before the draft-5 run, every draft-4 member was reviewed against one question
from AJ: could this answer mislead the user? Each case is scored only on the one
to three things that could mislead for it; a check that fails an answer that
would mislead no one was eased, and a misleading answer that passed got the
lightest check that catches it. The per-question findings and decisions are in
the review doc ("BENCHMARK draft-4 critical review", claude.ai artifact
68PEmch8CvCEJwgB2xtmTy). Applied to 213 case files:

- **Figures from the agent's own pull.** About 170 members gained a `figure`
  formula (and some a `figure_claim`), checked by `figure_match` and
  `figure_claim_match` against the table the agent itself pulled; data quality
  is out of scope. Column names and values were confirmed against real pulled
  tables. See `src/goldset/evaluators/README.md`.
- **Periods.** `date_extraction` passes a pull that contains the asked window;
  `answer_period_match` checks the answer uses exactly the asked period.
- **Fair alternatives.** New `/` records per area in `aoi_ids`, `|` alternatives
  in `context_layer` and in the nudge accept fields, plus the expectations the
  review proposed (datasets that can answer the question, defensible area
  records, sharper `text` that writes the fact in, tone and format clauses
  dropped).
- **Ghana.** `ch-quant-180` (Ashanti to Haut-Sassandra) and `ch-port-017`
  (Côte d'Ivoire only) moved like the eight 2026-10-26 Ghana questions;
  `notes.ghana_original` keeps the old wording.
- **Not applied, for AJ:** `ch-quant-164` and `ch-aoi-090` (would reverse his
  calls), `forbidden_tools` on the dataset questions (set-level), the
  `ch-causal-010` caveat direction and the `ch-aoi-116` branch. Prose
  ask-backs are not yet accepted (no harness support).

Each edited case records the change in `notes.review` and stamps
`notes.expectations` with "draft-5 review 2026-10-27".
