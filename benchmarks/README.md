# BENCHMARK

A **frozen, versioned subset of CHALLENGE** that tracks improvement over
about a year. CHALLENGE (`cases/challenge/`) grows and changes, so its rates
move under readers. BENCHMARK does not: it is the exam behind the published
North Star.

| | GOLD (`cases/v2`) | CHALLENGE (`cases/challenge`) | BENCHMARK (`benchmarks/`) |
|---|---|---|---|
| Question | did a release break something? | how good is the system, per capability? | is the system getting better, on a fixed exam? |
| Headline | regression count | pass rate per set / cohort | North Star complete rate + trend |
| Changes | curated per release | grows continuously | frozen per version (~annual) |
| Cases | own store | own store | **no cases of its own**: a uid manifest over CHALLENGE |

## One version = one manifest

`benchmarks/<version>.json` (contract and validation: `src/goldset/benchmark.py`):

- `status`: `draft` → `frozen` → `retired`. `frozen` carries the freeze date.
- `members[]`: `{uid, id, type, set, cohort, difficulty, stages}`. Membership
  is by **uid**; `type` etc. are frozen at sampling time, so a taxonomy or
  case-note change later cannot move a member between types mid-version.
- `types[]`: the 12-type query axis (the FE's taxonomy with Spatial split
  into **Geospatial** = aoi set and **Dataset** = dataset set, separate
  types). Types without sets are listed as `measured: false`: reports show
  them as "not yet measured", never as zero.
- `stage_order`: the attribution order `scope > retrieval > analysis >
  explanation > output`.
