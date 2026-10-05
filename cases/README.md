# Writing GOLD cases: what makes a good prompt

GOLD is a **capability smoke test**. A case earns its place by failing when
a release breaks a capability and passing otherwise. Everything below
follows from that one job. Read this file before you add or edit a case.

Terms are defined in the [README glossary](../README.md#glossary). A case
is one YAML file at `cases/<store>/<group>/<id>.yaml`.
`schema/case.schema.json` defines its fields, and the
[check index](../src/goldset/evaluators/README.md#index) says which
`expected` key switches on which check. The commands to run after any edit
are in [README: Changing cases](../README.md#changing-cases).

## The two stores

```
cases/v1/   frozen baseline, as imported from the original Google Sheet (now retired)
cases/v2/   the curated working set: every edit and every new case lands here
```

- Tools default to v2; pass `--cases-dir cases/v1` to run or check v1.
- Each store has its own `MANIFEST.json` holding its
  [caseset_version](../README.md#caseset-version). A run records the store
  (`caseset`) and caseset_version it loaded, so comparing a v1 run with a
  v2 run is an ordinary diff over the uids both runs share.
- v1 exists so that curation claims are measurable: run the same build
  against both stores and compare the reports.
- **Never edit v1.** `tests/test_v1_frozen.py` fails if its
  caseset_version moves. v1 changed only on deliberate re-imports from the
  sheet; the legacy `tools/import_sheet.py` writes to v2 unless you pass
  `--cases-dir cases/v1`.
- The stores hash multi-turn cases differently: a v2
  [uid](../README.md#uid) also covers each turn's `deltas`, while v1 uids
  leave them out, so v1 stays frozen.

## The four properties of a good case

1. **Capability-anchored.** It exercises one nameable thing the product
   does. If the case fails, an engineer knows which subsystem to look at;
   that is what `group:` means.
2. **Deterministic.** It fails only when the agent changes, never because
   time passed, data was updated or a judge changed its mind.
3. **Checkable in depth.** Its expectations imply at least two checks in at
   least two [buckets](../README.md#bucket) (Retrieval, Analysis,
   Explanation, Output, Scope), so a pass can't mean "measured nothing".
   CI enforces this ([The audit gate](#the-audit-gate)).
4. **Environment-honest.** If the capability is missing in some environment
   or [profile](../README.md#profile), the case carries an `env_gated` note
   so its zeros are never read as agent regressions. Today the LGMS dataset
   (id 12) exists only on the `experimental` profile, so its cases are
   parked while runs use the default profile. Re-check `env_gated` notes
   when the environment changes: older notes saying that dashboards or
   imagery need `--ff experimental` are out of date
   ([Running the set](../README.md#running-the-set)).

## DOs

- **DO use absolute, closed date windows.**
  ✔ `"…between January 2025 and April 2025…"` with
  `start_date: '2025-01-01'`, `end_date: '2025-04-30'` (date expectations
  belong only on date-scoped datasets; see the DON'Ts).
- **DO give every case a `scope`**: `analyse` (the agent pulled data),
  `suggest` (it offered datasets through a `dataset_choice` nudge),
  `clarify` (it asked the user to choose through another kind of nudge) or
  `refuse` (no pull and no nudge). It is the cheapest deterministic check
  in the suite: one key, read straight off the final state. A clarifying
  question asked in prose alone, with no nudge, classifies as `refuse`.
- **DO name the metric unambiguously**: the class, the gas basis, the
  confidence tier. ✔ `"gross greenhouse gas emissions from tree cover loss"`
  ✘ `"deforestation-related carbon emissions"`. ✔ `"natural grassland"`
  ✘ `"grassland"`. ✔ `"the short vegetation land cover class"`.
  Measured over 312 trials, precisely worded rows trigger a dataset-choice
  nudge on **1.2%** of trials and loosely worded ones on **38%**, and one
  nudge fails five to seven checks at once because no data is pulled. This
  is the AOI rule below, applied to the metric.
- **DO steer with a framing clause when only one of two similar datasets
  gives the intended answer.** ✔ `"Distinguishing natural from non-natural
  land cover, …"` routes to SBTN Natural Lands rather than Global Land
  Cover without naming either. Left unsteered, the agent may nudge between
  the two and fail the case. If both datasets would give the same answer,
  accept both instead (next rule).
- **DO use `;`-alternatives where two answers are genuinely defensible and
  the expected result is the same either way**, in preference to rewording
  the prompt. `dataset_id: "<a>;<b>"` accepts either dataset;
  `scope: "refuse;suggest"` accepts either behaviour. A single-value pin on
  a row that could defensibly go either way is a flaky case you authored
  yourself. With alternatives, the row still tests "route somewhere
  defensible and analyse", passes on either choice and fails only on a
  nudge. Record in `notes` why both are defensible. In some fields `;`
  means "all of these", not "either": see
  [`;` alternatives by field](#semicolons).
- **DO keep a few deliberately loose sentinels.** If every row names its
  metric precisely, nothing detects the next regression towards
  over-nudging: rows that expect a nudge only test that the agent nudges
  when it *should*. A sentinel has loose wording, `;`-alternatives covering
  every defensible dataset, and `scope: analyse`, so it passes on any real
  analysis and fails only on a nudge. **No sentinel exists today**: the
  cases that once served were tightened, and a `notes.sentinel` entry left
  on a tightened case is out of date. When you nominate one, say so in
  `notes.sentinel`, and do not tighten a sentinel without nominating a
  replacement.
- **DO put per-class figures in `class_values`** when the query implies a
  breakdown: ✔ `class_values: "mangroves=15,444 hectares"`. It catches a
  wrong sub-total hiding under a correct headline. But `class_value_match`
  is currently [info-only](../README.md#info-only): reported, never
  gating. The
  [info-only list](../src/goldset/evaluators/README.md#info-only-checks)
  says what would make it gate again. If the row needs a gating Analysis
  check, also add a verified `answer`.
- **DO write behaviour expectations in `text`** for terminology, caveats
  and refusals: ✔ `text: "resolution of tree cover loss is 30 x 30 meters"`
  ✔ `text: "refuses monthly analysis because the dataset is annual"`. The
  semantic-inclusion judge behind it is the most stable judge in the suite.
- **DO name the admin level when the AOI is ambiguous.**
  ✔ `"…in Puri district, Odisha, India"`, or expect the clarification
  instead. An ambiguous AOI with a pinned expectation flaps: the agent can
  resolve the same input to a country on one trial and a district on the
  next. A place made of many areas ("protected areas in Colorado") may
  resolve to a different set on every trial; check that the agent resolves
  the AOI consistently before you invest in expectations.

## DON'Ts

- **DON'T name the dataset by id or product name.** ✘ `"Using the SBTN
  Natural Lands Map…"` hands over the answer and turns `dataset_id_match`
  into a string-copy test. The exceptions are the groups whose subject *is*
  the dataset: `dataset-parameters`, `dataset-suggestion`, `context-layer`
  and `dashboard`.
- **DON'T use relative dates.** ✘ `"…in the past decade"`, ✘ `"…since 2020"`:
  the true answer moves with every data release. The one tolerated pattern
  is a query whose expectations are **routing-only** (`aoi_ids`,
  `aoi_source`, `dataset_id`, `dataset_name`, `dataset_parameters`,
  `context_layer`, `scope`, `clarification`), with no `answer`, `text` or
  dates, because none of those drift with time. Even then, prefer closing
  the window. If a query must name the current period (imagery that exists
  only for the current month, say), write a template token instead:
  `{current_month}`, `{last_month}` or `{current_year}` (`TEMPLATE_VARS` in
  `src/goldset/templates.py`). The harness fills in the date when the run
  starts and the uid hashes the token, so the case keeps its identity from
  month to month. Pair a token only with expectations that hold whatever
  date it resolves to.
- **DON'T set date expectations on annual datasets** (tree cover loss and
  the other yearly datasets). The agent pulls the full range and slices in
  code, so the recorded window flips between runs while the answer stays
  right. Let `answer` carry the year. Keep date expectations for genuinely
  date-scoped pulls: integrated alerts (dataset 11) and the `imagery` group
  (`DATE_SCOPED_DATASET_IDS` and `DATE_SCOPED_GROUPS` in
  `tools/audit_cases.py`).
- **DON'T stake a verdict on chart choice.** Chart type is the agent's
  least deterministic output (8 of the 19 flaky rows in one 3-trial run).
  If chart type matters, expect alternatives: `chart_type: "bar;table"`.
  The check reads only the first chart.
- **DON'T pin expectations that drift with data versions.** "The most
  recent year is 2024" breaks on the next data release. Expected numbers
  should come from closed periods on stable datasets.
- **DON'T author judged-only rows** unless the capability is inherently
  textual (the `metadata` group is the sanctioned exception). Every row
  should carry at least one deterministic expectation besides `answer` and
  `text`.
- **DON'T write multi-turn turns whose text depends on the agent's
  previous wording.** ✔ `"Puri in Odisha, India"` works whatever the
  clarification said. ✘ `"yes, the first option"` depends on option order.
- **DON'T edit `expected` casually.** Editing the query, any expected value
  or (in v2) a turn's `deltas` mints a new [uid](../README.md#uid). That is
  intended, but it resets the case's regression history, and a `done` case
  must be verified again at the new uid. The uid covers every expected
  field, scored or not (`dataset_name` drives no check but is hashed), so a
  result always points at the exact content it ran against. Don't move
  expectations into `notes` to avoid a new uid. Batch expectation edits and
  explain them in the PR.

<a id="semicolons"></a>
## `;` alternatives by field

A `;` inside an expected value does not mean the same thing in every
field. Check this table before you write one.

| Field | `a;b` means | How it is matched |
|---|---|---|
| `dataset_id` | any of | the dataset the agent chose (and, for `pull_source_match`, the one it pulled) must be one of the alternatives |
| `scope` | any of | the observed scope must be one of them; one invalid alternative makes the check abstain |
| `nudge_type` | any of | the nudge's type must be one of them |
| `chart_type` | any of | the first chart's type must be one of them |
| `aoi_ids` | all of | the set of resolved AOI ids must equal the expected set exactly (GADM ids are compared without their `_N` suffix); there is no way to write "either of these places" |
| `class_values` | all of | every `name=value` pair must match within the 2% tolerance |
| `dashboard_widgets` | all of, with counts | widget types are compared as a multiset: `insight;insight;map` means exactly two insight widgets and one map widget |
| `nudge_options` | allowed set | the agent must offer at least one option, and every option it offers must match one in the list (case-insensitive substring, either way round) |
| `suggested_datasets` | allowed set | as `nudge_options`; legacy, because the agent no longer writes this state field |
| any other field (`answer`, `text`, dates, ...) | nothing special | the value is used whole. In `answer` the judge reads `a;b` as written, so a reply that merely names both values can pass |

## Worked examples

Each example quotes a real case file, without its `uid` and `notes`. If you
edit one of these cases, update the quote here.

**A good single-turn case** (`cases/v2/direct/1-002.yaml`):

```yaml
id: 1-002
status: done
group: direct
query: How much of Sao Paulo was affected by disturbance alerts in the second half of 2024,
  considering high and highest confidence alerts only?
expected:
  aoi_ids: BRA.25_1
  aoi_source: gadm
  dataset_id: '11'
  dataset_name: Integrated alerts
  start_date: '2024-07-01'
  end_date: '2024-12-31'
  answer: 1,299,278 hectares
  scope: analyse
```

- It names a state (no AOI ambiguity), the confidence tiers (one reading of
  the metric) and a closed window on a date-scoped dataset, so the answer
  is stable.
- Its expectations imply eight checks across all five buckets:
  `aoi_id_match`, `dataset_id_match`, `date_extraction`,
  `data_pull_exists`, `answered_without_data`, `agent_answer`,
  `chart_produced` and `scope_match`. `aoi_source` and `dataset_name` imply
  none, though both are hashed into the uid.
- The expected number came from a real run and sits well inside the 2%
  tolerance. A figure 1.5% off the agent's stable answer would flip to a
  hard failure on the next data refresh with nothing else changed.

**A bad case and its repair** (`cases/v1/direct/1-075.yaml`, then
`cases/v2/direct/1-075.yaml`):

```yaml
# v1: parked
id: 1-075
status: not doing
group: direct
query: How much tree cover loss within intact forest landscapes in Sweden since 2020?
expected:
  aoi_ids: SWE
  dataset_id: '4'
  dataset_name: Tree cover loss
  context_layer: intact_forest
  answer: 3.3 kha
  scope: analyse

# v2: repaired and verified
id: 1-075
status: done
group: direct
query: How much tree cover loss occurred within intact forest landscapes in Sweden between
  2020 and 2024?
expected:
  aoi_ids: SWE
  dataset_id: '4'
  dataset_name: Tree cover loss
  context_layer: intact_forest
  answer: 391.70 hectares
  scope: analyse
  aoi_source: gadm
```

"Since 2020" is an open window, so the true figure grows with every data
release. Closing it to 2020 to 2024 fixes the answer, and the new figure
was measured on a 3-trial run (391.70 ha on all three trials). The old
`3.3 kha` had never been verified, and it was wrong.

**A multi-turn case** (`cases/v2/multiturn/mt-005.yaml`):

```yaml
id: mt-005
status: ready
group: multiturn
turns:
- query: How much tree cover loss did Brazil have in 2022?
  expected:
    aoi_ids: BRA
    dataset_id: '4'
    scope: analyse
- query: And for Indonesia?
  expected:
    aoi_ids: IDN
    scope: analyse
  deltas:
    changed:
    - aoi_ids
    retain:
    - dataset_id
```

All turns share one thread, and turn 2's text works whatever turn 1's reply
said. Its `deltas` assert how the state moved since the previous turn:
`changed` (the field must differ), `retain` (it must stay the same, which
catches lost context) and `absent` (it must be empty, which catches
carry-over). Each turn with `deltas` adds a `state_delta` check; the
allowed field names are listed in `schema/case.schema.json`.

## Status lifecycle

Every case has one of four statuses:

- `ready`: written and expected to pass, but not yet verified at its current uid.
- `todo`: held by a known problem; a dated `notes.status_reason` says what blocks it.
- `done`: verified at its current uid (see below).
- `not doing`: parked; runs skip it, and `notes.status_reason` says why.

`gold run` runs every status except `not doing` (`--status-exclude`
defaults to `not doing`), and the audit and COVERAGE.md count the same
cases as active. So `ready` and `todo` cases are run and scored like
`done` ones; the progress line prints each case's status, so a failure on
an unverified case reads differently. COVERAGE.md lists every `todo` and
`not doing` case with its reason
([Parked and held cases](v2/COVERAGE.md#parked-and-held-cases)).

**Promoting to `done`.** A case is `done` when it passes at its current
uid on a 3-trial run with the same `ff` as the release baseline (today the
default [profile](../README.md#profile), no `--ff`): every gating check
that ran passed on the majority of the three [trials](../README.md#trial).
Cite the run_id and date in `notes.status_reason`, for example
`promoted to done <date>: passed at this uid on run <run_id> (3 trials, default profile)`.
A 1-trial pass is a smoke signal, not verification. An edit that mints a
new uid ends the verification: set the case back to `ready` until it
passes again.

**Parking.** Set `status: not doing` when a case cannot earn a verdict,
and always write a dated `notes.status_reason` with the evidence: which
run, what the agent did on how many trials, and why no prompt edit can fix
it (or what would). `cases/v2/parent-child/1-011.yaml` has a good example.
Notes are never hashed, so parking does not change the uid.

**Unparking.** Treat it as probation: re-test the reason the case was
parked, and do not assume it is fixed. An edit that does not touch that
reason (closing the date window on a case parked for an ambiguous AOI,
say) leaves the case parked. An unparked case returns as `ready` (or
`todo`) and earns `done` like any other.

## Mechanics checklist (every case PR)

- [ ] the four properties hold, and the expectations imply at least two
      checks in at least two buckets
- [ ] `env_gated` noted if the capability depends on the environment or profile
- [ ] the status follows the [status lifecycle](#status-lifecycle); a `done`
      case cites its verifying run
- [ ] the after-edit commands in [README: Changing cases](../README.md#changing-cases)
      ran clean, and their output is committed with the case
- [ ] `uv run pytest tests/test_schema.py -q` passes (the file matches the schema)
- [ ] if you edited a case quoted in [Worked examples](#worked-examples), the
      quote is updated
- [ ] the PR text says *why* the semantics changed (the uid change records *what*)

## The audit gate

CI runs `uv run python tools/audit_cases.py --strict` on every PR and every
push to `main`. It checks every active case in v2 (any status but
`not doing`, and every turn of a multi-turn case) and **fails the build**
on two kinds of defect, both fixable in the case you are already editing:

- **Depth violations**: a case whose expectations imply fewer than two
  checks, or checks in fewer than two buckets. A row like that can "pass"
  while measuring almost nothing, and an unmeasured bucket must look
  different from a passing one. The usual fix is a verified `answer`, which
  implies checks in Retrieval, Analysis, Explanation and Output at once;
  `scope` adds only Scope. The audit counts info-only checks too, so
  `class_values` satisfies it without adding a gating check. The `metadata`
  group is exempt.
- **DON'T violations** (`dont_violations` in `tools/audit_cases.py`):
  - relative-date words (`last`, `past`, `recent`, `latest`, `this year`,
    `this month`, `this week`) in a query whose expectations go beyond
    routing;
  - `start_date` or `end_date` on a dataset that is not date-scoped (with
    `;`-alternatives, every alternative must be date-scoped);
  - judged-only expectations (`answer` or `text` with no deterministic
    field and, on a multi-turn turn, no `deltas`) outside the `metadata`
    group;
  - an unknown `{template}` token in a query.

Deliberately **not** gated: the coverage floors (groups or datasets with
fewer than three active cases). Clearing those means authoring new cases,
which is different work from fixing the one in front of you, so they stay
report-only. The report is still worth reading.

Run the audit before you open a PR; it takes about a second and is the
same command CI runs.

**A green audit is not proof.** The relative-date rule matches a fixed
list of words, so phrasings like "since 2020" or "since the turn of the
century" pass the audit even when paired with an `answer`. Read the rule,
not just the exit code.
