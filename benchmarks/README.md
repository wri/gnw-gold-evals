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

### Current versions

| Version | Status | Members | Notes |
|---|---|---|---|
| `2026-draft-5` | draft | 269 (as `2026-draft-4`) | `2026-draft-4` after the 2026-10-27 review, judged by "could this answer mislead the user?" (`cases/challenge/README.md`): figure formulas (`figure`, `figure_claim`) on about 170 members, checked against the table each attempt pulls, and 209 revised expectations; `ch-quant-180` and `ch-port-017` moved off Ghana (seed `seeds/benchmark-v2026-bef-2026-10-27.csv`) |
| `2026-draft-4` | retired | 269 (as `2026-draft-3`) | `2026-draft-3` with 26 expectations revised after its first run (`cases/challenge/README.md`, expectation review 2026-10-24): many-area rows reworded to the real `pick_aoi` limits or moved to answer-with-data, either/or rows without dataset checks, defensible alternative datasets and AOIs (two texts reworded again after the first rerun, so draft-4 was rebuilt in place), and on 2026-10-26 seventeen members that asked back gained `accept_nudge_offering` or `accept_aoi_nudge_offering`, three why-questions gained `accept_blog_sources`, two now require data, and the eight Ghana questions moved to Côte d'Ivoire while PZB-1408 is open (seed `seeds/benchmark-v2026-bef-2026-10-26.csv`; rebuilt in place each time); of the 139 cases drafted on 2026-10-23, 26 were revised from run evidence and 113 are unchanged, and none is human-reviewed yet; replaced by `2026-draft-5` on 2026-10-27; keeps its 23 to 26 Oct runs as history |
| `2026-draft-3` | retired | 269 (quantification 84, comparison 57, monitoring 41, causal 31, trend 23, geospatial 9, refusal 9, portfolio 9, dataset 6) | curated from the v2026 BEF sheet of 2026-10-22 (`seeds/benchmark-v2026-bef-2026-10-22.csv`, 299 rows); members carry priority use cases UC1–UC6; 30 rows that need a seeded test account are excluded; replaced by `2026-draft-4` on 2026-10-24; keeps its 23 Oct run as history |
| `2026-draft-2` | retired | 199 (quantification 45, comparison 32, trend 32, monitoring 29, causal 24, geospatial 15, refusal 15, dataset 7) | curated from the proposed v2026 set (`seeds/benchmark-v2026-proposed.csv`); members carry JTBD jobs, impact pathways and user groups; replaced by `2026-draft-3` on 2026-10-23; keeps its 1 Oct run as history |
| `2026-draft` | retired | 100 (20 each: geospatial, dataset, quantification, comparison, trend) | sampled 2026-09-29; replaced by `2026-draft-2`; keeps its 29 Sep run as history |
| `2026` | not yet frozen | | freeze planned November 2026, from `2026-draft-5` once the drafted expectations are reviewed |

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
  --benchmark benchmarks/2026-draft-5.json --build "<label>"
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
  every applicable non-info check passed in the majority of trials) over
  active members that were measured, with a Wilson 95% interval.
- **Consistency**: of complete answers, the share clean on every trial.
- **Availability**: errored members leave the denominator and are reported
  separately.
- **Per type**: the same rate, and failure modes by primary-failure
  attribution: each failed member goes to its earliest failing dedicated
  stage in `stage_order`; failures only on shared checks are `unattributed`.
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
