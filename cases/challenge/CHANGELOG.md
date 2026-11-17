# CHALLENGE changelog

How each CHALLENGE set was built, and every dated change to its cases.
The doctrine and the procedures are in [README.md](README.md).

Abbreviations used here: PZB-NNNN is a ticket in the project-zeno Jira
project. GFW is Global Forest Watch and LCL is Land & Carbon Lab, whose user
stories several sets were written from. TCL is tree cover loss.

## Batch 1: the `aoi` set

153 prompts across 12 cohorts (`cases/challenge/aoi/<cohort>/`), each
isolated in scope so that only `pick_aoi` runs. Run it alone with
`--set aoi`. Seed and per-case lineage: `seeds/challenge-aoi-v1.csv`; the
Jira tickets and specs behind each case are in `notes.lineage`.
Expectations were verified against prod `/api/aois` on 2026-09-01 (121
rows), or against structural GADM id ranges (5 expansion rows).
The `designations` cohort (22 rows, added 2026-09-15, PZB-1392) names
protected areas and indigenous lands with an English designation where the
WDPA or Landmark row stores a French, Spanish or Portuguese one, plus two
controls with the designation in the name. Its ids were verified against
prod `/api/aois` on 2026-09-15. These cases were written by hand from
session traces (`notes.origin`).

Known scoring gaps accepted for batch 1 (candidates for future evaluators):

- `aoi_ids` is an all-of exact set match. Until 2026-10-24 there was no
  any-of, so cases with more than one defensible answer either expect a
  nudge or pin the most defensible id, with the alternative recorded in
  `notes.lineage`. `|` now separates alternative sets (`555697863|10906`;
  see `aoi_id_match` in `src/goldset/evaluators/README.md`), and `/` lists
  one area's equivalent records within a set (`555697863/10906;2017`).
  Batch 1 rows keep their pinned ids.
- No `aoi_absent` check: "must not substitute a wrong area" is approximated
  with the `clarification` and `text` judges.
- The scope classifier has no class for "resolved an area and stopped", so
  these cases omit `scope`.

Deferred: a custom-areas set (needs seeded areas under the run token's
user), multi-turn area refinement, coordinate support.

### Pinning the five `todo` rows (one-off procedure)

`ch-aoi-095`, `-098`, `-099` and `-101` (expansion id lists) and
`ch-aoi-108` (Lahti, which name search cannot reach) are `todo` because
their expected ids could not be pinned. To pin one:

1. Run it once, including `todo` cases:
   `uv run evals run --suite challenge --env prod --id <id> --status-exclude "not doing" --build "<label>"`.
2. Read the selected ids from the run's artifact,
   `results/challenge/artifacts/<run_id>/<uid>.json.gz`.
3. Verify them against prod `/api/aois`, put them in the case's
   `expected`, record how in `notes.verified`, and set the status to
   `ready`.
