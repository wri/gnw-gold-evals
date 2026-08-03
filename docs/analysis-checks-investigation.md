# Do the Analysis-bucket chart checks survive aggregated data?

**Question (2026-08-04):** does `chart_integrity` fail to work when the chart
contains data that has been summed or aggregated?

**Answer: `chart_integrity` is sound — the hypothesis is refuted for it. But it is
correct for its neighbour `class_value_match`, where aggregation defeats the check
in *both* directions.** Both live in
`src/goldset/evaluators/analysis_checks.py`.

Evidence base: every retained chart artifact in `results/artifacts/` — **1,317
artifacts, 1,888 charts, 3,641 axis references** across nine runs.

---

## 1. `chart_integrity` — sound, with a narrow scope worth knowing

What it does (`analysis_checks.py:121-155`): for each chart, for each of `xAxis`
and `yAxis`, it counts records where the referenced field is **present but
`None`**, and fails if any are. It was built for run-6's 1-060, which zipped a
state ranking and a driver breakdown into one array and null-padded 3 of 10
records in the pie's own axis fields, after which the prose quoted the wrong
figure.

Three ways aggregation could have broken it, all tested and all negative:

| hypothesised failure | occurrences in 3,641 axis refs |
|---|---|
| Axis field **absent from every record** (an aggregation dropped the column) — `field in record` guards absence, so the check would pass a chart that cannot render | **0** |
| A legitimate **total/summary row** carrying a null axis label, reported as a mis-join | **0** |
| `data` shaped as a dict, a scalar, or a list of non-dicts — all silently skipped by the `isinstance(data, list)` guard | **0** (all 1,888 charts are lists of dicts, and all declare axes) |

All **48** null-axis findings in the corpus are genuine mis-joins, and several are
unmistakable — one record reads
`{"chart1_region": null, "chart1_emissions": null, "chart2_year": 2019, …}`, i.e.
two charts' record sets concatenated with their own column prefixes intact.

**What it does *not* do**, which is the fair version of the concern: it never
validates that aggregated numbers are self-consistent. A chart whose "total" row
disagrees with the sum of its parts passes, because every axis field is non-null.
That is a scope limitation, not a defect — arithmetic consistency would be a new
check with its own spec decision.

**Recommendation: no change.** Keep the two absence guards documented as
deliberate (a missing column and a non-list payload both mean "nothing to judge"),
because they *look* like bugs to the next reader and the corpus says they have
never fired.

---

## 2. `class_value_match` — confirmed broken by aggregation, in both directions

The check (`analysis_checks.py:65-117`) exists to catch "a wrong per-class
sub-total hiding under a correct total". Its mechanism: find records where **any
string value contains the class name** (case-insensitive substring), collect
**every numeric value** from those records, and compare the one **closest** to the
expected figure.

Both halves of that mechanism are defeated by aggregate columns.

### 2a. False pass — an aggregate column can satisfy the expectation

Because it takes the closest of *all* numerics in a matching record, an unrelated
aggregate that happens to sit near the target satisfies the check. Reproduced:

```python
{"class": "mangroves", "area_ha": 9999.0, "total_area_ha": 15444.0, "share_pct": 1.7}
# expected: mangroves=15,444 hectares
# -> class_value_match 1.0, "mangroves: closest 15,444.00 (0.00%)"
```

The per-class area is **9,999** — wrong by a third — and the check passes at
"0.00%" by matching the `total_area_ha` column. This is precisely the failure the
check was written to prevent, and an aggregate column in the same record is enough
to defeat it.

### 2b. False fail — an aggregated-away class hard-fails instead of abstaining

When aggregation means per-class records no longer exist, there is no matching
record and the check returns **`0.0`, not `null`**. Reproduced on 1-015's real
shape (its rewritten prompt asks which *county* leads, so the chart is per-county):

```python
[{"county": "Powys", "area_ha": 53497.6}, {"county": "Gwynedd", "area_ha": 41000.0}]
# expected: short vegetation=53,498 hectares
# -> class_value_match 0.0, "short vegetation: no matching record"
```

The figure is right there — 53,497.6, a 0.00% match — but under a `county` key
rather than a class name. Likewise `records == []` returns `0.0` with "no data
records to check classes against" (`analysis_checks.py:82-86`), so a row whose
pull never happened fails the *class* check as well as the pull check.

### 2c. The damning statistic

Across **every committed run**, `class_value_match` has produced 7 failures:

| failure mode | count |
|---|---|
| "no matching record" (class aggregated away / keyed differently) | 4 |
| "no data records" (no pull happened — 1-030) | 3 |
| **wrong per-class number** | **0** |

**It has never once caught the failure it was built to catch.** Every failure it
has ever produced is structural — "I could not find the class" — on rows
1-015, 1-029, 1-030 and 1-031. That, not the flakiness alone, is why its mean sits
at 0.44 and why it is info-only.

---

## 3. Fix plan for `class_value_match`

Ordered by value. Each is small; the first two are the substance.

**F1 — Match the class in a *label* field, not in any string value.**
Restrict the record match to keys that look like labels (`name`, `class`,
`*_class`, `category`, `type`, `label`, `driver`, `land_cover*`, or the chart's own
declared `xAxis`), and take the measure from the chart's declared `yAxis` when
present, falling back to the single numeric field. This kills 2a: a `total_area_ha`
column is no longer a candidate for a per-class figure. Prefer the chart's
declared axes over guessing — `chart_integrity` already reads them, so the
convention is established.

**F2 — Decide deliberately between `null` and `0.0` for a missing class**, per the
`docs/PLAN.md` §6 rule that every check states what an absence means. Proposal:
- **no data records at all** → `null`. The pull checks already fail that row; this
  check has nothing to measure and should not double-count. (Today: `0.0`.)
- **records exist but no label field mentions the class** → `null` *with* the
  reason retained, because the chart is answering a differently-shaped question
  and the expectation is unsatisfiable rather than violated. (Today: `0.0`.)
- **label matched, number outside tolerance** → `0.0`. This is the real signal and
  the only case that should fail.

That change alone converts 7 of 7 historical failures from verdicts into
abstentions, which is the honest reading: none of them was a wrong number.

**F3 — Drop `class_values` from 1-015.** After its W1 rewrite the row asks which
county leads, so a per-class expectation cannot be satisfied by its chart. Leaving
it is a permanently unsatisfiable expectation, which F2 would silently mask.

**F4 — Re-verify the remaining `class_values` rows before re-admission.** 1-029,
1-030 and 1-031 carry figures from unverified sheet scratchpads
(`results/recommendations/20260801T093002Z.md` §5). 1-030 in particular has *never*
pulled data, so its `mangroves=78,924 hectares` has never been checked against
anything.

**F5 — Only then consider re-admitting it from info-only**, on the standard bar: a
3-trial run with std ≤ 0.10 and at least one demonstrated true positive. Until it
has caught a wrong per-class number at least once, it is unproven as a check, not
merely flaky.

### Tests to write first

- an aggregate column near the target must **not** satisfy a per-class expectation
  (2a, currently passes)
- a per-class figure keyed under a label field **is** matched, and one keyed only
  under an unrelated dimension abstains rather than failing (2b)
- `records == []` abstains
- a genuinely wrong per-class number still fails — the check's actual purpose,
  which has no test coverage today because it has never happened in a run

### Not in scope

Arithmetic consistency of aggregates (does the total equal the sum of its parts?)
is a different assertion and belongs in its own check with its own spec decision on
whether absence is `null` or `0.0`.
