# Writing GOLD cases — what makes a good prompt

GOLD is a **capability smoke test**. A case earns its place by failing when
a release breaks a capability and passing otherwise. Everything below
follows from that one job. (Strategy lives in `docs/CASESET_PLAN.md`; this
file is the working guide you read before adding or editing a case.)

## The two stores

```
cases/v1/   the as-imported baseline (sheet lineage) — re-imports only
cases/v2/   the curated working set — all improvement work lands here
```

Tools default to `v2`; pass `--cases-dir cases/v1` to run the baseline.
Both carry their own `MANIFEST.json`; runs record which `caseset_version`
they executed, so v1-vs-v2 comparisons are ordinary ledger diffs. v1 exists
so improvement claims are measurable, not vibes: same build, both stores,
compare the reports.

## The four properties of a good case

1. **Capability-anchored.** It exercises one nameable thing the product
   does. If this case fails, an engineer knows which subsystem to look at
   — that is what `group:` means.
2. **Deterministic.** It fails only when the agent changes — never because
   time passed, data updated, or a judge got moody.
3. **Checkable in depth.** Its expectations imply at least 2 checks in at
   least 2 buckets (Retrieval / Analysis / Explanation / Output / Scope),
   so a "pass" can't mean "measured nothing".
4. **Environment-honest.** If the capability is absent somewhere
   (dashboards and `send_nudge` are absent on prod), the case carries an
   `env_gated` note so its zeros are never read as agent regressions.

## DOs

- **DO use absolute, closed date windows.**
  ✔ `"…between January 2025 and April 2025…"` with
  `start_date: '2025-01-01'`, `end_date: '2025-04-30'`
- **DO give every case a `scope`** (`analyse` / `suggest` / `clarify` /
  `refuse`) — it is the cheapest deterministic check in the suite.
- **DO name the metric unambiguously** — the class, the gas basis, the
  confidence tier. ✔ `"gross greenhouse gas emissions from tree cover loss"`
  ✘ `"deforestation-related carbon emissions"`. ✔ `"natural grassland"`
  ✘ `"grassland"`. ✔ `"the short vegetation land cover class"`.
  Measured over 312 trials: precisely-worded rows trigger a dataset-choice
  nudge on **1.2%** of trials, loosely-worded ones on **38%** — and one nudge
  fails 5–7 checks at once, because no data is pulled. This is the AOI rule
  below, applied to the metric axis.
- **DON'T name the dataset by id or product name.** ✘ `"Using the SBTN
  Natural Lands Map…"` hands over the answer and turns `dataset_id_match`
  into a string-copy test. The exceptions are the groups whose subject *is*
  the dataset: `dataset-parameters`, `dataset-suggestion`, `context-layer`,
  `dashboard`.
- **DO use `;`-alternatives where two answers are genuinely defensible** —
  in preference to disambiguating the prompt.
  ✔ 1-003 expects `dataset_id: "0;11"` because DIST-ALERT and integrated
  alerts are both correct routings for that query. A single-value
  expectation on a defensible-either-way row is a flaky case you authored
  yourself. The row then still tests "route somewhere defensible and
  analyse", passes on either choice, and fails only on a nudge. Two families
  need it: alerts (`0;11`) and emissions (`4;6`). `scope` accepts
  alternatives too (`refuse;suggest` on 1-089).
- **DO keep a few deliberately loose sentinels.** If every row names its
  metric precisely, nothing detects the *next* over-nudging regression —
  the `nudge` and `clarification` rows only test that the agent nudges when
  it *should*. 1-004 and 1-043 are the nominated dataset-side sentinels
  (loose wording + `;`-alternatives + `scope: analyse`), and 1-014 the
  AOI-side one. Don't tighten them without nominating replacements.
- **DO put per-class figures in `class_values`** when the query implies a
  breakdown: ✔ `class_values: "mangroves=15,444 hectares"` — it is the
  Analysis bucket's main expectation-driven check, catching wrong
  sub-totals hiding under a correct headline.
- **DO write behaviour expectations in `text`** for terminology, caveats,
  and refusals: ✔ `text: "resolution of tree cover loss is 30 x 30 meters"`
  ✔ `text: "refuses monthly analysis because the dataset is annual"` —
  the semantic-inclusion judge is the most stable judge in the suite.
