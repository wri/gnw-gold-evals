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
| `2026-draft-2` | draft | 199 (quantification 45, comparison 32, trend 32, monitoring 29, causal 24, geospatial 15, refusal 15, dataset 7) | curated from the proposed v2026 set (`seeds/benchmark-v2026-proposed.csv`, built by `tools/benchmark_from_sheet.py`); members carry JTBD jobs, impact pathways and user groups; 62 new cases have drafted, unreviewed expectations |
| `2026-draft` | retired | 100 (20 each: geospatial, dataset, quantification, comparison, trend) | sampled 2026-09-29; replaced by `2026-draft-2`; keeps its 29 Sep run as history |
| `2026` | not yet frozen | | freeze planned November 2026, from `2026-draft-2` once the drafted expectations are reviewed |

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
  --benchmark benchmarks/2026-draft.json --build "<label>"
```

`--benchmark` selects the manifest's active members from its source store,
writes to `results/benchmark/`, and records `benchmark: {version, status,
manifest_sha, members}` on the run. A run is a **trend point** only when
it is **canonical**: prod, default profile (no `ff`), 3 trials, every active
member measured or errored (none missing). `results/index.json` lists
benchmark runs with that flag and the reasons for any failure.

## Metrics (computed by consumers for now)

The FE `/evals` page computes these from the manifest plus runs; a
precomputed scorecard will follow once the outputs settle.
`tools/challenge_rollup.py --benchmark` computes the same numbers in Python.

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