4. Follow [After an edit](README.md#after-an-edit).

## Batch 2: the numeric sets (quantification, trend, comparison)

Ported from `eval-metrics-slice-1` in gnw-evals, the eval harness this repo
replaced (github.com/wri/gnw-evals, retired). Slice 1 was the eval-metrics
programme's first numeric slice: 90 TCL cases. Set = intent, cohort =
dataset (short names in `generation/dataset_config.py`): quantification and
comparison cells for the 11 default-profile catalogue datasets, and trend
for the five time-series ones. The 90 slice-1 TCL cases came over with
reviewed wordings; the other cells' wordings were generated from the held
manifests. Authoring machinery and workflow: `generation/README.md`.

Scoring is **retrieval-first**: dataset, area and date checks, explicit
(non-default) canopy as `dataset_parameters`, forest-filter behaviour as
`context_layer` (explicit opt-outs score `no_selection`, which detects the
primary-forest substitution), and `data_pull` on every row. The slice-1
ground-truth fidelity checks (`data_fidelity`, `number_usage`) were
deliberately not ported: they were written for TCL only, and generalising
them was left to a later evaluator workstream. So the Explanation bucket
rode in `notes.judge_instruction`, unscored, and no case stores an expected
number: ground truth must be computed at run time so that it survives data
version bumps. The draft-5 review (2026-10-27, below) added `figure`
formulas, which are checked against the table the agent itself pulled.

Known coverage informed by live bugs: primary-forest substitution
(`no_selection` rows), the canopy-default quirk (explicit-canopy rows),
date-scoping flakiness (the biggest slice-1 retrieval drag; every dated row
scores `date_extraction`), and alert routing after DIST-ALERT's removal
(all alert cells expect integrated alerts, id 11).

## Batch 3: the `dataset` set

200 dataset-selection prompts (`cases/challenge/dataset/<cohort>/`, ids
`ch-dataset-001` to `-200`). Each asks only to see a layer on the map, with
no place, no quantity and no date, so the one tool that should run is
`pick_dataset` (the frontend draws the tile layer from `state.dataset`; there is
no separate add-to-map tool). The set was built to compare project-zeno's
dataset selector, which retrieves candidate datasets and asks a language
model to choose (retrieval-augmented generation, RAG), with jev, a decision
model trialled as a replacement (project-zeno PR #841, closed). Seed and
per-row lineage: `seeds/challenge-dataset-v1.csv`; expectations from the
project-zeno catalogue at e2fb83f (`selection_hints`, `context_layers`,
`parameters`).

| cohort | n | scored |
|---|---|---|
| 10 dataset cohorts (land-cover, grasslands, natural-lands, tcl, tc-gain, ghg-flux, tree-cover, tcl-drivers, tcl-fires, integrated-alerts; ids 1 to 8, 10, 11) | 13 each (easy, medium, hard: 4, 5, 4) | `dataset_id` (five rows add an explicit non-default `dataset_parameters` canopy) |
| multilingual (es, pt, fr, id, sw) | 25 | `dataset_id` (two rows add `context_layer`) |
| context-layer | 15 | `dataset_id` + `context_layer` (primary or intact asks, and `no_selection` opt-outs) |
| ambiguous | 15 | 11 pinned `select` rows with `;` alternatives, 4 pinned `nudge` rows (`dataset_choice` + options) |
| unmappable (sLUC, climate and other asks outside the catalogue) | 15 | `dataset_id: no_selection` (sLUC `9;no_selection`) + `text` |

sLUC is the statistical land-use change emission factors dataset (id 9).

Every row also sets `forbidden_tools` (pull_data, generate_insights,
create_dashboard, add_to_dashboard, add_map_widget, search_blogs,
search_insights, show_imagery), which gates `forbidden_tools_absent`: the
set's scope-isolation assertion. The list is hashed, so changing it gives
all 200 cases new uids. `pick_aoi` is deliberately **not** forbidden
(decided 2026-09-25): the set tests the dataset picker only, and picking a
layer and then asking "where?" through `pick_aoi` (seen on 3 of 31 smoke
trials) is acceptable behaviour, not a scope leak.

Scoring decisions and gaps:

- Plain dataset cohorts do **not** score `context_layer`. With no area, the
  selector sees every layer unfiltered, and the TCL and fires
  primary-forest descriptions say to default to that layer for general
  forest loss, so a primary pick on "show tree cover loss" is policy, not
  error. Only the context-layer cohort scores it.
- The ambiguous cohort cannot say "select X **or** nudge": each row pins one
  behaviour (`notes.behaviour`), with the alternative in `notes.lineage`.
- **The four nudge rows cannot be won by jev v1**: jev returns one choice
  plus a confidence, and `none` goes down the no-match path with no
  suggestions, so it never emits a `dataset_choice` nudge. They stay in:
  the ambiguous cohort failing under jev is a finding. Read them separately
  when comparing selectors.
- Unmappable rows pass on "no dataset selected + honest text"; a nudge is
  neither required nor penalised.
- `text` is the only judged check (15 rows, one Haiku call each per trial).
- Dates are deliberately unscored (the set is date-free).

The set was named `map` (ids `ch-map-NNN`) until 2026-09-29.

### Comparing two builds locally (the jev comparison, 2026-09-25)

The two local runs `20260925T113115Z_local` and `20260925T121040Z_local`
compared the selectors on this set. The protocol, kept for a future
comparison of two agent builds:

- Prod, default profile, 3 trials stays the published reference series.
  The verdict is read from a **local-main against local-candidate** pair
  (same commit, same stack, same trials, same `--workers`), never prod
  against local.
- Latency is half of such a verdict. The rollup reports median, p90 and
  mean per set and cohort from `stream_s` (POST /api/chat to the last stream
  line: the agent turn, without the state GET or judge time). Older runs
  carry only `latency_s`, which also spans the state GET; the rollup says
  which basis it used.
- Run both local sides with `--workers 1` (recorded on the run as
  `workers`): concurrent turns contend for one local API and inflate each
  other's latency.
- Compare with `tools/challenge_rollup.py <local-main>.json
  <local-candidate>.json`: the cross-run latency table gives both runs side
  by side with median deltas and flags any environment, workers or basis
  mismatch.
- **Prod latency is reference only.** It includes internet round trips and
  prod infrastructure (autoscaling, other users' load), so a gap between
  prod and local says nothing about the selector.

## Batch 4: the benchmark v2026 cases (`monitoring`, `causal`, AOI-level)

63 cases from the proposed BENCHMARK v2026 set
(`seeds/benchmark-v2026-proposed.csv`, rows marked NEW), written by hand on
2026-10-01 in a Claude Code session from GFW and LCL user stories rather
than observed traffic, so every one is tagged `notes.synthetic: TRUE`.
Expectations were **drafted, not reviewed** (`notes.expectations`); area
ids were resolved against prod `/api/aois` on 2026-10-01. Review them before
the freeze.

| set | n | what it adds |
|---|---|---|
| `monitoring` (new) | 30 | near-real-time integrated alerts (dataset 11) for parks, Indigenous territories, states and districts; rolling windows use run-relative date tokens with `date_tolerance_days`; 4 non-English; 3 scope rows judged by `text` |
| `causal` (new) | 18 | driver and fire attribution; judged `text` checks for not over-claiming a commodity, checking the question's premise, and the selective-logging caveat |
| quantification, comparison, trend | 15 | the same analyses at protected-area, Indigenous-territory and sub-national level (every earlier analytic row is country-level) |

- Questions that name no dates carry no expected window: the window is the
  agent's call, and an expected one would fail correct answers.
- `ch-mon-028` (triage across a user's saved areas) is `todo`: it needs a
  seeded test account.
- Protected-area (WDPA) analytics fail upstream while PZB-1406 is open;
  those rows count as failures, as any user would see them.

## Batch 5: the v2026 benchmark sheet (`portfolio` set, plus monitoring, numeric and causal rows)

168 cases written by hand on 2026-10-23 from the benchmark sheet exported
on 2026-10-22 (`seeds/benchmark-v2026-bef-2026-10-22.csv`, 299 rows; the
sheet's file names carry `bef`): the rows that no existing case answers.
The sheet's other 131 rows reuse existing cases (98 real-traffic cases by
`challenge_id`, 33 earlier synthetic cases by query text). Every new case
is synthetic and its expectations are **drafted, not reviewed**
(`notes.expectations`). Area ids were resolved against prod `/api/aois` on
2026-10-23, with doubtful or unpinned ones explained in `notes.verified`.

| set | new | what it adds |
|---|---|---|
| `portfolio` (new) | 27 | many areas at once (ranking every state, screening uploaded sites, saved-area triage), judged by `text`; revised on 2026-10-24 to the real limits (below); `notes.reclassify_when` says when the fixture rows become "answer with data" |
| `monitoring` | 36 | alert follow-up (imagery, clusters, coordinates, prioritising), alert context (natural lands, primary forest, mangroves, park buffers), alert method questions, unsupported actions and fixture rows |
| quantification, comparison, trend | 93 | sub-national, protected-area and Indigenous-territory analyses, two- and three-area comparisons, data or method questions (`method` cohort, `text` only), unavailable data (`unavailable`) and many-area redirects (`many-areas`) |
| `causal` | 11 | alert causes, driver shares, commodity over-claims and premise checks |
| `aoi` | 1 | an ambiguous Amazon question |

- **Fixture rows are `todo`.** 29 new rows (plus `ch-mon-028`) need a seeded
  test account with a custom area or a 25-polygon portfolio. Their
  `status_reason` names the fixture, and BENCHMARK `2026-draft-3` lists them
  as excluded (the repo owner, 2026-10-23).
- **Unconfirmed capabilities run now.** Rows the sheet marks "Confirm with
  engineering" (imagery, alert clusters, coordinate export, VIIRS fire
  alerts, concession and buffer analysis, production forests) carry an
  either-or `text` expectation that accepts a correct answer or an honest
  "not available". `notes.capability_check` marks them for engineering to
  confirm (the repo owner, 2026-10-23). Concession areas (logging, mining,
  oil palm) are in the area index, so the Lomié and mining-overlay rows may
  deserve a firmer expectation once confirmed.
- **Open-ended windows end in 2025.** Tree cover loss, fires, drivers and
  flux run to 2025 (catalogue `content_date`), so "since 2021" expects
  2021-01-01 to 2025-12-31 where the sheet wrote 2024-12-31; each case says
  so in `notes.build_notes`. Questions that name no window carry none, as in
  Batch 4.
- Each member's sheet facets (use cases, engagement, area type,
  capability, grounding) are case notes written by
  `tools/benchmark_from_sheet.py`.

### Expectation review after the first draft-3 run (2026-10-24)

The first `2026-draft-3` run (`20261023T094447Z_prod`; recommendations in
`results/benchmark/recommendations/`) showed that some drafted expectations
were wrong. The repo owner's decisions were applied to 44 cases (26 run, 18
fixture rows); each case's `notes.review` gives its evidence:

- **Many areas: the real limits.** `pick_aoi` takes up to 1,000
  administrative sub-units of one GADM parent, but only 50 protected areas,
  KBAs (Key Biodiversity Areas), Indigenous lands or concessions
  (project-zeno `src/agent/subagents/pick_aoi/tool.py`). Rows within the
  limit now expect an answer with data (every municipality of Pará, every
  department of Bolivia, African countries, Brazilian states, districts of
  two countries); the rest keep a redirect worded to the real limit, never
  "one to three named areas". The sheet's `capability` facet still says
  "Not yet" for the reclassified rows; fix it in the sheet before the next
  curation.
- **Either-or rows** whose decline branch selects no dataset carry no
  dataset or date checks.
- **Defensible alternatives:** emissions from loss accept tree cover loss
  (`6;4`), land cover accepts natural lands (`1;3`), and four area
  expectations use the `|` any-of syntax (Salonga, Kakataibo, Mahakam
  Delta).
- **Confirmed capability:** alerts on natural lands (`ch-mon-058`) now
  expect data with `context_layer: natural_lands`.
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

Reviewing the draft-4 failures, the repo owner decided that asking which
dataset to use is a right answer when the choice offered is the right one.
Sixteen members asked back on every attempt. Fourteen of them now carry
`accept_nudge_offering` (their `dataset_id` set): an attempt that ends in a
`dataset_choice` nudge offering every listed dataset passes, extra options
allowed, and a correct pull still passes. The check and the attempt-majority
verdict are documented in `src/goldset/evaluators/README.md`
(`accepted_nudge_match`). The other two are not dataset choices and are
unchanged: `ch-aoi-090` asks which Pará and `ch-mon-027` never nudges.
Replayed on their 23 and 24 October attempts, 9 of the 14 would pass; the 5
that still fail never offered SBTN Natural Lands (`ch-comp-154`, `-157`,
`ch-quant-175`, `-180`) or offered only the sLUC emission factors
(`ch-comp-155`). The members' new uids are unmeasured until rerun.

The repo owner then reviewed the 18 members that pulled on some attempts
and asked on others, and opted in three more: `ch-causal-025` (`4;8`) and
`ch-causal-015` (`8;10`) accept a dataset choice, and `ch-quant-188` accepts
an area choice through `accept_aoi_nudge_offering` (`BRA.14`): asking which
Pará is meant is fine as long as Pará, Brazil is offered. Replayed,
`ch-causal-025` would pass (it failed) and the other two still pass. The
other 15 keep their expectations: their failures are agent fixes or correct
as they stand.

### "Why" questions answered from blogs (2026-10-26)

Nineteen members answered from `search_blogs` instead of the data. A search
of the corpus the tool reads (WRI and Land & Carbon Lab Insights; the list
is in `experiments/2026-10-26-search-blogs-corpus/` of the GNW workspace
repository, which is not public) found posts that
fairly answer three of them. The repo owner decided that those three may
pass on a blog answer and the rest must be answered from data, then kept
four as they were:

- `ch-causal-002` (Bolivia 2024), `ch-causal-003` (Brazil 2016) and
  `ch-causal-022` (Riau) carry `accept_blog_sources`, the slugs of the posts
  that answer them. An answer from `search_blogs` that links one passes, and
  `web_fallback` ignores those posts on a pull (`accepted_blog_match` in
  `src/goldset/evaluators/README.md`).
- Ten of the other 16 already required a pull. Two now do: `ch-trend-081`
  (pull flag added) and `ch-quant-173` (Brazil, sLUC and a pull). The repo
  owner kept `ch-causal-029`, `ch-quant-166`, `ch-aoi-155` and `ch-quant-190`
  as they were (text expectations only); a data requirement was drafted for
  each and dropped in review.

### Ghana questions moved to Côte d'Ivoire (2026-10-26)

The analytics API rejects every Ghana sub-national GADM id: GADM 4.1 writes
them without the dot (`GHA15_2`), and the fix is PZB-1408. Until then the
eight Ghana members moved to similar areas in Côte d'Ivoire, Ghana's
cocoa-belt neighbour: Western region to Cavally (`ch-causal-001`), Western
North to Nawa (`ch-comp-149`, `ch-mon-011`), Western North and Ashanti to
Nawa and Haut-Sassandra (`ch-comp-150`), the Offinso districts to Cavally,
Guémon and Tonkpi (`ch-comp-163`) and to San-Pédro (`ch-mon-041`,
`ch-mon-045`), and the Ghana Cocoa Belt to Côte d'Ivoire's cocoa belt
(`ch-causal-026`). Each case keeps its Ghana version in
`notes.ghana_original`. The benchmark sheet matches these rows by query
text, so `seeds/benchmark-v2026-bef-2026-10-26.csv` is the 22 October export
with those eight queries substituted, and `2026-draft-4` is built from it.
Restore the Ghana versions once PZB-1408 is fixed.

### Draft-5 review: could this answer mislead the user? (2026-10-27)

Before the draft-5 run, every draft-4 member was reviewed against one
question from the repo owner: could this answer mislead the user? Each case
is scored only on the one to three things that could mislead for it. A
check that failed an answer that would mislead no one was eased, and a
misleading answer that passed got the lightest check that catches it. The
per-question findings and decisions are in the review doc ("BENCHMARK
draft-4 critical review", claude.ai artifact 68PEmch8CvCEJwgB2xtmTy, which
is private). Applied to 213 case files:

- **Figures from the agent's own pull.** About 170 members gained a
  `figure` formula (and some a `figure_claim`), checked by `figure_match`
  and `figure_claim_match` against the table the agent itself pulled; data
  quality is out of scope. Column names and values were confirmed against
  real pulled tables. See `src/goldset/evaluators/README.md`.
- **Periods.** `date_extraction` passes a pull that contains the asked
  window; `answer_period_match` checks that the answer uses exactly the
  asked period.
- **Fair alternatives.** New `/` records per area in `aoi_ids`, `|`
  alternatives in `context_layer` and in the nudge accept fields, plus the
  expectations the review proposed (datasets that can answer the question,
  defensible area records, sharper `text` that writes the fact in, tone and
  format clauses dropped).
- **Ghana.** `ch-quant-180` (Ashanti to Haut-Sassandra) and `ch-port-017`
  (Côte d'Ivoire only) moved like the eight 2026-10-26 Ghana questions;
  `notes.ghana_original` keeps the old wording.
- **Not applied, left for the repo owner:** `ch-quant-164` and `ch-aoi-090`
  (would reverse earlier calls), `forbidden_tools` on the dataset questions
  (set-level), the `ch-causal-010` caveat direction and the `ch-aoi-116`
  branch. Prose ask-backs are not yet accepted (no harness support).

Each edited case records the change in `notes.review` and stamps
`notes.expectations` with "draft-5 review 2026-10-27".

### Verdict rule: attempt majority (2026-10-28)

From 2026-10-28 a case passes when most of its scored attempts were right,
an attempt being right when every applicable non-info check passed on it.
Before, a case passed when each check passed on most attempts. Rates in
reports written before that date are not comparable point for point.

## How the seed imports are known

The two seed CSV imports are established from the cases and the git
history, not from a record of the commands. Every case from those CSVs
carries `notes.source_tab` with the CSV's name, which is what
`tools/import_sheet.py --csv` writes. The import commit of the `dataset`
set (2026-09-25) names `--set map`, the set's name before it was renamed
`dataset` on 2026-09-29. `tools/import_sheet.py` is one of the legacy tools,
and it writes to `cases/v2` unless you pass `--cases-dir`.