- **DO name the admin level when AOI ambiguity exists.**
  ✔ `"…in Puri district, Odisha, India"` — or expect the clarification
  instead. An ambiguous AOI with a pinned expectation flaps (1-112:
  `BRA` vs `BRA.14.8_2` on identical input).
- **DO record why in `notes.status_reason`** whenever you park a case —
  the note is triage gold for whoever unparks it (1-003's note is the
  model), and notes never change the uid.

## DON'Ts

- **DON'T use relative dates.** ✘ `"…in the past decade"` (1-011) drifts
  every year. The one tolerated pattern is when only *routing* is
  asserted: `"most recent year"` (1-072) works because its expectations
  are dataset-only — copy that pattern deliberately or not at all.
- **DON'T set date expectations on annual datasets** (Tree cover loss and
  friends). The agent pulls the full range and slices in code; the
  recorded window flips between runs while the answer stays right. Let
  `answer` carry the year; keep date expectations for genuinely
  date-scoped pulls (DIST-ALERT, integrated alerts, imagery).
- **DON'T stake a verdict on chart choice.** Chart type is the agent's
  most nondeterministic surface (8 of run-5's 19 flaky rows). If chart
  type matters, expect alternatives: `chart_type: "bar;table"`.
- **DON'T pin expectations that drift with data versions** — "the most
  recent year is 2024" breaks on the next data drop. Expected numbers
  should come from closed periods on stable datasets.
- **DON'T author judged-only rows** unless the capability is inherently
  textual (the `metadata` group is the sanctioned exception). Every row
  should carry at least one deterministic expectation.
- **DON'T write multi-turn turns whose text depends on the agent's
  previous wording.** ✔ `"Puri in Odisha, India"` works whatever the
  clarification said. ✘ `"yes, the first option"` depends on option order.
- **DON'T edit `expected` casually.** Every semantic edit mints a new uid
  — intended, but it resets that case's regression history. Batch
  expectation edits, explain them in the PR, run `check.py --fix`.

## Worked examples

**Good single-turn case** (deterministic, deep, capability-anchored):

```yaml
id: 1-002
status: ready
group: direct
query: How much of Sao Paulo was impacted disturbance alerts in the second
  half of 2024, considering high confidence alerts only?
expected:
  aoi_ids: BRA.25_1          # named state, no ambiguity
  dataset_id: '11'
  start_date: '2024-07-01'   # closed absolute window, date-scoped dataset
  end_date: '2024-12-31'
  answer: 1,299,278 hectares # closed period -> stable number
  scope: analyse
```
Implied checks: aoi, dataset, dates, pull, answer (x2), chart_produced,
answered_without_data, scope — five buckets covered by one row.

The figure was `1,319,600` until 2026-08-03 and matched nothing the agent
produced. Two lessons worth carrying: an expected number must come from a
real run, not a scratchpad; and pick the value that sits **far** inside the
2% tolerance rather than just inside it — `1,319,600` was 1.54% off the
agent's stable answer, so one data refresh would have flipped a passing row
to a hard failure with nothing changed.

**Bad case, and its repair:**

```yaml
# BAD: relative window, judged-only, no scope
query: How much land changed to short vegetation in protected areas in
  Colorado in the past decade?
expected:
  aoi_source: gadm

# REPAIR: close the window, add the checkable expectations
query: How much land changed to short vegetation in protected areas in
  Colorado between 2015 and 2024?
expected:
  aoi_ids: USA.6_1
  dataset_id: '1'
  scope: analyse
  class_values: "short vegetation=53,498 hectares"
```

**Good multi-turn case** (fixed turn text, delta assertions):

```yaml
id: mt-005
turns:
  - query: How much tree cover loss did Brazil have in 2022?
    expected: {aoi_ids: BRA, dataset_id: '4', scope: analyse}
  - query: And for Indonesia?
    expected: {aoi_ids: IDN, scope: analyse}
    deltas: {changed: [aoi_ids], retain: [dataset_id]}
```

## Mechanics checklist (every case PR)

- [ ] `uv run python tools/check.py --fix` after any edit (uid truthful)
- [ ] `uv run pytest tests/test_schema.py -q` (schema conformance)
- [ ] the four properties hold; expectations imply ≥2 checks in ≥2 buckets
- [ ] `env_gated` noted if the capability is environment-dependent
- [ ] PR text says *why* the semantics changed (uid churn is the record)
