# GOLD v2 case-set improvement plan — target ~95% per-row pass

**Date:** 2026-08-03 · **Author:** case-set review of runs `20260731T120022Z`,
`20260801T062750Z`, `20260801T084050Z`, `20260801T093002Z`, `20260802T055915Z`
· **Scope:** `cases/v2` (114 cases, 105 active) plus the harness defects that
block the case work.

Read alongside `cases/README.md` (the authoring rubric), `docs/CASESET_PLAN.md`
(strategy) and `cases/v2/COVERAGE.md` (what each row carries). This plan does
not restate them; it says what to change and why.

---

## 0. Action index

| action | rows | where |
|---|---|---|
| **REMOVE** | 1-081 (exact duplicate of 1-056 — move its expectations across first) | §7.7 |
| **REWRITE prompt** | 1-002, 1-004, 1-010, 1-015, 1-021, 1-027, 1-034, 1-043, 1-045, 1-053, 1-054, 1-056, 1-079, 1-093, 1-099, 1-101, 1-104 | §7.2, §7.5 |
| **UPDATE expected** | 1-002, 1-009, 1-054, 1-082, 1-083, 1-084, 1-086, 1-089, 1-091, 1-099, 1-103, 1-107, mt-007 | §7.3, §7.5 |
| **KEEP — genuine agent signal, must stay failing** | 1-014, 1-026, 1-030, 1-037, 1-060, 1-061, 1-088, 1-097, 1-103, mt-001 | §7.1, §7.5 |
| **VERIFY before editing** (do not mint numbers) | 1-010, 1-043, 1-054 | §7.4 |
| **UNPARK with rewrite** | 1-011, 1-020, 1-033, 1-041, 1-075 | §7.6 |
| **LEAVE PARKED, record the reason** | 1-028, 1-049, 1-085 | §7.6 |
| **HARNESS fix first** | H1–H8 | §4 |
| **Free `notes` edits** (unhashed, no uid churn) | `env_gated` on 1-096…1-102; stale/wrong notes on 1-013, 1-035, 1-107 | §7.1, §7.5 |

Headline: this plan takes the set from **46% to ~90%** of rows giving a clean
pass, and to **92%** giving a *stable* verdict. Reaching ~95% additionally needs
**one** upstream fix — the chart mis-join bug — because eight rows fail or flap on
genuine agent defects that a case edit must not paper over. See §9.

**§11 proposes a change to the scoring convention itself** — staged, contingent
verdicts, so one root cause is not counted five times. It does *not* raise the
pass rate, but it localises the deficit to a single stage (`scope`, at 84%) and
makes the other four read truthfully at 87–97%.

---

## 1. The baseline, stated honestly

Two numbers, because only one of them is the real problem.

| measure | value |
|---|---|
| majority-of-3 row verdict, latest two runs | **70%** (73/104 and 59/86 non-error) |
| rows clean on **every** valid trial | **46%** (46/99) |

Evidence is pooled **by `uid`**, not by `id`: the 08-01 and 08-02 runs executed
different `caseset_version`s (`d564c1b3b4786bc0` vs `a93cedfc97c98a4d`), so a
trial only counts as evidence for a case if it ran that case's current uid.
Pooling by `id` invents defects that the W2 date scrub already fixed — the
standing `date_extraction` zeros on 1-010/1-012/1-013/1-073 are exactly that
artifact and are **not** live.

**The 24-point gap between those two numbers is the whole story.** Of the
rows that fail or flap:

- **18 rows carry standing failures** — a check that is 0.0 on every trial.
  These are real expectation defects (or real agent bugs).
- **~35 rows only flap** — the same input scores differently across identical
  trials. Nothing is *wrong* with the expectation; the row simply cannot hold a
  verdict.

So the 95% target is a **determinism** programme first and an expectations
programme second. Ranked by rows spoiled:

| check | rows | standing | flapping |
|---|---:|---:|---:|
| chart_produced | 26 | 3 | 23 |
| dataset_id_match | 24 | 3 | 21 |
| scope_match | 23 | 9 | 14 |
| agent_answer | 19 | 5 | 14 |
| data_pull_exists | 15 | 3 | 12 |
| answered_without_data | 15 | 3 | 12 |
| charts_answer | 14 | 5 | 9 |
| pull_source_match | 6 | 3 | 3 |
| aoi_id_match | 6 | 1 | 5 |
| chart_integrity | 5 | 0 | 5 |

Also: **15 cases have no evidence at their current uid** — the 9 parked rows
plus 1-090…1-095, which only ran in 08-02 where they hit the tail of 19
`ReadTimeout`s. Those timeouts are staging infrastructure, not case defects,
and must not be diagnosed as such. Those six rows need a rerun before any
verdict.

### Three framing facts that change how rows must be read

1. **`todo` and `ready` do not park anything.** `--status-exclude` defaults to
   `"not doing"` alone (`src/goldset/cli.py:262`). Every `todo` row — 1-002,
   1-021, 1-027, 1-030, 1-053, 1-062, mt-007 — **gates verdicts today**.
   mt-007's own `status_reason` worries that "as `ready` this judged check would
   fully gate verdicts"; that is already true at `todo`. Any row whose caveat
   depends on not gating needs `not doing`, or a per-case info-only mechanism
   that does not yet exist.
2. **The 08-01 run predates the G4 fix.** `pull_source_match` then read
   `statistics.get("dataset_id") or …`, so registry id **`0` was falsy** and the
   guard abstained; the fix landed after the 09:30 run. Combined with
   `majority()`, one evaluated `0.0` among `None`s decides the row — which
   manufactured 1-088's apparent "standing" failure. Not a case defect.
3. **Ledger `actuals` come from the last trial only**, which is why 1-099's
   recorded widget list is `[]` while other trials produced a map. Diagnose from
   `results/artifacts/<run>/<uid>[_tN].json.gz`, not from `actuals`.

---

## 2. Root cause 1 — the `dataset_choice` cascade (the dominant lever)

The single largest source of flake. Mechanism: the agent asks *"which dataset
should I use?"* instead of analysing. No pull happens, so 5–7 checks fail
together — `data_pull_exists`, `dataset_id_match`, `scope_match`,
`chart_produced`, `agent_answer`, `answered_without_data`, `charts_answer`.
Recorded as `actual_scope: clarify`.

Across all retained agent-state artifacts (1,298 case-trials), **162 nudges are
`dataset_choice`** versus 47 `aoi_choice` and 3 imagery variants. This is the
agent's dominant nondeterministic surface, and it is what the case set is most
exposed to.

Two independent facts, both from the ledger:

**(a) The nudge rate is a build regression.** Measuring `data_pull_exists == 0`
per trial:

| run | agent build | trials | no-data |
|---|---|---:|---:|
| 20260731T120022Z | GNW 2026.7.29.1 | 66 | **1 (1.5%)** |
| 20260801T084050Z (gnw-evals bridge) | staging-20260801 | 66 | 5 (7.6%) |
| 20260801T093002Z | staging-20260801 | 197 | 23 (11.7%) |
| 20260802T055915Z | staging-20260801 | 188 | 20 (10.6%) |

The **bridge** run on the new build reproduces the cascade at 7.6%, which
exonerates the in-repo harness port: this is the agent, not the runner. No
query text changed between those runs. p ≈ 0.003.

**(b) Which rows it lands on is prompt-determined.** Same build, 8 trials/row:

| prompt names the metric… | rows | nudge rate |
|---|---:|---:|
| precisely (1-001, 1-002, 1-008, 1-009, 1-012, 1-016, 1-017, 1-019, 1-022 … 24 rows) | 24 | **2/168 = 1.2%** |
| loosely (this cluster) | 18 | **55/144 = 38%** |

The cleanest contrast sits inside a single dataset. Dataset 2 rows saying
**"natural grassland"** (1-017, 1-019, 1-022, 1-023, 1-024, 1-069) nudge
**0/9 each**. Dataset 2 rows saying bare **"grassland"** — 1-021 (5/8) and
1-079 (2/8). Same dataset, same agent, same runs. The word "natural" is the
entire difference.

**Conclusion: GOLD caught a real regression, and the case set is
over-exposed to it** because 18 rows use loose metric wording where 24 sibling
rows use precise wording. Fix the exposure; keep the sensor.

---

## 3. Root cause 2 — `suggested_datasets` is a dead surface