- `sampling`: the full record (tool, seed, eligibility, per-stratum allocation).
- `errata[]`: `{uid, date, reason}` voids.
- `pairs_with` (optional): on a languages companion, the English version
  its members pair with (see [Languages companion](#languages-companion)).

### Current versions

| Version | Status | Members | Notes |
|---|---|---|---|
| `2026` | frozen 2026-11-18 | 269 (the members of `2026-draft-5`, uid for uid) | the English North Star set for 2026 (AJ, 2026-11-18). Immutable apart from errata. Frozen with the 30 seeded-account rows still excluded, 113 of the 139 expectations drafted on 2026-10-23 not yet human-reviewed, and no single full run of all 269 members (the newest results are the 27 Oct run plus the 28 Oct reruns, recorded under `2026-draft-5`); its first canonical run is still to come |
| `2026-draft-5` | retired | 269 (as `2026-draft-4`) | `2026-draft-4` after the 2026-10-27 review, judged by "could this answer mislead the user?" (`cases/challenge/README.md`): figure formulas (`figure`, `figure_claim`) on about 170 members, checked against the table each attempt pulls, and 209 revised expectations; `ch-quant-180` and `ch-port-017` moved off Ghana (seed `seeds/benchmark-v2026-bef-2026-10-27.csv`); frozen as `2026` on 2026-11-18; keeps its 27 and 28 Oct runs as history |
| `2026-draft-4` | retired | 269 (as `2026-draft-3`) | `2026-draft-3` with 26 expectations revised after its first run (`cases/challenge/README.md`, expectation review 2026-10-24): many-area rows reworded to the real `pick_aoi` limits or moved to answer-with-data, either/or rows without dataset checks, defensible alternative datasets and AOIs (two texts reworded again after the first rerun, so draft-4 was rebuilt in place), and on 2026-10-26 seventeen members that asked back gained `accept_nudge_offering` or `accept_aoi_nudge_offering`, three why-questions gained `accept_blog_sources`, two now require data, and the eight Ghana questions moved to Côte d'Ivoire while PZB-1408 is open (seed `seeds/benchmark-v2026-bef-2026-10-26.csv`; rebuilt in place each time); of the 139 cases drafted on 2026-10-23, 26 were revised from run evidence and 113 are unchanged, and none is human-reviewed yet; replaced by `2026-draft-5` on 2026-10-27; keeps its 23 to 26 Oct runs as history |
| `2026-draft-3` | retired | 269 (quantification 84, comparison 57, monitoring 41, causal 31, trend 23, geospatial 9, refusal 9, portfolio 9, dataset 6) | curated from the v2026 BEF sheet of 2026-10-22 (`seeds/benchmark-v2026-bef-2026-10-22.csv`, 299 rows); members carry priority use cases UC1–UC6; 30 rows that need a seeded test account are excluded; replaced by `2026-draft-4` on 2026-10-24; keeps its 23 Oct run as history |
| `2026-draft-2` | retired | 199 (quantification 45, comparison 32, trend 32, monitoring 29, causal 24, geospatial 15, refusal 15, dataset 7) | curated from the proposed v2026 set (`seeds/benchmark-v2026-proposed.csv`); members carry JTBD jobs, impact pathways and user groups; replaced by `2026-draft-3` on 2026-10-23; keeps its 1 Oct run as history |
| `2026-draft` | retired | 100 (20 each: geospatial, dataset, quantification, comparison, trend) | sampled 2026-09-29; replaced by `2026-draft-2`; keeps its 29 Sep run as history |

Use cases (`USE_CASES` in `goldset.benchmark`; a question can carry several):
UC1 Alert monitoring and response, UC2 Supply chain and sourcing, UC3
Investigating causes, UC4 Reporting and accountability, UC5 Landscape context,
UC6 Understanding the data. `2026-draft-3` (and `-4`) also adds the **Portfolio** type
(many areas at once; the `portfolio` CHALLENGE set), so the type axis has 13
types.

A version is either **sampled** (`tools/benchmark_sample.py`, stratified
from CHALLENGE) or **curated** (`tools/benchmark_from_sheet.py`, one member
per row of a reviewed sheet export, with the row's use-case facets). Both
write the same manifest contract.

## Languages companion

The questions in Spanish and Indonesian sit in a companion manifest,
`benchmarks/<version>-languages.json`, beside the English version. The
English manifest is never changed for them.

- Each question in another language is its own CHALLENGE case, with its own
  uid, in its type's set. It names an English `twin` that holds the same
  expectations (`cases/challenge/README.md`), so the score gap of a pair
  measures the language alone.
- The companion's top-level `pairs_with` names the English version, for
  example `"pairs_with": "2026"`.
- A member can carry two more optional facets, written only when set:
  `language` (`es` or `id`; absent means English) and `twin_uid` (the uid of
  its pair). A member with a `language` always has a `twin_uid`.
- The twin is either a member of the companion or a member of the
  `pairs_with` version. The companion names those English members by uid and
  does not hold them. It does hold the English twins that were written for a
  question in another language and are not in the English version.
- **The language rates sit beside the English headline and never count in
  it.** The North Star is the English version's rate. A companion is run and
  reported as its own version, and its rates are read per language against
  the same pairs in English.
- **A reply in the wrong language is never a fail.** The info-only check
  `reply_language_match` records whether each reply is in the question's
  language (`src/goldset/evaluators/README.md`). It runs on English
  questions too, so each language has a rate, and it changes no verdict.

Write the expectations once, then build and check:

```bash
# Copy expected from one case of a pair to the other (either direction).
uv run python tools/twin_case.py --from <case id> --to <case id>
uv run python tools/check.py --fix --cases-dir cases/challenge
uv run python tools/coverage_doc.py --cases-dir cases/challenge

uv run python tools/benchmark_languages.py \
  --version 2026-languages --pairs-with 2026
uv run python tools/check_benchmark.py
```

`benchmark_languages.py` selects every `ready` case with a `language`, plus
those cases' twins that are not members of the `pairs_with` version. A
member whose twin is in that version takes the twin's type and optional
facets (use cases and the rest), so both halves of a pair sit in the same
groups. `check_benchmark.py` checks each pair against the store: the case's
language, that `twin_uid` is the uid of the case's `twin`, and that the twin
is an active member of the companion or of the `pairs_with` version. If the
`pairs_with` manifest is missing, it reports that as one problem.

### The page's `languages` block

Write a companion's page with the English run as its base, so the twins
that are members of the `pairs_with` version have a result:

```bash
uv run python tools/benchmark_page.py results/benchmark/runs/<companion run>.json \
  --base results/benchmark/runs/<English run>.json
```

`--base` matches results by uid, so it needs the two runs to share
environment, ff and trial count, as for a rerun. The page of a manifest that
has a member with a `language` then carries one more top-level key,
`languages`. A page of any other manifest does not have the key and is
byte-identical to what the tool wrote before
(`tests/test_benchmark_page.py` pins it). **The block is internal until the
frontend adds a parser**: the FE parses the page strictly and shows only the
runs it pins, so do not pin a companion page before then.

On a combined page, each `run.sources` entry of a companion page also has
`twins_drawn`: how many twins of the measured pairs came from that run. A
base that holds only twins shows `questions: 0`, because its twins are no
members of the companion; `twins_drawn` says it was used. The tool reads the
`pairs_with` manifest from the same directory and stops if it is missing.

`languages` is a list with one object per language of the manifest, `es`
before `id`:

| Field | Meaning |
|---|---|
| `key` | `es` or `id`. |
| `pairs` | Pairs measured: the question and its English twin both have a pass or fail verdict. Every figure below is over these pairs. |
| `unpaired` | Questions whose twin has no result in the run or its bases, or whose twin an erratum voids (in the companion or the `pairs_with` version). Left out, never a fail. |
| `unscored` | Pairs with an errored or uncovered side. Left out, as errors leave every rate. |
| `twin_runs` | The ids of the runs the measured pairs' twins came from, sorted. |
| `max_days_apart` | The largest gap in calendar days between a question's run and its twin's run, over the measured pairs; null with none. Above 0 the agent may have changed between the two sides, so that change is inside `gap`. Above 1 the tool prints a warning to stderr: rerun the twins, or read the gap with care. |
| `native` | The questions in the language: `every_time` (right on every scored attempt) and `majority` (right on most), each `{n, passed, rate, ci_low, ci_high}` with a Wilson 95% interval. The two standards are the page's own. |
| `english` | The same two rates for the English twins of the same pairs. |
| `gap` | The paired gap on the `majority` rate, native minus English: `difference`, `ci_low`, `ci_high`, and the discordant pairs `native_only` and `english_only` (right on that side only). `difference` is null with no pairs. |
| `reply_language` | For `native` and for `english`: `{matched, scored, undecided, rate}`. `rate` is the share of scored attempts whose `reply_language_match` is 1.0; attempts where the check is null or absent are left out and counted in `undecided`. Info-only: it changes no other figure. |
| `failure_modes`, `failure_modes_by_standard` | Where the questions in the language went wrong, by the page's stage attribution, in the shape every group carries. |

The gap's interval is the Agresti-Min adjusted Wald interval for a
difference of paired proportions (Agresti and Min, 2005;
`challenge_rollup.paired_difference`): 0.5 is added to each of the four
cells of the paired table (both right, native only, English only, both
wrong) before the Wald interval is taken. Pairs that agree move neither
rate, so only the discordant counts set the difference. With no discordant
pair the plain Wald interval has zero width; this one keeps about
±1.96/(pairs + 2). The interval is centred on the adjusted difference, and
`difference` is the observed one.

On a companion page, `summary`, `types`, `use_cases` and `stages` cover only
the members without a `language`: the English twins the companion holds. The
rate of each language is in this block alone, so no figure of the page mixes
languages. `questions` still lists every member. The twins held here are a
few questions, not the North Star: read that from the English version's
page.

## Adding a language

The steps that added Spanish and Indonesian (18 and 19 November 2026), for
the next language. Read [Languages companion](#languages-companion) first.
The sheets, scripts and review notes of the first two languages are in the
GNW workspace, `experiments/2026-11-18-multilingual-benchmark-questions/`.
`<lang>` is the language code.

### 1. Make the harness accept the language

A new code needs a harness change, on its own branch, before any case is
written. Today the harness accepts `es` and `id` only:

| Where | What a new code needs |
|---|---|
| `src/goldset/canonical.py`, `LANGUAGES` | The code. The case check (`store.py`), the member check (`benchmark.py`), `gold run --language` and the order of the page's `languages` block all read this tuple. |
| `schema/case.schema.json`, `language` | The code in the enum. `tests/test_schema.py` keeps the enum equal to `LANGUAGES` without `en`. |
| `src/goldset/evaluators/figures.py` | How `figure_match` reads the reply's numbers: the usual decimal mark (`_USUAL_DECIMAL_MARK`, measured on Horizon's replies in the traces, not the textbook convention), scale words (`_LOCAL_SCALES`, required for every code), percent and km² words (`_LOCAL_NUMBER`, `_KM2_PHRASE`), units (`_LOCAL_UNITS`) and phrases that state a zero (`_LOCAL_ZERO_WORDS`). |
| `src/goldset/evaluators/reply_language.py` | The language's function words in `FUNCTION_WORDS`, in `LANGUAGES` order (an assert checks it). French and Portuguese are decoys in `DECOY_WORDS` today. |
| Tests and docs | Several tests use `fr` as the example of an unknown code. This README, `cases/challenge/README.md`, the evaluators README and `CLAUDE.md` name `es` and `id`. |

The page schema needs no change: it does not describe the `languages` block.

### 2. Choose the questions

Write the questions as a sheet, `<lang>-pairs.csv`, before any case exists.

1. Check that the language is a core language: more than 5% of external
   users' turns over 12 months (AJ, 2026-11-18). For the year to 17
   November 2026, French had 3.8% and Portuguese 1.2%. Below that, the owner
   decides.
2. Plan 80 pairs (about ±10 points on the language rate; they find a gap
   to English of 15 points or more). Each use case gets the mean of its
   share of the `2026` use-case tags and of the language's traffic (each
   user counted once; trace task and topic labels mapped to UC1 to UC6),
   and at least 6.
3. Fill each use case with translated pairs first: active `2026` members
   about places where the language is spoken, by their first use case.
   Spanish took 43 of 50 such members, Indonesian 20 of 25. Leave out a
   member whose test rests on English wording (an English designation,
   "Borneo" for "Kalimantan"), a near copy and a member with no place.
   Never move a member's area.
4. Fill the rest with native pairs: prompts in the language from GNW Horizon
   Traces, external users, no suggested prompts. Sample by user, not by
   turn (one user wrote 243 of the 247 Venezuelan turns). Spanish took 37
   prompts from 37 users, Indonesian 60 from 41.
5. Keep a native prompt only when it names an area that can be found
   (method and tool questions excepted), Horizon can answer or fairly
   decline it, and it stands alone (a later turn can; say so in `notes`).
   Leave out repeats of a `2026` member, imagery, answers to a clarifying
   question and details that point to a person or an organisation. Use a
   scripted (workshop) wording at most twice.
6. Give each row a type, set and cohort that has a `2026` member.

Columns: `pair_id` (`<lang>-t-NNN` translated, `<lang>-n-NNN` native),
`kind`, `use_case`, `type`, `set`, `cohort`, `english_id` and `english_uid`
(translated rows: the member), `english_query`, the question in a column
named for the language (`spanish_query`), `source` (`trace YYYY-MM`),
`notes`, and `expected_draft` and `unverified` (native rows, step 4).

### 3. Translate and review

1. A translated question keeps every area, date, period, threshold, dataset
   word and measure of its member, and its ambiguity. "Deforestation" and
   "tree cover loss" stay apart, as in the member.
2. The English twin of a native prompt is a faithful, natural translation
   that repairs nothing: it keeps the user's vagueness, abbreviations
   ("kalteng") and words ("forest cover", not the dataset name). It never
   copies a typo.
3. In a native prompt, correct a misspelt place name (`es-n-024`), so both
   sides ask about the same place. Keep other typos, case slips and missing
   accents.
4. A subagent that reads the language reviews all 80 rows against these
   rules, the later turns, repeated wordings and personal details
   (`<lang>-review.csv` and `.md`). Per row: `verdict` (`ok`, `fix`,
   `drop`), `issue` (`natural`, `correct`, `twin`, `same-question`,
   `typo-asymmetry`, `not-self-contained`, `other`), text for each side and
   a note. It lists the rows a native speaker must read.
5. The owner decides the flagged rows. The result is
   `<lang>-pairs-reviewed.csv`, with the text before a fix in
   `<language>_query_draft` and `english_query_draft`. A replaced row keeps
   its `pair_id`; the old row goes to `<lang>-replaced-rows.csv`, the new
   one to `<lang>-replacements.csv`.
6. Native speakers verify later. Until then each case in the language
   carries `notes.language_review: subagent review <date>; native speaker
   not yet`. A note never changes the uid.

### 4. Write and verify the expectations

A translated pair takes its member's `expected` as it is. A native pair
gets expectations in English, checked without an agent run.

1. Write `expected_draft` as one line of YAML in the case vocabulary
   (`aoi_ids`, `dataset_id`, `start_date`, `end_date`, `data_pull`,
   `figure`, `text` and so on), after a similar `2026` member. `aoi_name`
   and `aoi_source` are helper keys, not case fields. Write an unchecked id
   as `UNVERIFIED (<name>, <level>)` and name its key in `unverified`.
2. A subagent checks each draft against the `2026` members (precedents),
   the catalogue snapshot `cases/zeno_catalog.json`, the GADM areas in a
   local project-zeno database, a search of the production `/api/aois`
   (WDPA, KBA and landmark ids) and the areas the traces resolved. It fills
   `verify_verdict` (`verified`, `corrected`, `partial`),
   `expected_verified`, `still_unverified`, `verify_changes`,
   `verify_precedent` and `verify_evidence`. 59 of the 97 Spanish and
   Indonesian drafts needed a correction.
3. The owner settles what is still open. No `UNVERIFIED` value may remain.

### 5. Create the cases and the companion

`make_cases.py`, in the experiment's `pilot/` folder, wrote the cases from
the reviewed sheets. **It is not a repo tool yet**: for a new language,
change its sheet folder, language loop, query column map (`QCOL`) and the
dates in its notes. Run it from the worktree root with `--dry-run` until it
reports no problem, then once without: it writes every good row and only
reports a bad one (an `UNVERIFIED` value, a member uid that is not
`english_uid`, a set and cohort the store lacks), and a second run writes
the native pairs again under new ids. It requires 80 rows per language.
A translated row becomes `<member id>-<lang>` with the member's set,
cohort and `expected`. A native row becomes two cases with one `expected`:
the English twin at the next free id of its set (`ch-quant-206`) and the
question as `<twin id>-<lang>` (`ch-quant-206-es`). Notes: `lineage`,
`pair_id`, `use_cases`, `synthetic`, `language_review` (the language side
only) and, for native pairs, `benchmark_type`, `verified`, `precedent` and
`aoi_name`.

Then run the commands below, without the first line. Run all of them after
any later change to a pair: edit the English twin (never one side only),
then copy it across with `twin_case.py`.

```bash
uv run python tools/twin_case.py --from <English id> --to <case id>
uv run python tools/check.py --fix --cases-dir cases/challenge
uv run python tools/coverage_doc.py --cases-dir cases/challenge
uv run python tools/benchmark_languages.py \
  --version 2026-languages --pairs-with 2026
uv run python tools/check_benchmark.py
uv run pytest -q
```

One companion holds every language. `benchmark_languages.py` takes every
`ready` case with a `language` and has no option for one language, so a
rebuild adds the new language to `2026-languages`. It keeps the draft's
creation date, errata and `pairs_with`, and never rewrites a frozen
manifest.

### 6. Pilot, triage and fixes

1. Pick 20 pairs per language over both kinds and every use case. On one
   day, run the twins that are `2026` members first, then the pilot's
   companion members (its questions and the twins the companion holds):
   1 trial, production, default profile. Pilot runs are never committed.

   ```bash
   caffeinate -i uv run gold run --env prod --trials 1 \
     --benchmark benchmarks/2026.json --id <member id> ... --build "<label>"
   caffeinate -i uv run gold run --env prod --trials 1 \
     --benchmark benchmarks/2026-languages.json --id <case id> ... \
     --build "<label>"
   ```

2. Read every failed answer on both sides and class it **Agent** (the agent
   was wrong), **Judge** (an AI reviewer misread a right reply) or **Case**
   (the expectation is wrong or too strict). Record per pair each side's
   cause and reason, a note and the case fix. The first pilot's 34 failed
   answers were 23 Agent, 9 Case and 2 Judge.
3. Fix a Case finding with a clear answer on both sides (step 5).
4. Put every other point to the owner as a decision card: both prompts, the
   failure, a suggestion and the options. Apply the decisions the same way.
5. A `2026` member with a wrong expectation is never edited. Add an erratum
   `{uid, date, reason}` to `benchmarks/2026.json` that names the corrected
   copy: a new case at the next free id in the member's set and cohort,
   with the member's notes (less `benchmark_id`) and a `lineage` note.
   Point each language case's `twin` at the copy, copy across with
   `twin_case.py`, rebuild the companion (it then holds the copy) and
   regenerate `results/index.json`.

### 7. Full run and page data

Start only on the owner's word. The plan's reviewer calibration (a native
speaker labels 40 replies per language) has not run; AJ waived it for the
Spanish and Indonesian pilot and full run (2026-11-18 and 2026-11-19).

1. On one day, run the twins that are `2026` members first, then the whole
   companion: production, default profile, 3 trials on both.
   `benchmark_page.py --base` refuses a base newer than the run, and a gap
   in days puts agent changes inside the language gap (`max_days_apart`).

   ```bash
   uv run python - <<'EOF'  # prints the --id flags of the 2026 twins
   import json
   lang = json.load(open("benchmarks/2026-languages.json"))
   en = json.load(open("benchmarks/2026.json"))
   twins = {m["twin_uid"] for m in lang["members"] if m.get("language")}
   voided = {e["uid"] for e in en["errata"]}
   print(" ".join(f"--id {m['id']}" for m in en["members"]
                  if m["uid"] in twins and m["uid"] not in voided))
   EOF
   caffeinate -i uv run gold run --env prod --trials 3 --workers 5 \
     --benchmark benchmarks/2026.json <the --id flags> --build "<label>"
   caffeinate -i uv run gold run --env prod --trials 3 --workers 5 \
     --benchmark benchmarks/2026-languages.json --build "<label>"
   ```

2. Write the page on the machine that ran both runs (it reads their local
   agent artifacts), with the twins run as its base:

   ```bash
   uv run python tools/benchmark_page.py \
     results/benchmark/runs/<companion run>.json \
     --base results/benchmark/runs/<twins run>.json
   ```

3. Commit only on the owner's word: the runs, the page and
   `results/index.json` in one commit (`git add` the runs before
   `tools/build_run_index.py`). The `languages` block stays internal until
   the frontend parses it.

### 8. Standing rules

AJ's rules for every language (2026-11-18 and 2026-11-19):

- Expectations stay in English; both sides of a pair hold the same ones.
  Never edit one side only.
- A reply in the wrong language is never a fail (`reply_language_match` is
  info-only). Language rates sit beside the English headline, never in it.
- An ambiguous number ("1.209") passes on its first reading. `language` is
  part of the uid of a case in another language.
- A "get the data" request owes no total: score the pull and a text check,
  not a figure.
- A dataset choice that offers the right dataset is a fair reply. An area
  clarification on a question that names one area is not.
- "Forest cover loss" with no forest type: the no-layer and the primary
  forest readings both pass. "Deforestation" alone scores no forest filter.
- Both readings of "last N years" pass (for 5 years: 2021 to 2025, or 2020
  to 2024). A KBA and a protected area with the same name both pass.
- A village or sub-district is an expected refusal. An island or another
  place a user cannot select is a text-only row (as `ch-aoi-091`).
- A row whose type or cohort has no `2026` member moves to the nearest that
  has one. No imagery questions: no check scores imagery.
- A frozen `2026` member gets an erratum and a corrected copy, which
  becomes the new twin. It is never edited.
- Run the `2026` twins on the day of the companion run, before it, under
  `caffeinate -i` on a Mac. Commit run records only on the owner's word.

## Rules

**Sampling** (`tools/benchmark_sample.py --version <v>`): ready cases only;
Geospatial and Dataset from **easy + medium only** (the hard cohorts are
extremely hard and would pin the number to the frontier rather than track
improvement); 20 per measured type; stratified by difficulty × cohort where
the set labels difficulty, else cohort; fixed seed. Regenerating a draft is a
deliberate, reviewed act (commit the diff); CI never regenerates. A frozen
manifest is never regenerated.

**Freeze.** Editing a member case mints a new uid, which drops the member
out. `tools/check_benchmark.py` (CI) fails a **frozen** version whose member
uids are missing or not `ready`, or whose frozen facets disagree with the
live case; for a **draft** it warns. So once frozen, member cases are
edit-frozen in practice: change CHALLENGE by adding cases, not by editing
members.

**Errata.** A frozen version is immutable apart from errata. A member found
to be broken (wrong expectation, dead ground truth) is voided by an erratum
entry, never edited. Voided members leave the denominator of every report
of that version, and reports state the count. More than ~5% voided triggers
an early re-version.

**Re-versioning** (~annually): sample a new version, then run the old and new
versions once side by side (the bridge), then retire the old one. Rates are
only comparable within a version.

## Runs

```bash
uv run gold run --env prod --trials 3 --workers 5 \
  --benchmark benchmarks/2026.json --build "<label>"
```

`--benchmark` selects the manifest's active members from its source store,
writes to `results/benchmark/`, and records `benchmark: {version, status,
manifest_sha, members}` on the run. A run is a **trend point** only when
it is **canonical**: prod, default profile (no `ff`), 3 trials, every active
member measured or errored (none missing). `results/index.json` lists
benchmark runs with that flag and the reasons for any failure.

### Rerunning revised members only

After an expectation review revises a few members (new uids, often a new
draft version), rerun just those members and combine them with the earlier
run instead of rerunning the whole set:

```bash
uv run gold run --env prod --trials 3 --benchmark benchmarks/<v>.json \
  --missing-from results/benchmark/runs/<earlier>.json --build "<label>"
uv run python tools/benchmark_page.py results/benchmark/runs/<rerun>.json \
  --base results/benchmark/runs/<earlier>.json
```

`--missing-from` runs the active members the earlier run did not measure
(`--id` names members directly). Both `--missing-from` and `--base` repeat,
so a second round of revisions chains on the first: rerun what none of the
earlier runs measured, then pass every earlier run as a base (the newest
measurement of each member wins). On its own the rerun is not canonical. The
page combines it with the earlier run's results for every other member,
matched by uid, and records both runs under `run.sources` and on each
question (`run_id`). The index then judges the **combination**: canonical
when both runs are prod, default profile and 3 trials and together cover
every active member; the entry names its base in `composed_with`. The
results come from two dates, so agent changes in between show up only in
the rerun members; say so in the rerun's recommendations doc, and prefer a
full run before a freeze.

## Metrics

`tools/challenge_rollup.py --benchmark` computes these in Python. The FE
accuracy-benchmarks page reads them precomputed: `tools/benchmark_page.py`
writes `results/benchmark/pages/<run_id>.json` after each run (the numbers
below plus per-type, per-use-case and per-question detail, including a
summary of what the agent did on each attempt), and `results/index.json`
points each run at its page. The page's headline is the share of questions
right on **every** trial (`every_time`); `majority` is the North Star below.

- **North Star**: majority-verdict complete rate (a question counts when
  the majority of its scored attempts were right, an attempt being right
  when every applicable non-info check passed on it) over active members
  that were measured, with a Wilson 95% interval. AJ switched to this
  attempt majority on 2026-10-28; before, a question counted when each
  check passed in the majority of trials, which let a check scored on one
  attempt fail a question right on 2 of 3, and passed one right on 1 of 3
  whose attempts failed different checks.
- **Consistency**: of complete answers, the share clean on every trial.
- **Availability**: an attempt that got no reply (the stream stalled,
  dropped or failed) counts as a wrong attempt, and the page reports how
  many of all attempts got none. An attempt the harness could not score
  (an AI reviewer or the state fetch failed) is left out; a member with no
  scored attempt is errored, leaves the denominator and is reported
  separately (AJ, 2026-10-27; before then any errored attempt errored the
  member).
- **Per type**: the same rate, and failure modes by primary-failure
  attribution: each failed member goes to its earliest failing dedicated
  stage in `stage_order` (from its per-check majorities, or, when none
  failed, from the checks that failed on its wrong attempts); failures only
  on shared checks are `unattributed`.
  Pass + stages + unattributed = 100% of measured.
- **Failure modes by standard** (page data only, `failure_modes_by_standard`
  on every group): the same breakdown for each accuracy standard the page
  can show. A question is wrong under `every_time` when any trial is wrong,
  under `majority` when its verdict fails (identical to the failure modes
  above), and under `any_time` when no trial is right. A failed verdict
  counts at its primary failure; a passed verdict that was wrong on some
  trials counts at the earliest dedicated stage that failed on any trial
  (`challenge_rollup.failure_stage`). Each question sits at one stage under
  every standard, so a stricter standard only adds questions.
- **Coverage matrix**: type × stage, from `members[].stages`.

### Known limit of 2026-draft

The numeric sets are scored retrieval-first (see `cases/challenge/README.md`,
Batch 2): no expected numbers, no scored explanation judge. Their members
exercise **retrieval only**, so for Quantification, Comparison and Trend the
complete rate means "fetched the right data", and the analysis, explanation
and output columns of the matrix are empty for them. Closing that is the
Phase 2 numeric-fidelity evaluator work, and it must land (and the version be
re-sampled, since new expectations mint new uids) before the `2026` freeze if
the North Star is to mean what its copy says.