`agent_state["suggested_datasets"]` is populated in **0 of 1,298** retained
case-trials. Independently verified. Dataset suggestion is real and frequent,
but it is carried entirely by `nudge.type == "dataset_choice"`; the
`pick_aoi`/`pick_dataset` → nudge migration (wri/project-zeno#770) moved it,
and `nudge_evaluator.py`'s docstring already records the cause.

Two consequences, both bad:

1. `suggested_datasets_match` is a **guaranteed-fail** check — 0.00 on all 3
   rows, perfectly stably, on every run since 07-31 (which was both an older
   build and an older harness).
2. `scope: suggest` is a **guaranteed-fail scope**, because
   `classify_scope` (`scope_checks.py:36`) can only emit `suggest` when that
   same dead field is non-empty. All 6 active `dataset-suggestion` rows fail on
   it.

The "suggest" coverage `COVERAGE.md` claims for these rows is therefore
**fictional as evaluated**. What is actually exercised — and passing —
is suggestion via nudge: `expected_text_match` scores 6/6 on 1-082/083/084.

This was flagged as item 4 of `results/recommendations/20260801T093002Z.md` and
never resolved. It is now the second-largest lever.

---

## 4. Harness defects that must land BEFORE the case edits

Sequencing matters. Three of these change what a correctly-authored case is
*allowed* to express; editing prompts first would disambiguate rows that should
have carried alternatives, permanently deleting a routing test.

| # | defect | evidence | rows |
|---|---|---|---|
| **H1** | `parse_expected_number` drops a leading minus. `_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)")` — `chart_numeric.py:66` — has no `-?`, so `-286,994 Mg CO2e` parses as **+286,994**. Verified: the chart's own series aggregate **−286,993.69** is a 0.0001% match, rejected purely on sign, and the reported "closest" is a far-away gross-emissions bar. | reproduced directly; ledger reason string is byte-identical on all 5 trials | 1-055 |
| **H2** | `pull_source_match` never splits `;` alternatives. `guards.py:135` compares `reference == normalize_value(expected)`, so the sanctioned `dataset_id: "0;11"` pattern **can never match**. Verified: expected `0;11` + pull `11` → 0.0; expected `11` + pull `11` → 1.0. | reproduced directly | 1-003, 1-062 (the only two rows using alternatives) |
| **H3** | `evaluate_scope` has no `;`-alternatives support, so a legitimately either-way row cannot be expressed. | `scope_checks.py:44-58` | 1-089 |
| **H4** | `classify_scope` should treat a `dataset_choice` nudge with no pull as `suggest`. This restores a class that exists post-#770 and matches the docstring's stated intent. **Blast radius:** 1-107 is the only currently-green row that breaks (expects `clarify`, nudges `dataset_choice` 6/6) — its `scope` must flip to `suggest` in the same PR. `aoi_choice` rows (1-105, mt-002) are unaffected. | 162 dataset_choice nudges vs 0 populated suggested_datasets | unblocks 6 rows |
| **H5** | **Narrow `charts_answer`**: gate on `evaluate_numeric_support`; make the Haiku appropriateness verdict info-only. The override is currently **asymmetric** (`llm_judges.py:340-358`) — `unsupported` forces 0, but `supported` only annotates the reason and the judge still decides. See §5. | 5 of 6 flappers are rows where the deterministic half passed or abstained | flips exactly 1 row (1-059) |
| **H6** | `chart_candidate_values` never sums **across** measure columns, only within them. A chart splitting one quantity into `high_confidence` + `highest_confidence` (1-002) or gross emissions + gross removals (1-055) cannot support the combined figure. Verified: a two-measure-column chart yields no row totals and no grand total. | reproduced | 1-002, 1-055 |
| **H7** | `dashboard_widgets_valid` returns **0.0 for an empty dashboard even when the case expects no widgets** (`dashboard_evaluator.py:163-171`). 1-096's prompt is only *"Create a dashboard for brazil"* — nothing was requested to be in it — yet an empty dashboard fails, and the row passes only on the trials where the agent volunteers an *unsolicited* text widget. The rule is also internally inconsistent: `evaluate_dashboard_created` treats an unsolicited dashboard as a guardrail violation while this check **rewards** unsolicited widgets. Fix: return `None` when `expected_dashboard_widgets` is empty; keep "empty → 0.0" only where widgets were expected. Note `docs/specs/PR-04-fix-first.md:22` names 1-096 as in-scope for F3, so this is a deliberate reversal needing a spec amendment, not a silent patch. There is currently no way to express "expect zero widgets" (empty string → `None` → no expectation). | 1-096 empty on 4/6 trials; parity report records `A=None B=0.0` | 1-096 |
| **H8** | `web_fallback` false-positives on the product's own tile domain. `_OWN_DOMAINS = ("globalnaturewatch.org",)` (`guards.py:30`) omits `globalforestwatch.org`, which the product itself serves tiles from (visible in dashboard widget configs). 1-095's one failing trial merely appended a `globalforestwatch.org/dashboards/country/FIN/` "see also" link while `dataset_parameter_match`, `dataset_id_match`, `agent_answer`, `charts_answer` and `pull_source_match` all passed and the pull produced the expected 241,368.24 ha exactly. The guard's stated purpose — "the answer came from web knowledge, not the pulled data" — is demonstrably false there. Fix: add `globalforestwatch.org`, or condition G2 on the pull being absent/unused. **Keep `wri.org` firing** — that is precisely 1-030's signal. | 1/6 trials | 1-095 |

H1, H2, H3, H8 are small and unambiguous. H4, H5 and H7 change check semantics —
run the next run with `--note`, per the after-every-run ritual, and amend
`PR-04-fix-first.md` for H7.

---

## 5. Root cause 3 — `charts_answer` stakes verdicts on chart framing

`cases/README.md` already forbids this: *"DON'T stake a verdict on chart
choice — chart type is the agent's most nondeterministic surface."*
`charts_answer` is currently the one gating check that does exactly that.

The aggregate looks acceptable — mean 0.85, ±0.05, inside the ≤0.10 admission
gate from `docs/PLAN.md` §6. But that std is a **blend** of a rock-solid
comparator and a coin-flip aesthetic verdict, and averaging them hides the
defect. Of the 6 rows flapping in the latest run:

| row | numeric support | why it flapped |
|---|---|---|
| 1-001 | `None` (expected `TRUE`) | judge only — no deterministic input exists |
| 1-004 | `None` (expected `Brazil`) | judge only |
| 1-009 | **supported** (1.79%) | judge flip |
| 1-059 | **supported** (0.07%) | judge flip on framing |
| 1-103 | **supported** (0.00%) | judge flip |
| 1-027 | flips with the agent's chart choice | chart-choice staking |

**Five of six are rows where the deterministic half passed or abstained — 100%
of the movement is the judge's opinion.** The deterministic half is by contrast
perfectly stable: 1-002 (0/6), 1-055 (0/5), 1-034 (6/7) fail identically every
time with byte-identical reason strings.

The decisive case is **1-059**. Numeric support passed on both zero trials
(*"closest figure to the expected 25,540,000 is 25,521,080.13, a 0.07%
difference, within the 2% tolerance"*), then the judge failed it anyway —
*"neither chart directly displays the global total … the user would need to
manually sum all regions"* — and passed the third identical trial. The prompt
is unambiguous, the expectation is right, the agent is right, and the chart's
own data contains the answer.

**H5, concretely:**

1. `support == "unsupported"` → **0.0** (unchanged — it catches real defects).
2. `support == "supported"` → **1.0**; judge verdict recorded in the reason,
   non-gating. This symmetrises an override that is currently one-directional.
3. `support is None` → **`null`** (n/a, not failure). A boolean or place-name
   expectation gives the comparator nothing, so the row should not carry a
   gating chart verdict at all. Honours the "every check's spec decides whether
   absence is `null` or `0.0`" agreement, and fixes 1-001/1-004 by construction.
4. Keep the judge verdict in the ledger as a separate info-only field, on the
   same probation path as `answer_traceability` and `class_value_match`.

**The narrowing is provably signal-preserving on this run.** Every row that
fails today for a real reason also fails a deterministic sibling: 1-010
(numeric unsupported at 62.99% *and* `agent_answer` 0/7), 1-043
(`agent_answer` 0/7), 1-031 (`agent_answer` 4/7), 1-002/1-027/1-034/1-055
(numeric unsupported). Exactly **one** row flips fail→pass: 1-059, the false
failure. The wrong-place/wrong-metric surface the judge nominally guards is
already covered deterministically by `aoi_id_match`, `dataset_id_match`,
`date_extraction`, `chart_integrity`, `chart_well_formed` and
`chart_type_match`; the OUTPUT half of its shared tag stays covered by
`chart_produced`/`chart_well_formed`.

### `chart_produced` — the other flake engine

26 rows, 23 of them flapping, ±0.13 std — **the worst std in the suite**,
worse than the ±0.09 that got `answer_traceability` demoted. Two populations:

- **cascade-driven** (no pull → no chart): fixed by §2's work.
- **standalone prose-only answers** (~6 rows: 1-008, 1-012, 1-035, 1-048,
  1-050, 1-069, each flapping 1/6): the agent pulls data, answers correctly,
  and simply omits the chart. No case edit fixes this.

Recommendation #3 of the previous run asked the product to decide whether data
answers must always chart. Until that stance exists, **`chart_produced` cannot
hold a verdict**: demote it to info-only (it keeps reporting), and re-admit it
when the product commits. This is not silencing — it is the same admission
discipline the charter already applies to judged checks.

---

## 6. Rule additions for `cases/README.md`

The authoring rubric has a DO for AOI ambiguity but none for metric ambiguity,
and the metric axis has the identical failure mode. Add:

> - **DO name the metric unambiguously** — the class, the gas basis, the
>   confidence tier. ✔ `"gross greenhouse gas emissions from tree cover loss"`
>   ✘ `"deforestation-related carbon emissions"`. ✔ `"natural grassland"`
>   ✘ `"grassland"`. Evidence: precisely-worded rows nudge on 1.2% of trials,
>   loosely-worded ones on 38%.
> - **DON'T name the dataset by id or product name.** "Using the SBTN Natural
>   Lands Map…" hands over the answer and turns `dataset_id_match` into a
>   string-copy test. The exceptions are the groups whose subject *is* the
>   dataset: `dataset-parameters`, `dataset-suggestion`, `context-layer`,
>   `dashboard`.
> - **DO prefer `;`-alternatives over prompt disambiguation where two datasets
>   are genuinely both right** (the 1-003 precedent). The row still tests
>   "route somewhere defensible and analyse", passes on either choice, and fails
>   only on the nudge. Two families need it: alerts (`0;11`) and emissions
>   (`4;6`).
> - **DO keep a few deliberately loose sentinels** so the next over-nudging
>   regression is still caught (see §8).

### Data-integrity item found en route

`dataset_id: '4'` carries **two different `dataset_name`s** across the set:
`Tree cover loss` (31 cases) and `Forest GHG emissions` (7 cases: 1-040 … 1-046).
`dataset_name` is reference-only and unscored, but it *is* hashed, so correcting
it mints uids — batch it with the §7 edits. Resolve which label is right against
the registry; the ledger suggests one dataset returns both area and emissions
(1-059's answer reports hectares and MgCO2e from a single pull).

Also mechanically confirmed by `tools/audit_cases.py` and a prompt-hygiene
scan: **8 depth violations** (1-005, 1-007, 1-040, 1-042, 1-058, 1-070, 1-071,
1-087 imply ≥2 checks in only 1 bucket), **30 rows carry no `scope`**, and 9
prompts have typos.

**On those 30 rows: adding `scope` is *not* free coverage — do not bundle it.**
An earlier draft of this plan called it "close to free". The stage measurements
in §11 show that is wrong: `scope` is the **least reliable stage in the suite**
(84–85% row pass rate, against 96–97% for `form`), so adding a *gating*
`scope_match` to 30 more rows is about as likely to lower the pass rate as to
raise it. Treat it as a separate, independently measured change, applied only to
rows whose expected scope is unambiguous — an `analyse` row that already carries
an `answer` — so the effect is attributable rather than tangled up with the
rewrites. See the closing note in §12.

---

## 7. Case actions

Legend: **KEEP** = genuine agent signal, do not touch · **REWRITE** = prompt
defect, exact replacement given · **UPDATE** = expectation stale/wrong ·
**REGROUP** = group only (not hashed, no uid churn) · **VERIFY** = blocked on a
confirming pull.

### 7.1 KEEP — genuine agent signal, must stay failing

| row | evidence | file upstream as |
|---|---|---|
| **1-014** | Nudges `aoi_choice` 8/8 on the new build offering *"California, United States / California, Usulután, El Salvador"* — although the prompt says **"in California, USA"**. Pulled data fine on the old build. 7 checks fail, zero flake. Sibling 1-016 (same land-cover-transition phrasing) routes 9/9. | AOI disambiguation regression: a country qualifier in the prompt no longer suppresses the geocoder clarification |
| **1-030** | 9/9 trials, **including the old build**: `actual_scope: none`, `web_fallback: 0.0`, cites `wri.org/insights/...`. Answers "mangroves in Senegal" from the blog skill, never pulls SBTN. | Blog-skill routing preempts data analysis (the G1 reference failure) |
| **1-037** | `aoi_id_match` 3/9. Its enumeration of "Canadian provinces beginning with N" wobbles between 3, 4 and 5 ids across identical trials. A deterministic fact it gets wrong. | AOI enumeration instability on string-predicate parent-child queries |
| **1-103, 1-061, 1-026, 1-060** | `chart_integrity` reports a reproducible mis-join: *"chart 0 (pie): yAxis 'value' is null in 37/40 records"*. Signature of concatenating two differently-shaped record sets and null-padding the axis fields the chart references. `chart_integrity` is the most stable check in the suite (0.98, ±0.01). | **One** upstream bug with the row list: chart data assembled by concat of disjoint schemas |
| **1-018** | Best evidence for the timidity diagnosis: the prompt *already* says "natural grasslands" and the nudge offers *"Global natural/semi-natural grasslands"* — it asks permission to use the dataset it has already identified as correct. | included in the over-nudging filing |
| **1-053, 1-013, 1-035, 1-063, 1-006, 1-031** | Marginal (nudge 1–2/8, at or near the 1.2% floor); all pass on majority-of-3. **Do not fix 1-063's "more more" typo** — `query` is hashed, so a cosmetic edit resets the row's regression history for nothing. | — |

Free, unhashed `notes` corrections (no uid churn): 1-013's `value_2: 924,000 km²`
is wrong by ~2.5× (the agent's 37.4 M ha = 374,000 km²; 924,000 km² is
Nigeria's land area); 1-035's `value_1: 42 hectares` vs the ledger's 48.04;
1-107's `status_reason: "Validator not working"` is stale — `nudge_match` scores
6/6 on the current build.

### 7.2 REWRITE — prompt defects, with exact replacement text

| row | replacement query | expectation changes | calibration evidence |
|---|---|---|---|
| **1-043** | `Which region of New Zealand had the highest total gross greenhouse gas emissions from tree cover loss between 2005 and 2020?` | none yet — see VERIFY below | "region" not "state" (GADM L1 for NZL, and the agent's own nudge says "19 administrative regions"); precise siblings 1-044, 1-046, 1-042 all 0/9 failures |
| **1-004** | `Which country had more area affected by high confidence disturbance alerts in November 2025, Australia or Brazil?` | prefer `dataset_id: "0;11"` + `scope: analyse` (**blocked on H2**) | 1-001, 1-002, 1-009 all route to 11 with 0/9 failures. 1-003 already expects `0;11` for near-identical wording — the team's own position is that both are defensible, so alternatives beat disambiguation here |
| **1-021** | `Which comunidad autónoma of Spain (Iberian peninsula only) had the least natural grassland in 2022?` | none | six "natural grassland" siblings at 0/9; parked 1-020 already uses this wording. Also fixes the "communidad" misspelling |
| **1-015** | `Which Welsh county had the most land in the short vegetation land cover class in 2024?` | none (`class_values: short vegetation=53,498 hectares` corroborated — ledger: Powys 53,497.625 ha) | the recorded nudge is a real two-dataset collision (GLC "short vegetation" vs SBTN "natural short vegetation"); 1-027 says "natural short vegetation" → SBTN 0/9, 1-012 says "cultivated grasslands" → GLC 1/9 |
| **1-045** | `True or False: In the Rep. of Congo, Bouenza generated more gross greenhouse gas emissions from tree cover loss than Cuvette in 2021` | none (`answer: FALSE` solid — Cuvette 2,770,365 vs Bouenza 1,078,505 MgCO2e) | as 1-043 |
| **1-079** | `What was the peak natural grassland extent in Mongolia between 2000 and 2022?` | none (`answer: 80.63 million hectares` holds — ledger peak 80,626,410 ha in 2011) | fixes **two** defects: the bare-"grassland" nudge exposure *and* an open-ended "peak" window pinned to a figure that drifts the moment the dataset extends past 2022 |
| **1-054** | `Based on net forest greenhouse gas flux, are the Canary Islands (Canarias, Spain) a net source or a net sink?` | `text` figure is wrong — see UPDATE | "deforestation related emissions" is what points it at id 4; 1-055 spells out "net greenhouse gas flux" and is 0/9 on both nudge and `dataset_id_match` |
| **1-034** | `In total, how much primary forest loss was recorded in Champoton community land in Mexico, between 2001 and 2024?` | none — keep `context_layer: primary_forest`, `answer: 10,765.60 ha` | **the stale-expected read is wrong here.** On 0801 trial 2 the agent *did* apply the primary-forest layer, and `context_layer_match`, `agent_answer` and `charts_answer` all scored 1.0 on that trial. So 10,765.60 is the correct primary-forest figure; the prompt is simply silent about which quantity it wants. 1-073 names primary forest and never fails `context_layer_match` |
| **1-027** | `Break down the natural land classes by area in the Murgia Alta WDPA in Italy — how much natural short vegetation is there?` | add `class_values: "natural short vegetation=679.17 ha"` (already recorded unhashed in `notes.class_1`) | prose is right 7/7 (679.16–679.28 vs 679.17, max drift 0.016%) but the chart is a pie of Natural 2,123.93 vs Non-natural 123,810.97, so the figure is genuinely absent → 212.72% "difference". 1-026 asks for a *ranking*, which forces the class-level chart, and passes 6/7 at 0.00% |
| **1-002** | `How much of Sao Paulo was impacted by disturbance alerts in the second half of 2024, considering high and highest confidence alerts only?` | `answer:` `1,319,600 hectares` → **`1,299,278 hectares`** | expected 1,319,600 matches nothing. Agent's prose = 1,299,278.14 on 6/6, which is exactly high (1,286,327.39) + highest (12,950.75). Also fixes the "impacted disturbance" typo. The run's own `answer_traceability` line already computes the match at 1.00%. **Alternative** worth considering: keep "high confidence only" and set `answer: 1,286,327` to preserve strict-tier filtering as the capability under test — but that leans on the 2% tolerance to mask a semantic difference, so prefer the explicit prompt and add a dedicated strict-tier row if that capability matters |
| **1-056** | `Which Norwegian county (admin level 1) had the most tree cover in 2000?` | `scope: analyse`, `dataset_id: '7'`, keep the 19 `NOR.*_1` ids, add `answer: "Hedmark"` | GNW's Tree cover dataset is a **year-2000 baseline**, so the prompt asks for a vintage the data lacks; the agent nudges 5/6 ("2000 baseline instead?") and analyses 1/6. Also drops the admin-level ambiguity that made one trial resolve **438 districts** instead of 19 |
| **1-010** | `How much land in the Arawe Key Biodiversity Area, Papua New Guinea was mapped as wetland in 2024? Include all wetland land cover classes.` | `answer` — **VERIFY, do not mint** | expected 16,359 ha is not reproducible: the agent answers **110.10 ha** on 9/9, explicitly *"Wetland – short vegetation"* (one compound sub-class), and the chart's closest figure is 26,663.61 (62.99% off). So 16,359 matches neither the sub-class nor any class in the current data — consistent with the "unverified sheet scratchpads" note in the previous recommendations doc §5 |
| **1-104** | `Show me satellite imagery for the Comunidad de Madrid, Spain for the first two weeks of January 2021` | none (`aoi_ids: ESP.8_1` is already the expectation and the majority resolution) | `aoi_id_match` flaps 2/6 between `ESP.8_1` *Comunidad de Madrid* (similarity 0.50) and `ESP.8.1.3.10_1` *Madrid locality* (similarity **0.38**) — both weak, i.e. the geocoder is guessing. The exact `BRA` vs `BRA.14.8_2` pattern the rules already name. `;`-alternatives cannot express it: `aoi_ids` is split on `;` into a **set** compared by set-equality, which is how 1-056/1-021 list *children*, so a two-level either-or is unexpressable (also 1-020's parked reason). The imagery path itself is healthy — `show_imagery(target_date=2021-01-07, window_days=7)` every trial |
| **1-053** | `True or False: the UK has a lower net forest greenhouse gas flux than the Rep. of Ireland` | none | the abbreviation "net GHG flux" triggers a 1/7 cascade taking 7 checks with it; the passing dataset-6 sibling 1-055 spells it out. Low-risk wording tightening — one review rated this marginal (nudge 1/8, passes on majority-of-3), so it is optional if edit budget is tight, but it is consistent with the new metric-precision rule |
| **1-099** | see §7.5 — the case cannot pass as written; needs the AOI expectation changed too | `aoi_ids: CHE.6.3.1_1` → `CHE.6_1` | four checks perfectly anti-correlated; unpinned imagery date |
| **1-061** | name the admin level: `Which Australian state or territory lost the most forest to settlements and infrastructure?` | none | one 0801 trial resolved **568** GADM-2 ids instead of the 11 level-1 ids (1-056 showed the same drift at 438 ids, fixed by its own rewrite above). Its `chart_integrity` flap is the separate mis-join bug — KEEP that signal |

**Do not** enumerate the five provinces in 1-037's prompt — that deletes the
capability the row exists to test. Keep it failing (§7.1).

### 7.3 UPDATE — stale or wrong expectations

| row | field | old → new | evidence |
|---|---|---|---|
| **1-054** | `text` | `"…net flux of approximately -286,993.68 Mg CO2e"` → `"…approximately -2,793,765 Mg CO2e"` | **Provable authoring error.** −286,993.68 is **1-055's** answer — a different row, `aoi_ids: ESP.14.1_1` (Las Palmas *province*). 1-054 is `ESP.14_1` (the whole archipelago). A province cannot equal the archipelago. Independently verified from artifacts: on every trial where 1-054 analysed, the agent reports **−2,793,765**, reconciling exactly with its own chart (gross emissions 1,580,945 + gross removals −4,374,710). 1-055 reports −286,993.68 on all 11 of its trials. Confirm with one fresh pull, then set |
| **1-009** | `answer` | `4.00%` → **`3.93%`** | self-authored fragility: the agent reports 3.93% every trial (chart candidate 3.92834%), which is a **1.79–1.80%** relative difference against 4.00% — inside the 2% tolerance by 0.2 points. One data refresh tips a passing row to a hard deterministic failure with nothing changed. New margin: 0.04% |
| **1-086** | `scope` | `suggest` → `analyse`; optionally add `answer: "39,957 hectares"`; **REGROUP** to `direct` | never suggests: 6/6 trials it commits dataset 10 and answers with verified numbers (39,957 ha of 1,161,830 ha; traceability 0.00% in both runs). The `suggest` expectation was authored against behaviour that no longer exists, and answering directly is *better*, not a regression |
| **1-103** | `scope` | `suggest` → `analyse`; **REGROUP** to `direct` | 5/5 non-error trials analyse with dataset 9 and hit the expected answer exactly (123.94 M tCO2e, `agent_answer` 1.0 every trial). Scope is its only standing failure. Its `chart_integrity` flap stays — that is the §7.1 mis-join bug and must not be masked |
| **1-082** | surface move | `suggested_datasets: 1;3;8` → `nudge_type: dataset_choice`, `nudge_options: "Global land cover;SBTN;Tree cover loss by dominant driver"` | every trial's option set ⊆ expected — **the expectation was right all along, only the surface moved** |
| **1-084** | surface move | `suggested_datasets: 0;1;2;3;4` → `nudge_options: "DIST-ALERT;Global land cover;grassland;SBTN;Tree cover loss"` | every trial ⊆ expected. Note the token **"grassland"** singular: the agent's actual option is "Global natural/semi-natural grassland extent", so the case-file name "…Grassland**s**" would not substring-match |
| **1-083** | surface move | `suggested_datasets: 4;8;9` → `nudge_options: "Tree cover loss by dominant driver;sLUC;DIST-ALERT"` | dataset 0 appears on 4/6 trials (outside the old set) and 4 is never offered. Including DIST-ALERT is the determinism call; file the underlying quality issue upstream instead. Use the full "…by dominant driver" token — bare "Tree cover loss" would licence datasets 4 and 10 too |
| **1-089** | `scope` | `refuse` → `refuse;clarify` (or `refuse;suggest` under H4) — **blocked on H3** | the case contradicts itself: its `text` explicitly permits *"Refuses … **or** acknowledge and caution that TCL is annual"*, and the agent does both across trials (prose refusal → `none` → pass on 4/6; caution + nudge → `clarify` → fail on 2/6). `expected_text_match` passes **6/6** — the capability (never fabricate monthly TCL data) is intact every trial; only the scope pin flaps. **Do not weaken `text`**, and do not reclassify the agent as wrong: its own case charter licenses the behaviour |
| **1-107** | `scope` | `clarify` → `suggest` — **only if H4 lands, in the same PR** | otherwise H4 converts a green row into a regression-count entry |

### 7.4 VERIFY before editing

Three rows are blocked on one confirming pull each. Do not mint numbers.

- **1-043 `answer`** — even when it analyses, the agent says **West Coast**, not
  Waikato, and the judge reason reveals why: *"the region with the highest
  carbon emissions from **intact forest loss**"* — it is applying an
  `intact_forest` context layer the prompt never requested (same unrequested-
  filter behaviour appears in 1-037 and 1-034). Waikato is plausible as the
  *unfiltered* leader (plantation-heavy), West Coast as the intact-forest
  leader. Run one verification pull for the unfiltered gross-emissions ranking.
  If Waikato confirms, keep it and file the unrequested-context-layer bug.
- **1-010 `answer`** — neither 110.10 (one sub-class) nor 26,663.61
  (unidentified) is defensible as the "all wetland classes" total. One pull.
- **1-054 `text`** — confirm −2,793,765 on a fresh pull before setting.

### 7.5 Capability groups — dashboard, imagery, multilingual, multiturn

**1-099 is the standout: the case cannot pass at all.** Its four flapping
checks are *perfectly anti-correlated* across every completed trial:

| resolved AOI | widgets | aoi + dashboard_aoi | widgets_match + valid |
|---|---|---|---|
| `CHE.6.3.1_1` (municipality, similarity 0.89) | `[]` | **1.0** | **0.0** |
| `CHE.6_1` (canton, similarity 1.0) | `[map]` | **0.0** | **1.0** |

The trial artifact says why in its own words: *"I tried to add a satellite
imagery map, but I couldn't find any clear, cloud-free images for the current
date"*. The city AOI is too small to intersect a cloud-free Sentinel-2 mosaic;
the canton succeeds. Whichever AOI the agent picks, two checks fail. The imagery
date is also unpinned, so the outcome depends on cloud cover on the day the run
happens — the determinism violation the date rules exist to prevent.

- **REWRITE:** `Create a dashboard for the canton of Bern, Switzerland and add a
  satellite imagery map for the first two weeks of July 2025 to it`
- `aoi_ids: CHE.6.3.1_1` → **`CHE.6_1`**; widgets and `dashboard_created`
  unchanged. Confirm the widget appears for that window on the landing run; if
  the July-2025 mosaic is empty, fall back to "the most recent available
  satellite imagery" (routing-only relative date — the tolerated 1-072 pattern).
- **Coverage consequence, must be paid:** 1-099 is the **only** level-3
  (city/municipality) AOI expectation in v2. Re-add city-level resolution on a
  **non-imagery** row — imagery is what couples AOI size to failure — e.g. a
  `direct` tree-cover-loss row phrased "in the municipality of Bern (Berne),
  Switzerland", with `aoi_ids` read off a verification run first.

| row | verdict | detail |
|---|---|---|
| **1-101** | REWRITE | expects `insight;insight;map;text`; the agent produces two insights on 3/6 trials and one on the other 3, same build — nondeterminism, not regression. *"Two insights on deforestation"* never says what the second is, so one insight is a defensible reading. New query: `Create a dashboard for Paraná, Brazil with an insight on annual tree cover loss, a second insight on tree cover loss in primary forests, an explainer text block, and a Tree Cover Loss dataset map layer`. Expectations unchanged. Keeps the duplicate-widget-type capability, makes the count deterministic, and removes the dataset ambiguity driving its 1/6 `dataset_id` flap |
| **1-097** | **KEEP** | `dashboard_widgets_match` 1/6 zero is the agent adding an unsolicited `map` + `text` where one insight was asked for. That is the unsolicited-artifact guardrail doing its job |
| **1-093** | REWRITE | *"Berapa luas hutan yang hilang…"* asks about **forest** loss, but the case pins `context_layer: primary_forest` and `answer: 230.003 hektar`. Total Indonesian TCL 2022 is 885,237.65 ha; primary-forest loss is 230,002.77 ha, and the agent flaps between the two readings. New query: `Berapa luas hutan primer yang hilang di Indonesia pada tahun 2022?` ("hutan primer" = primary forest). Keep both expectations — this preserves the only multilingual × context-layer row rather than flattening it into a fifth plain-TCL row |
| **1-088** | **KEEP** | Not the `;` bug (expected `dataset_id` is the single value `'0'`). On 3/6 trials the agent routes to Integrated alerts (11) instead of DIST-ALERT (0) — the only dataset that can filter by `natural_lands`, as the agent itself states on the correct trials — and then answers *"Cropland, 889,446 ha"*, not a natural ecosystem at all. Five checks correctly fail together. On DIST-ALERT trials the expected 507,742 ha matches to 0.00%. No defensible alternative routing exists, so `;`-alternatives would be **wrong** here. The flagship instance of the §10.1 filing |
| **1-091** | add depth | clean, but the only multilingual row with no `answer` and no `scope`. Add `scope: analyse` and `answer: 289 hectares` (verified 289.11 ha on both completed 08-02 trials) |
| **1-090, 1-092, 1-094, 1-098, 1-100, 1-102** | no action | clean on all completed current-harness trials; expected answers verified to ≤0.001%. 1-100/1-101's `dashboard_widgets_valid` zeros exist **only** in the 07-31 run, which predates PR-04's fix to `_widget_is_valid` (it read `widget["text"]` instead of `config.text`) — already fixed, not case defects. 1-094's `chart_produced` 1/5 zero is the known prose-only flap |
| **mt-001** | **KEEP** | `t1.clarification_requested` and `t2.state_delta` are **one** agent behaviour: on 08-02 t3 the agent skipped the nudge and silently picked `IND.26.26_1` out of four candidates spanning India *and* Angola. T2's `changed: [aoi_ids]` then fails mechanically because T1 had already resolved the AOI. The ambiguity is real; the case is right and the agent is wrong. GOLD counts rows, so the double-hit costs nothing |
| **mt-007** | make T2 deterministic | The targeted behaviour is real: on 08-01 t3 and 08-02 the agent does **not** re-confirm — it hedges about definitions, cites two `wri.org` pages, and offers to re-pull. Judged verdicts run 1.0 / 0.0 / 1.0, std far above the 0.10 its probation note requires, and the variance is **agent-side** (the answers genuinely differ), not judge-side. Since `todo` does not stop it gating, the honest options are `not doing`, or making T2 deterministic — **do the latter**: add `answer: 885,238 hectares` to T2 beside the existing `text`. T1 produces 885,237.65 ha on every trial in both runs, so "the re-stated figure is unchanged" becomes a numeric assertion at the standard 2% tolerance and capitulation fails it deterministically. Separately, reconsider T2's `deltas.retain: [dataset_id]`: on 08-01 t2 the whole T2 state came back empty and `state_delta` scored 0.0 with no error recorded — **a degraded turn should error, not fail a delta** (harness note) |
| **mt-003, mt-004** | no action | `t2.answer_traceability` is info-only and the figures are not wrong. mt-004 t2 bolds a *percentage change* with no chart counterpart; mt-003 t2 bolds a **sum of two confidence tiers** that is no single chart datum — and `charts_data` is **cumulative across turns**, so the T2 check searches T1's July chart. Two check-side limitations to record before `answer_traceability` re-admission: cross-turn chart carryover, and derived/summed claims. Unrelated tidy: mt-003's "Kalimantan, Indonesia" resolves to *Kalimantan Barat*, one of several — name it explicitly before anyone adds an `aoi_ids` pin |
| **mt-002, mt-005, mt-006, mt-008** | no action | clean on every completed trial; the 08-02 blemishes are `ReadTimeout`/`ReadError` |

**Free `env_gated` fix (notes are unhashed — no uid churn).** `docs/PLAN.md:158`
gates dashboards *and* `send_nudge` as absent on prod, and `cases/README.md`
property 4 requires the note in the case. Only **mt-002** and **mt-008** carry
it. Add `notes.env_gated: "dashboards absent on prod as of 2026-07-30"` to all
seven dashboard rows — **1-096, 1-097, 1-098, 1-099, 1-100, 1-101, 1-102** — as
one commit. Two nuances: mt-001 and 1-105 obtain their clarification through the
`aoi_choice` nudge and deserve the mt-002-style note as probable env-gating; and
1-102 expects `dashboard_created: 'FALSE'`, so on prod it passes **vacuously** —
say so in its note, or someone will read a prod pass as evidence the guardrail
works.

### 7.6 Parked rows — verdicts

None appear in any ledger in this repo, so these rest on the case text plus
analogous active-row evidence. Checked first: **no parked row is the sole
carrier of any `dataset_id` or `aoi_source`** (wdpa survives via 1-018/1-027/
1-048; Landmark via 1-003/1-012/1-019/1-034/1-042), so none must be unparked
for coverage reasons.

| row | verdict |
|---|---|
| **1-033** | **Unpark essentially as-is** — the best-value unpark here. A single named WDPA, closed year, annual dataset with dates already scrubbed, `answer: 1,436.02 hectares`, `scope: analyse`. All four properties hold. One 3-trial verification of the figure, then `done`. Record a reason either way |
| **1-041** | Fix the internal contradiction, then unpark. `dataset_id: '4'` with `dataset_name: Forest GHG emissions` is inconsistent — the registry is 4 = Tree cover loss, 6 = net flux; there is no "Forest GHG emissions" id. Emissions figures ride on dataset 4, so keep `'4'` and correct the name to `Tree cover loss` (hashed → new uid). Query and window are already closed and deterministic. Verify the year, then unpark |
| **1-075** | REWRITE — "since 2020" drifts with every data drop. `How much tree cover loss occurred within intact forest landscapes in Sweden between 2020 and 2024?`, keeping `aoi_ids: SWE`, `dataset_id: '4'`, `context_layer: intact_forest`, `scope: analyse`. Re-verify `answer: 3.3 kha` for the closed window and restate as `3,300 hectares` (every other row uses hectares). Add the missing `aoi_source: gadm` |
| **1-020** | REWRITE using the sanctioned children pattern. "Which country in the UK…" with `aoi_ids: GBR` can never match: set-equality cannot express "GBR or its children" and the agent selects the four constituents. Do what 1-056 and 1-021 do — list them: `Which of the four countries of the United Kingdom (England, Northern Ireland, Scotland, Wales) had the least natural grassland in 2022?`, `aoi_ids: GBR.1_1;GBR.2_1;GBR.3_1;GBR.4_1`, `dataset_id: '2'`, `scope: analyse`, plus a verified `answer`. Corroboration for the ids: 1-039 uses English districts under `GBR.1`, 1-015 uses 22 Welsh districts under `GBR.4`. Confirm all four against a run's `actual_id` before activating. Note it says *natural* grassland — the 1-021 lesson applied pre-emptively |
| **1-011** | REWRITE, then re-verify. Two defects: a relative window ("past decade") and an inexpressible AOI — "protected areas in Colorado" is a multi-AOI aggregate the product cannot select, which is why the agent clarifies, and `aoi_source: gadm` contradicts `notes.aoi_type: wdpa`. `cases/README.md:113-128` already publishes the repair. **But do not ship the number unverified**: the parked case says 564,406 ha and the README's repair says 53,498 — they cannot both be right. Alternative if preferred: accept the clarification as correct (`clarification: 'TRUE'`, `scope: clarify`) |
| **1-028** | Leave parked pending one exploratory `--id 1-028` run, then unpark or delete **with the reason written down**. The empty "INVESTIGATE" note is what got it stuck |
| **1-049** | **Leave parked; delete if unreproduced.** `answer: 1.41 hectares` of tree cover *gain* over 2010–2015 for a whole reserve is implausible on its face — likely a unit/scale error in the sheet. Dataset 5 has five active carriers. Record that reason, replacing "INVESTIGATE" |
| **1-085** | Leave parked until the suggestion-surface work lands — unparking a fourth carrier of a guaranteed-fail check today just adds a failure. Then rewrite onto `nudge_type`/`nudge_options` and fix the "wilfires" typo in the same edit |
| **1-081** | **REMOVE — see §7.7** |

### 7.6b `todo` rows needing a decision

- **1-062** — standing `pull_source_match` is exactly the H2 `;` bug
  (`dataset_id: "8;10"` compared as a whole string). Independently, its own
  `status_reason` is right that with `aoi_ids` and `answer` dropped the row no
  longer verifies the Washington-vs-Oregon comparison its group promises.
  Sequence: land H2 → 3-trial run → read the two `actual_id`s and per-state
  figures off the ledger → reinstate `aoi_ids` (both states; set-equality is
  correct here) and `answer` (its `notes` record 62,509 ha vs 143,655 ha but not
  which is which) → `ready`. Until then it gates as a guaranteed failure, so
  prefer `not doing` over `todo` this cycle.
- **1-002, 1-021, 1-027, 1-053** — leave `todo` until their rewrites land, then
  promote. Each is covered in §7.2/§7.3.

### 7.7 REMOVE

Deliberately short. Deleting a row that carries real signal is the worst
outcome available, so the bar is "cannot be made deterministic **and** its
coverage survives elsewhere".

**One outright deletion: 1-081 — an exact duplicate of active row 1-056.**

A duplicate-prompt scan over `cases/v2` found their queries are byte-identical
("Which norwegian state had the most tree cover in 2010?"), with the same
19-county AOI set and the same `dataset_id: '7'`. That is almost certainly why
1-081 was parked in the first place.

The important part is which copy holds the *correct* expectations, and it is the
parked one. **1-081 expects `scope: analyse` and `answer: Hedmark`**; active
1-056 expects `scope: suggest` and has no `answer` — and 1-056's `scope_match` is
a **standing 0/6** precisely because the agent analyses. Two independent reviews
reached `answer: Hedmark` for this prompt from different evidence (1-081's own
expectation, and the one 08-01 trial where 1-056 analysed and reported *"Hedmark,
~1.43 M ha on the 2000 baseline"*).

So: **move 1-081's expectations into 1-056 first** — `scope: analyse`,
`answer: Hedmark`, `notes.value_1: 1.43 million hectares` — apply the §7.2
rewrite (2000 baseline, named admin level), regroup 1-056 out of
`dataset-suggestion`, and only then delete `cases/v2/parent-child/1-081.yaml`.
Deleting first loses the verified answer. Net effect: one duplicate removed, one
standing zero fixed, and Analysis/Output coverage added to a row that has none.

The same scan flagged **1-008 and 1-088** as sharing a query verbatim ("What type
of natural ecosystem in Uganda had the most disturbances in 2025?") while sitting
in different groups with different expectations — 1-008 in `class-comparison`
(no context layer), 1-088 in `context-layer` (`natural_lands`). That is a
defensible pair only if the two genuinely test different things; as written they
are the same prompt scored two ways, and one of them (1-088) is the row where the
agent's routing failure shows up. Keep 1-088; consider re-pointing 1-008 at a
different country so the pair stops sharing a uid lineage in all but name.
- **1-030** — keep running at `todo` with an upstream ticket. It is perfectly
  deterministic (9/9, costs the flakiness metric nothing), but it has *never*
  passed, so it cannot detect a **new** regression — arguably outside GOLD's
  charter. If the team parks it to clean the headline, the PR must say it is
  hiding a 9/9 reproducible routing failure. Coverage if parked: it is the only
  `comparative`+SBTN row and one of four `class_values` rows; `class_values`
  survives via 1-015, 1-029, 1-031, and the SBTN-mangrove class via 1-031's
  `mangroves=15,444 hectares`.
- **1-085** (parked) — keep parked, then probe. It is the most on-charter prompt
  in the group (it explicitly *asks* for suggestions) but has zero trials in
  any run and its expectations sit on the dead surface. One staging probe, then
  rewrite onto `nudge_type`/`nudge_options` (or `text` if the agent answers in
  prose), fixing the "wilfires" typo in the same edit. Don't unpark blind.
- **`suggested_datasets_match`** drops to **0 active users** after the surface
  move. Deliberate and honest — its surface no longer exists in the product.
  The evaluator stays (v1 baseline rows still exercise it) and
  `COVERAGE.md`'s "Known gaps" should record it as dormant-by-design, replacing
  the `nudge_type` entry, which goes from 0 users to 4–5.

---

## 8. The cost that must be paid explicitly: sentinels

If all 18 loosely-worded rows are tightened, the set's only remaining
nudge sensors are the 2 `nudge` rows and the 3 `clarification` rows — and those
test that the agent **does** nudge when it should, not that it **doesn't** when
it shouldn't. The over-nudging regression that this very review discovered would
not be caught next time.

**Nominated sentinels — leave deliberately loose:**

- **1-004** and **1-043**, expressed as `dataset_id: "0;11"` / `"4;6"` with
  `scope: analyse` (needs H2). They pass on any real analysis and fail only on
  a nudge — which is precisely the sensor.
- **1-014** untouched, as the AOI-side sentinel. Already the cleanest signal in
  the set: 8/8, zero flake, worked on the previous build.

---

## 9. Projection and sequencing

Modelled on the uid-correct baseline. A row counts **clean** only when nothing
standing and nothing flapping remains — i.e. a 3-trial run gives the same verdict
every time. Rows are held out as **agent-side** when a case edit must *not* make
them pass.

| after | clean | agent-side | still open |
|---|---:|---:|---:|
| baseline | 46/99 (46%) | 8 | 45 |
| W1 metric-precision rewrites (§2, §7.2) | 63 (64%) | 8 | 28 |
| W2 scope/suggestion taxonomy + H4 (§3, §7.3) | 68 (69%) | 8 | 23 |
| W3 harness H1–H3, H8 | 70 (71%) | 8 | 21 |
| W4 `chart_produced` demoted / product stance settled | 77 (78%) | 8 | 14 |
| W5 `charts_answer` narrowed (H5) | 82 (83%) | 8 | 9 |
| W6 AOI admin-level naming | 84 (85%) | 8 | 7 |
| W7 dashboard rewrites + H7 (§7.5) | 86 (87%) | 8 | 5 |
| W8 multiturn + remaining stale numbers | **89 (90%)** | 8 | 2 |

### The honest answer on ~95%

**Case-set and harness work alone reach ~90%, not 95%.** The gap is not case
defects — it is eight rows of genuine agent misbehaviour that this plan
deliberately refuses to edit away:

| row | agent defect | stable? |
|---|---|---|
| 1-014 | `aoi_choice` nudge despite "California, USA" in the prompt | stable fail |
| 1-030 | answers from web knowledge, never pulls | stable fail |
| **1-103, 1-061, 1-026, 1-060** | **chart data assembled by concat of disjoint schemas** | flapping |
| 1-088 | routes to Integrated alerts instead of DIST-ALERT, answers "Cropland" | flapping |
| 1-037 | AOI enumeration of "provinces beginning with N" wobbles between 3, 4 and 5 | flapping |
| mt-001 | skips the nudge and silently picks one of four Puri candidates | flapping |

Two of these fail *stably*, which costs GOLD nothing: **a stable failure is not a
regression**, it is a documented known-fail that never flips. The other six
**flap**, and flapping is what actually breaks the suite — it manufactures false
regressions and false recoveries run to run.

So there are two different targets, and it matters which one is being asked for:

| target | value after this plan |
|---|---|
| rows giving a **stable verdict** (GOLD's real requirement) | **92%** |
| rows **passing** | **90%** |

**One upstream fix closes most of the remaining gap.** The chart mis-join bug is
a *single* defect affecting four rows (1-103, 1-061, 1-026, 1-060) — fixing it
takes passing rows to ~94% and stable verdicts to ~96%. Add the two AOI/routing
regressions (1-088, 1-037) and the set reaches ~97%, with 1-014 and 1-030 as the
documented residual.

**~95% is therefore reachable, but only as a joint result: this plan plus the
chart mis-join fix.** A plan that hit 95% purely by editing cases would have
achieved it by deleting the four rows that caught a real chart-assembly bug —
exactly the outcome the charter exists to prevent.

Two remaining open rows: **1-062** (needs H2, then its `aoi_ids`/`answer`
reinstated — see §7.6b) and **1-101** (a 1/6 `dataset_id` flap that its rewrite
should remove; re-measure after).

One honest caveat on the rewrites: 1-025 and 1-012 nudge 1/9 despite precise
wording. Prompt tightening moves the per-row nudge rate to roughly the 1.2%
floor, not to zero. At 105 rows with majority-of-3 verdicts that is comfortably
inside the target, but the residual is agent-side and no case edit removes it.

**Order of work:**

1. **Harness first** — H1, H2, H3 (small, unambiguous), then H4 and H5 with
   `--note` on the next run. Doing case edits first would prompt-disambiguate
   rows that should have carried `;`-alternatives, permanently losing a routing
   test.
2. **Verification pulls** for the three §7.4 rows.
3. **One batched case PR** — every expectation edit together, since each mints
   a uid and resets that row's regression history. The PR text says why the
   semantics changed; `tools/check.py --fix` then `uv run pytest`;
   regenerate `COVERAGE.md`. Two documentation edits belong in the same PR:
   - `cases/README.md:105` quotes **1-002's stale figure** (`1,319,600
     hectares`) in the "Good single-turn case" worked example. Updating the case
     without updating the rubric leaves the rubric teaching the wrong number.
   - the §6 rule additions, and the `nudge_type`-for-`suggested_datasets`
     swap in `COVERAGE.md`'s "Known gaps".
4. **Rerun 1-090…1-095** (timeout-only rows) for a verdict at their current uid.
5. **3-trial staging run**, then the full after-run ritual: report, flakiness,
   `diff_runs.py`, and a recommendations doc.

---

## 10. Upstream filings (product/agent, not case defects)

1. **Over-nudging regression** — `dataset_choice` nudge rate went 1.5% → ~10.6%
   between GNW 2026.7.29.1 and staging-20260801, reproduced on the gnw-evals
   bridge so it is not a harness artifact. Evidence: the 18-row list and the
   per-run table in §2. This, not any single wrong answer, is the release risk.
2. **AOI disambiguation regression** (1-014) — a country qualifier in the prompt
   no longer suppresses the geocoder clarification.
3. **Chart data assembled by concat of disjoint schemas** (1-103, 1-061, 1-026,
   1-060) — null-pads the very axis fields the chart references, e.g.
   *"chart 0 (pie): yAxis 'value' is null in 37/40 records"*. **This is the
   highest-value upstream fix for the 95% target**: one bug, four rows, and it is
   the difference between ~90% and ~94% passing (§9). `chart_integrity` is the
   most stable check in the suite (0.98, ±0.01), so its verdict is trustworthy.
4. **Unrequested context-layer filtering** (1-043, 1-037, 1-034) — the agent
   sometimes applies `intact_forest`/`primary_forest` when the prompt didn't
   ask.
5. **Blog-skill routing preempts data analysis** (1-030).
6. **`suggested_datasets` state retirement** — confirm it is permanent
   post-#770; if so the GOLD check is permanently dead on new builds.
7. **Single-option `dataset_choice` nudges** (1-056 options=`["Tree cover"]` on
   5 trials; 1-089 t2 `["Tree cover loss"]`) — a one-option "choice" is a
   confirmation, not a choice.
8. **DIST-ALERT offered for a 2017 query** (1-083, 4/6 trials) — DIST-ALERT has
   no 2017 coverage.
9. **Prose-only answers on chart-implying rows** — the standing question from
   the previous run's recommendation #3. Blocks `chart_produced` re-admission.

---

## 11. Scoring convention — staged, contingent verdicts

**The proposal:** retrieval is a precondition, so when it fails, stop measuring
downstream; the other buckets are only meaningful conditional on retrieval
having been right.

**The diagnosis is correct.** Today `row_verdict` ANDs every applicable check
(`buckets.py:101-112`) and `diff_runs.py` counts regressions **per uid per
check**. One nudge therefore fails 5–7 checks and lights up **all five
buckets** — the bucket table reports "everything broke" when one thing broke.
Measured on the two 3-trial runs, the flat model depresses every downstream
bucket by punishing it for upstream breakage:

| bucket | flat (today) 08-01 → 08-02 | contingent 08-01 → 08-02 |
|---|---|---|
| retrieval | 93% → 93% | 94% → 94% |
| analysis | 93% → 91% | **97% → 96%** |
| explanation | 92% → 93% | **98% → 97%** |
| output | 93% → 92% | **97% → 95%** |
| scope | 85% → 82% | 85% → 82% |

Check-level regressions across that diff fall from **26 to 20** while rows
regressed stays at 14 — i.e. six of today's "regressions" were the same defect
counted again downstream.

### Two corrections to the model

**(a) The primary gate is `scope`, not retrieval.** Measured with a staged
verdict, **`pull` passes 100% of the rows that reach it, in both runs.** It never
fails independently — because when the agent nudges, *that is the scope failure*,
and "no data pulled" is its consequence. Scope is the actual bottleneck. So the
dependency order is:

```
scope → retrieval-fit → { form, value }
```

and `scope` + `data_pull_exists` should collapse into **one** gate rather than
two stages, since they are the same event.

Row-level pass rate per stage, measured only where the stage is reached:

| stage | 08-01 | 08-02 |
|---|---:|---:|
| scope (right kind of work) | **85%** | **84%** |
| pull (any data at all) | 100% | 100% |
| fit (right AOI/dataset/dates/layer) | 87% | 90% |
| form (artifact structure) | 96% | 97% |
| value (figures and prose) | 93% | 89% |

**(b) Guardrails must be exempt from suppression.** This is the one way the
proposal could do real damage, and it shows up on the most important row in the
set. Under naive staging, **1-030** — which answers confidently from the blog
skill with `wri.org` citations and no pull — reports `fail:scope` and
**suppresses `answered_without_data` and `web_fallback`**, the two checks that
exist specifically to catch fabrication (`guards.py:4-8` names 1-030 as their
reference failure). Worse, it becomes *indistinguishable* from 1-014, which also
reports `fail:scope` but merely asked a clarifying question and fabricated
nothing. Collapsing "politely asked" and "confidently made it up" into one
verdict is unacceptable.

So `answered_without_data` and `web_fallback` are **not pipeline stages** — they
are orthogonal safety checks that run unconditionally and can fail a row at any
stage. A `fail:scope` row that also trips a guardrail must be reported as the
more serious event.

### What this does and does not buy

**It does not raise the pass rate.** Staged verdicts on both runs give
**70% and 69% — identical to today.** Staging does not invent passes; it
re-attributes failures. Any hope that a scoring change reaches ~95% on its own
should be dropped.

What it does buy is threefold, and it is worth having anyway:

1. **Honest regression counts.** One root cause reports once. The release
   headline stops multiplying a single nudge into seven regressions.
2. **Diagnosable buckets.** Analysis at 97% rather than 93% is the truthful
   statement about the analysis capability, because the 4-point difference was
   retrieval's fault.
3. **A fair scorecard.** "scope 84%, fit 90%, form 97%, value 89%" is far more
   actionable than "70% pass", and it localises the deficit to **scope** — which
   is precisely what §2's metric-precision rewrites target. Land those and all
   five stages sit at or above ~95%, which is very likely the number being asked
   for.

### Two constraints that must ride along

- **Suppression must never reduce the row-fail count.** `fail:scope` is a fail.
  Report "rows blocked at stage X" as a first-class headline number beside the
  regression count, or a retrieval collapse would show *fewer* recorded failures
  as the agent got worse.
- **Stage rates are diagnostics, never the gate.** Denominators move run to run
  (scope measured on 80 rows then 67; pull on 59 then 51), so comparing 85% to
  84% compares different populations. Keep the per-uid-per-check diff as the
  release gate — it is population-independent, which is exactly why
  `docs/PLAN.md` §1 makes a regression count the headline and warns that
  "percentages reward adding easy checks". This proposal changes §4.1's binary
  row verdict; it must not change §1.

### Recommended shape

```
verdict        pass | fail:<stage> | error | uncovered      (fail is still fail)
stages         scope+pull (one gate) → fit → { form, value }
guardrails     answered_without_data, web_fallback — unconditional, never suppressed
suppressed     recorded explicitly as `suppressed_by: <check>`, never a bare null,
               so "not applicable to this case" stays distinguishable from
               "not measured because an upstream stage failed"
headline       N regressions (root-cause deduped) + M rows blocked at each stage
```

The `suppressed_by` marker matters: `docs/PLAN.md` §4.2 requires that an
unmeasured bucket be visibly different from a passing one, and a bare `null`
would quietly erase that distinction.

**Sequencing note:** this is a scoring change, so it needs `--note` on the next
run and it re-bases every historical comparison. Land it *after* the harness
fixes in §4 but *before* the batched case PR, so the case work is measured under
the convention it will live in.

---

## 12. Implementation runbook

The governing constraint is **uid churn**: every prompt or expectation edit mints
a new uid and resets that row's regression history. So the goal is *exactly one
discontinuity* in the ledger — reviewable in small pieces, but landed as a single
train with one before/after run bracketing it.

`tools/diff_runs.py` compares over the **intersection of uids**, so churn is
reported and never counted as a regression — the CI regression gate will not
trip on the rewrites. `--fail-on-coverage-loss` is off by default, which matters
because the suggestion-surface move deliberately takes
`suggested_datasets_match` from evaluated to not-evaluated on three rows.

### Phase 0 — notes only (zero risk, no uid churn, no run needed)

`notes:` is unhashed, so this cannot change `caseset_version` — which is also how
you verify it: `tools/check.py` must report the **same** `a93cedfc97c98a4d`
afterwards.

- `env_gated` on 1-096, 1-097, 1-098, 1-099, 1-100, 1-101, 1-102 (+ the
  1-102-passes-vacuously-on-prod caveat); probable env-gating note on mt-001 and
  1-105.
- Correct 1-013's `value_2` (924,000 km² → ~374,000 km²) and 1-035's `value_1`
  (42 → 48.04 hectares).
- Clear 1-107's stale `status_reason: "Validator not working"`.
- Record real reasons on 1-028, 1-049, 1-085, replacing "INVESTIGATE".

### Phase 1 — harness, as two PRs

The eight numbered defects from §4 split into two PRs by *risk*, not by file:

| PR | contains (§4 numbers) | why grouped | needs `--note`? |
|---|---|---|---|
| **PR-Ha** "corrective" | **H1** sign bug · **H2** `;` in `pull_source_match` · **H3** `;` in `evaluate_scope` · **H8** own-domains | each can only turn a *false* failure into a pass — no case coordination, no judgement calls | no |
| **PR-Hb** "semantics" | **H4** `classify_scope` · **H5** `charts_answer` narrowing · **H6** cross-column chart candidates · **H7** `dashboard_widgets_valid` | each deliberately changes what a check *means*, so it re-bases comparisons | **yes** |

**Decision 2026-08-03: H6 is IN**, in PR-Hb. Consequence for 1-002, resolved
here so C3 does not churn its uid twice — with cross-column candidates available
the chart's high + highest sum (1,299,278.14) becomes comparable against the
existing `answer` of 1,319,600, a **1.54% difference that is inside the 2%
tolerance**. So 1-002 passes on the merits with **no prompt rewrite at all** —
drop the §7.2 rewrite for that row, and with it the cosmetic typo fix (`query` is
hashed; the 1-063 precedent says don't churn a uid for a typo).

But 1.54% of a 2% tolerance is exactly the self-authored fragility flagged on
1-009: one data refresh tips it to a hard failure with nothing changed. So keep
the **expectation** edit and drop the prompt edit:

- 1-002 `answer:` `1,319,600 hectares` → **`1,299,278 hectares`** (margin ~0.00%)
- 1-002 `query:` **unchanged**

Recorded consequence: pinning the combined figure against a prompt that says
"high confidence alerts only" encodes "high confidence" as meaning *at least*
high, i.e. including the `highest` tier. That is defensible and is what the agent
does on 6/6 trials, but it is a semantic decision — §10 carries it as an upstream
clarification rather than a case defect.

**PR-Ha — corrective bugs.** Write the unit test first in each case; H1 and H2
both have exact reproductions in §4.

**PR-Hb — deliberate semantics changes.**
- **H4** (`classify_scope`: `dataset_choice` + no pull → `suggest`) **must ship
  with 1-107's `scope: clarify → suggest`** in the same PR, or it converts a
  green row into a regression.
- **H5** (`charts_answer` narrowed; judge verdict retained as a new info-only
  field).
- **H7** (`dashboard_widgets_valid` → `None` when no widgets were expected) plus
  the amendment to `docs/specs/PR-04-fix-first.md:22`, since this reverses a
  documented F3 decision.

**H6 verified against real artifacts (2026-08-03).** The worry with adding
candidates is permissiveness — a wider candidate set makes a false "supported"
likelier, which matters more now that H5 makes the comparator the sole gate. So
numeric support was recomputed over every stored chart artifact, with and without
H6:

| row | without H6 | with H6 | |
|---|---|---|---|
| 1-002 | supported on **3/15** trials | **15/15** | fixed *and* made deterministic |
| 1-055 | 7/8 | 8/8 | H1 did most of it; H6 closed the last trial |
| 1-027, 1-034, 1-010, 1-059, 1-009, 1-103 | — | **identical** | **no false supported introduced** |

So H6 fixes exactly the two rows it was designed for and moves nothing else.
Note 1-002 becomes *stable* on its **original** expected value; the re-pin above
is purely to move the margin off 1.54% of a 2% tolerance.

### Phase 2 — SKIPPED (decided 2026-08-03)

`20260802T055915Z` (3 trials) is the baseline; the end-of-work validation run
compares against it directly. Two consequences accepted deliberately:

1. **Harness and case effects will be mixed** in that final diff, since PR-Ha/Hb
   change scores on unchanged uids. The recommendations doc must say so rather
   than attribute everything to the case work.
2. **1-090…1-095 have no baseline** at their current uid (they only ever hit the
   `ReadTimeout` tail), so they will appear as coverage gained rather than as
   pass/fail movement.

The validation run must be **3 trials** to be comparable with the baseline.

### Phase 3 — verification pulls — DONE 2026-08-03

Run `20260803T195628Z_staging` (3 trials, post-PR-Ha/Hb harness, `--note` marks
it as a verification pull, not a baseline).

**1-054 — CONFIRMED.** The agent reports **−2,793,765 MgCO₂e** and calls the
archipelago a net carbon sink. So `text` becomes *"…approximately -2,793,765 Mg
CO2e"*, and the authoring error is proven: −286,993.68 is 1-055's Las Palmas
*province* figure. (Also a live demonstration of H5: `charts_answer` now reads
*"no numeric claim to check deterministically; not scored"* because the expected
answer is "Sink", where before it carried a judge-only verdict.)

**1-010 — RESOLVED, and the plan's proposed rewrite is withdrawn.** The chart
lists every land-cover class in the Arawe KBA:

| class | hectares |
|---|---|
| Tree cover | 86,403.67 |
| Bare and sparse vegetation | 26,663.61 |
| Built-up | 1,176.05 |
| Water | 480.32 |
| Short vegetation | 169.42 |
| **Wetland – short vegetation** | **110.10** |
| Agriculture | 4.28 |

Total ≈ 115,007 ha, matching the agent's own stated KBA area. **There is exactly
one wetland class**, so "all wetland classes" = 110.10 ha and the prompt was never
ambiguous — the agent has answered it correctly on 12/12 trials. The expected
`16,359 hectares` matches no class, no total, and no chart figure: it is simply
wrong, consistent with the "unverified sheet scratchpads" note in
`results/recommendations/20260801T093002Z.md` §5.

So: **`answer` → `110.10 hectares`, `query` unchanged**, and add
`class_values: "wetland – short vegetation=110.10 hectares"` — a verified figure
for the Analysis bucket, which is what recommendation item 5 asked for. Correct
`notes.value_2` (currently the same wrong 16,359) while there.

**1-043 — still blocked.** It nudged again (`actual_scope: suggest` — H4 working),
offering "Tree cover loss (Annual Emissions)" against net flux, so no pull
happened and Waikato is still unverified. The rewrite has to land *first*, then
the answer gets verified against a run that actually analyses. Sequence: apply the
C1 prompt rewrite keeping `answer: Waikato` provisionally, re-run, and correct the
answer if the agent names a different region.

- **Parked-row probes** (1-033, 1-041, 1-028) remain outstanding — Phase 6.

### Phase 4 — the case train (four stacked PRs, one merge)

Split by theme so each is reviewable; merge as one train so there is one
discontinuity.

| PR | contents | depends on |
|---|---|---|
| **C1** | metric-precision rewrites: 1-004, 1-005, 1-007, 1-015, 1-021, 1-034, 1-040, 1-043, 1-045, 1-053, 1-054, 1-063, 1-079, 1-093 | PR-Ha (H2, H3 — the `;` sentinels) |
| **C2** | scope/suggestion surface move: 1-056 (+1-081 deletion), 1-082, 1-083, 1-084, 1-086, 1-089, 1-103 | PR-Ha (H3), PR-Hb (H4) |
| **C3** | stale numbers + AOI admin levels: 1-002, 1-009, 1-010, 1-027, 1-061, 1-091, 1-104, mt-007 | H6 decision (1-002) |
| **C4** | dashboard + imagery: 1-096, 1-099, 1-100, 1-101 | PR-Hb (H7) |

Merge per the stacked-PR protocol: bottom-up with `gh pr merge N --merge`, then
`gh pr edit N+1 --base main` **before** touching any branch, and delete head
branches only once the whole train is in. Deleting a branch that is still the
base of an open PR closes that PR unrecoverably.

Docs ride along in the train: the §6 rule additions to `cases/README.md`, the
1-002 figure in its worked example (line 105), and `COVERAGE.md` regenerated —
CI gates its freshness with `coverage_doc.py --check`.

### Phase 5 — validation run and the after-run ritual

3 trials, `--note` describing the semantics changes, then the full ritual from
`CLAUDE.md`: `render_html.py`, `flakiness.py --per-case`, `diff_runs.py` against
the **Phase-2 baseline**, and a `results/recommendations/<run_id>.md`. Commit the
ledger, report and recommendation together.

Expect the diff to show many **recoveries** and near-zero regressions; the
rewritten rows will appear as churn rather than as either.

### Phase 6 — second wave

- Unpark with rewrites: 1-033, 1-041, 1-075, 1-020, 1-011 (each needs its number
  verified first).
- 1-062: reinstate `aoi_ids` and `answer` off the Phase-5 ledger, then `ready`.
- **Promote the audit to a gate**: `tools/audit_cases.py --strict` in CI. The
  workflow comment already says the step is "report-only until W1-W4 land" —
  flipping it is the completion criterion for this programme.
- Re-add city-level AOI coverage on a non-imagery row (the 1-099 debt, §7.5).

### Per-PR checklist — the things a batch edit loses

- [ ] `uv run python tools/check.py --fix`, then `uv run pytest`
- [ ] `uv run python tools/coverage_doc.py` regenerated
- [ ] **sentinels intact**: 1-004 and 1-043 keep `;`-alternatives rather than a
      disambiguated prompt; 1-014 untouched (§8)
- [ ] **the 10 KEEP rows are not touched**: 1-014, 1-026, 1-030, 1-037, 1-060,
      1-061 (prompt only), 1-088, 1-097, 1-103, mt-001. A reviewer should check
      this explicitly — a PR that quietly makes these pass has defeated the suite
- [ ] no number minted without a verification pull behind it
- [ ] PR text says *why* the semantics changed (uid churn is the record)

### One recommendation against a tempting change

§6 notes that **30 rows carry no `scope`** and calls it near-free coverage.
**Do not bundle that into this train.** `scope` is the *least* reliable stage in
the suite (84–85%, §11), so adding a gating `scope_match` to 30 more rows is as
likely to lower the pass rate as to raise it. Add it later, only on rows whose
expected scope is unambiguous (an `analyse` row that already carries an
`answer`), and measure it as its own change so the effect is attributable.

---

## 13. Run convention — trials and workers

### Measured: what one trial costs

Both recent runs stored per-trial checks, so the noise is measurable rather than
arguable. All figures over the **same 59 shared uids** with clean data in both
runs:

| comparison | regressions reported |
|---|---|
| cross-run, **majority-of-3 vs majority-of-3** | **15** ← the real signal |
| cross-run, 1 trial vs 1 trial (9 pairings) | 13–26 (mean 19.3) |
| **same run, trial vs trial — nothing changed at all** | **18–29** |

The last row is the decisive one. Comparing two trials of the *same run* — same
build, same case set, same prompts, nothing changed — reports **18 to 29
"regressions"**. That is the pure nondeterminism floor, and it is **larger than
the 15-regression real signal** between two genuinely different runs.

So a 1-trial release gate cannot distinguish a build that broke nothing from one
that broke twenty things, and `diff_runs.py --fail-on-regression` in CI would
fail on essentially every run. This is also the standing project decision —
`CLAUDE.md`: *"Official runs are 3 trials, always"*, and
`results/recommendations/20260801T093002Z.md` item 6 — so lowering it changes
what the release gate means, not just how long a run takes.

### Decided 2026-08-03: two tiers, with 1/10 as the flat default

`--trials 1 --workers 10` is now the **CLI default** (`cli.py`), and runs record
`workers` + `trial_timeout` so the concurrency risk below is observable.

| purpose | command | committed? | feeds the gate? |
|---|---|---|---|
| **iteration / smoke** (default) — "did my rewrite stop the nudge on 1-021?" | `gold run --env staging` | no | no |
| **official / gate** — baseline, validation, release | `gold run --env staging --trials 3` | yes | yes |

The fast tier is genuinely valuable during Phase 4: most case edits are checking
a single behavioural question on a handful of rows, and 1 trial at 10 workers
answers that in minutes.

**The constraint that survives:** anything producing a regression count stays at
3 trials, and **both sides of a comparison must carry the same trial count**. The
end-of-work validation run must therefore be 3 trials, because the baseline it is
being compared against (`20260802T055915Z`) is a 3-trial run — a 1-trial-vs-
3-trial diff is noisier than either.

### The timeouts are a different problem, and more workers may worsen them

The 19 errors in the 08-02 run were **not** scattered per-row failures. They sit
at **positions 78–103 of 105** — one contiguous block from roughly three-quarters
through the run to the end. That is a mid-run systemic degradation that started
and never recovered, not a per-request property.

Given that shape, raising `--workers` from 5 to 10 doubles sustained concurrency
against whatever fell over, so it is as likely to *cause* the tail block as to
avoid it. Cutting trials 3→1 shortens the run and so reduces exposure — but that
treats the symptom by making the measurement unusable.

Latency context: median 37s, p90 113s, max 485s, against a 240s per-read httpx
timeout (`runner/api.py:110`) and a 900s per-trial wall clock.

**We cannot currently attribute it, because `workers` is not recorded in the
ledger** — the run JSON carries `run_id`, `started`, `environment`, `build`,
`ff`, `harness`, `judge_model`, `num_trials`, `caseset_version` and no
concurrency at all. Three cheap harness items, in priority order:

1. **Record `workers` and `trial_timeout` in the ledger.** One-line change, and
   without it every future timeout post-mortem is guesswork.
2. **Make a tail failure survivable** — retry-on-timeout, or checkpoint/resume so
   a degradation at row 78 does not void 26 rows of a 3-trial run.
3. **Revisit the 240s per-read timeout** against the observed p90 of 113s and max
   of 485s.

### Consequence for Phase 2

The existing 08-02 run is a **partial** baseline: 19 rows errored and 6 rows
(1-090…1-095) have no evidence at their current uid. More importantly, PR-Hb
changes scores on *unchanged* uids by design, so once the harness lands, 08-02 is
no longer like-for-like and a Phase-5 diff against it would conflate harness
gains with case gains.

Two ways to handle it:

- **Preferred:** one 3-trial run after PR-Ha/PR-Hb, before the case train. Keeps
  attribution clean and picks up the six missing rows.
- **Cheaper:** diff against 08-02 anyway and accept that harness and case effects
  are mixed, stating so in the recommendations doc.

**A note on replay, since it looks like a free alternative and is not.**
Re-scoring stored artifacts under the new evaluators would give a harness-only
baseline with no staging calls at all — but it does not work today:
`runner/artifacts.py` writes a *derived diagnostic summary* (`statistics_last`,
decoded codeact, extracted tool calls), not the raw `agent_state` the evaluators
consume, and the artifact directories are gitignored. Making artifacts
replayable — persist the raw agent state, add a `gold rescore <run>` path — would
let every future harness change be validated for free and deterministically. It
is the highest-leverage harness investment on this list, but it is a build, not a
shortcut available this week.
