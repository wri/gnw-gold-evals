# Evaluators — check reference

This is the triage reference for every check the GOLD harness can emit. It
describes behaviour **as the code in this directory stands** (last evaluator
changes: 2026-08-03/04, H1–H8 of `docs/specs/caseset-v2-improvement-plan.md` §4).
Where the code and an older spec disagree, the code wins and the difference is
called out.

Every mean/std quoted below comes from the 3-trial validation run
`results/runs/20260803T201245Z_staging.json` (reproduce with
`uv run python tools/flakiness.py results/runs/20260803T201245Z_staging.json`),
which is the most complete run on the current case set. **That run omitted
`--ff experimental`**, so the four dashboard checks and the imagery rows were not
exercised in it; where a dashboard figure is quoted it comes from the
flag-bearing partial run `20260803T215155Z_staging_experimental` and its small n
is stated. `results/recommendations/20260803T201245Z.md` explains the flag and
why the run_id suffix is the tell.

## What an evaluator is here

An evaluator is a function of the agent's final state plus the case's
expectations — side-effect-free on its inputs, though the judged ones do call
Haiku. It takes `agent_state` (the `/api/threads/{id}/state` payload as
the runner received it), an `ExpectedData` (the case's `expected:` block,
re-prefixed with `expected_` by `adapter.py:21`), the query, and — for dashboard
checks — the separately fetched dashboard payload. It returns a flat dict of
`<check>_score` fields plus `actual_*` diagnostics. Nothing mutates the state;
nothing calls the agent.

The runner iterates `EVALUATORS` in declaration order and merges the dicts, so
**later evaluators win key collisions** (`registry.py:57-224`,
`runner/base.py:126-146`). Every `*_score` key except `overall_score` becomes a
ledger check, with the suffix stripped: `charts_answer_judge_score` →
`charts_answer_judge` (`cli.py:86-90`, `ledger.py:42-48`). `overall_score` is a
legacy flat mean kept only for output parity and is deliberately not extended
with checks added after the port (`runner/base.py:148-166`) — never read it.

### Tri-state, and why `null` vs `0.0` is the whole game

Every check is `1.0` (pass), `0.0` (fail), or `null` (not applicable). The
ledger refuses anything else (`ledger.py:61-69`). `docs/specs/PLAN.md` §6 requires each
check to decide *deliberately* whether an absence is `null` or `0.0`, so each
section below states its rule. Two consequences worth internalising while
triaging:

- A row with **zero** evaluated gating checks is `uncovered`, not a pass
  (`buckets.py:113-124`). Silent non-measurement is the bug class the
  reconciliation line exists to catch (`buckets.py:189-227`, `247-276`).
- An absence that *should* have been a failure is the most expensive kind of
  bug here, because it inflates the pass rate invisibly. Most of the PR-04 "F"
  fixes were exactly this (e.g. an AOI expectation with no resolved AOI used to
  return `null`; it is now `0.0` — `aoi_evaluator.py:52-58`).

### Numbers in code, structure to the judge

No judge is ever asked to do arithmetic (`docs/specs/PLAN.md` §6). The precedent is
recorded at the top of `chart_numeric.py:3-8`: asked about a chart whose 25
yearly values sum to 25.31 Mha, Haiku reported the same chart as summing to
27.4 Mha and to 26.0 Mha, each "within tolerance" of whatever expected value it
had been handed. So numeric agreement is computed in
`chart_numeric.evaluate_numeric_support` against the chart's own encoded data,
and `llm_judge_chart`'s prompt explicitly forbids the model from judging
numbers (`llm_judges.py:366-372`). Only three checks are judged at all —
`clarification_requested`, `agent_answer`, `expected_text_match` — plus the
now-info-only `charts_answer_judge`.

### Gating vs info-only

A **gating** check can turn a row's verdict to `fail`. An **info-only** check is
reported and never enters a verdict (`buckets.py:83-90`, `113-124`). Demotion is
an admission-discipline device, not silencing: judged checks run info-only until
they show std ≤ 0.10 over 3 trials (`docs/specs/PLAN.md` §4), and a check that proves
unreliable in a live run is demoted with a stated re-admission condition. See
[Info-only checks](#info-only-checks-and-what-re-admission-requires) at the end.

Judge **outages** are a third state: they raise rather than guessing
(`llm_judges.py:107-113`), the check stays `null`, the check name is appended to
`judge_errors`, and the row's verdict becomes `error` — never `fail`
(`buckets.py:115-116`).

### Where a failure's evidence lands

- `reasons.<check>` — any field named `<check>_reason` or `<check>_score_reason`
  (`ledger.py:51-58`), trimmed to 500 chars. One historical alias:
  `chart_answer_score_reason` → `reasons.charts_answer` (`ledger.py:21`).
- `actuals.<check>` — the `actual_*` diagnostics mapped in
  `cli.py:41-64`, **recorded only for checks that scored `0.0`**
  (`cli.py:68-80`). This is a real triage trap: several evaluators write
  carefully-worded abstention strings into `actual_*` fields (see
  [`pull_source_match`](#pull_source_match),
  [`class_value_match`](#class_value_match), [`scope_match`](#scope_match)), and
  because those abstentions score `null`, the strings never reach the ledger.
  A third gap: the clarification judge's prose lands in
  `clarification_explanation`, which matches neither reason pattern, so it is
  dropped too.
- `results/artifacts/<run_id>/<uid>[_t<trial>].json.gz` — raw state (final answer,
  codeact, tool calls, last statistics, charts, aoi_selection, dataset, nudge,
  dashboard widgets: `runner/artifacts.py:76-98`; one file per trial,
  `:105-112`). Evaluator diagnostics are *not* in there, so when a reason string
  is missing this is where you re-derive it.

### Multi-turn

Conversation checks are flattened under a turn prefix — `t2.aoi_id_match` — and
all bucket/verdict/diff machinery strips it (`buckets.py:93-99`,
`runner/multiturn.py:176-184`). Everything below applies per turn unchanged.

---

## Index

Bucket tags come from `buckets.py:32-66`; "shared" means a failure cannot be
attributed to one bucket, which is why the bucket table reports the two
populations separately. "Switched on by" names the key as written in a case
YAML's `expected:` block (unprefixed — `adapter.py:21` adds `expected_`). "Kind"
is the registry's `EvaluatorSpec.kind` (`registry.py:49-54`), which is also what
decides whether `tools/flakiness.py` holds a check to the judged ±0.10 gate or
the tighter deterministic one (`tools/flakiness.py:31-40`).

| Check | Bucket | Kind | Verdict role | Switched on by | Source |
|---|---|---|---|---|---|
| [`aoi_id_match`](#aoi_id_match) | retrieval | deterministic | gates | `aoi_ids` | `aoi_evaluator.py:8` |
| [`dataset_id_match`](#dataset_id_match) | retrieval | deterministic | gates | `dataset_id` | `dataset_evaluator.py:40` |
| [`dataset_parameter_match`](#dataset_parameter_match) | retrieval | deterministic | gates | `dataset_parameters` **and** `dataset_id` | `dataset_evaluator.py:124-129` |
| [`context_layer_match`](#context_layer_match) | retrieval | deterministic | gates | `context_layer` **and** `dataset_id` | `dataset_evaluator.py:132-138` |
| [`date_extraction`](#date_extraction) | retrieval | deterministic | gates | `start_date` **and** `end_date` | `data_pull_evaluator.py:63` |
| [`date_coverage`](#date_coverage) | — (untagged) | deterministic | **info-only** | `start_date` **and** `end_date` | `data_pull_evaluator.py:188` |
| [`data_pull_exists`](#data_pull_exists) | retrieval | deterministic | gates | derived: `answer`, or `dashboard_widgets` containing `insight` | `data_pull_evaluator.py:284` |
| [`answered_without_data`](#answered_without_data) | retrieval | deterministic | gates | derived: same as above | `guards.py:100-105` |
| [`pull_source_match`](#pull_source_match) | retrieval | deterministic | gates | `dataset_id` + a pull happened | `guards.py:119-153` |
| [`state_delta`](#state_delta) | retrieval | deterministic | gates | a turn's `deltas:` block | `runner/multiturn.py:45` |
| [`class_value_match`](#class_value_match) | analysis | deterministic | **info-only** | `class_values` | `analysis_checks.py:65` |
| [`chart_integrity`](#chart_integrity) | analysis | deterministic | gates | nothing — any row with charts | `analysis_checks.py:121` |
| [`charts_answer`](#charts_answer) | analysis + output (shared) | mixed — deterministic comparator decides, judge recorded | gates (on the comparator alone, H5) | `answer` + charts present | `answer_evaluator.py:168-186`, `llm_judges.py:237-292` |
| [`charts_answer_judge`](#charts_answer_judge) | — (untagged) | judged | **info-only** | same as `charts_answer` | `llm_judges.py:292`, `eval_types.py:86-87` |
| [`agent_answer`](#agent_answer) | analysis + explanation (shared) | judged | gates | `answer` + non-empty final message | `answer_evaluator.py:189-201` |
| [`expected_text_match`](#expected_text_match) | explanation | judged | gates | `text` + non-empty final message | `answer_evaluator.py:203-218` |
| [`answer_traceability`](#answer_traceability) | explanation | deterministic | **info-only** | nothing — any row with charts + a bold unit-bearing claim | `explanation_checks.py:55` |
| [`web_fallback`](#web_fallback) | explanation | deterministic | gates | derived data-pull expectation + non-empty answer | `guards.py:107-117` |
| [`chart_produced`](#chart_produced) | output | deterministic | gates | `answer` + derived data-pull expectation | `guards.py:97-98` |
| [`chart_well_formed`](#chart_well_formed) | output | deterministic | gates | nothing — any row with charts | `output_checks.py:20` |
| [`chart_type_match`](#chart_type_match) | output | deterministic | gates | `chart_type` | `output_checks.py:63` |
| [`dashboard_created`](#dashboard_created) | output + scope (shared) | deterministic | gates | `dashboard_created`, **or** an unsolicited dashboard | `dashboard_evaluator.py:9` |
| [`dashboard_aoi_match`](#dashboard_aoi_match) | output | deterministic | gates | `aoi_ids` + a fetched dashboard | `dashboard_evaluator.py:48` |
| [`dashboard_widgets_match`](#dashboard_widgets_match) | output | deterministic | gates | `dashboard_widgets` + a fetched dashboard | `dashboard_evaluator.py:159-161` |
| [`dashboard_widgets_valid`](#dashboard_widgets_valid) | output | deterministic | gates | a fetched dashboard with ≥1 widget, or `dashboard_widgets` with none delivered | `dashboard_evaluator.py:163-181` |
| [`clarification_requested`](#clarification_requested) | scope | judged | gates | `clarification` (`true`/`false`) | `clarification_evaluator.py:8` |
| [`suggested_datasets_match`](#suggested_datasets_match) | scope | deterministic | gates | `suggested_datasets` | `suggested_datasets_evaluator.py:6` |
| [`nudge_match`](#nudge_match) | scope | deterministic | gates | `nudge_type` and/or `nudge_options` | `nudge_evaluator.py:35` |
| [`scope_match`](#scope_match) | scope | deterministic | gates | `scope` | `scope_checks.py:54` |

Two expected fields drive **no** check of their own: `aoi_source` is read only by
`dashboard_aoi_match` (`registry.py:160`), and `dataset_name` is read by nothing
at all — it is present on 90 of the 114 `cases/v2` cases and, per
`docs/specs/PLAN.md` §2.2, is hashed into the uid regardless of being unscored. Do not
read either as coverage.

`chart_type_match` currently fires on **zero** `cases/v2` rows (no case sets
`chart_type`), and `suggested_datasets_match` on one. Both are live code with
near-empty populations.

---

# Retrieval

## `aoi_id_match`

**Measures** whether the agent resolved the place named in the prompt to the
expected area-of-interest ids. Compares the *set* of `src_id`s in
`agent_state["aoi_selection"]["aois"]` against the expected set
(`aoi_evaluator.py:60-69`).

**Fires on** `aoi_ids`. The value splits on `;` into a **set compared by set
equality** (`eval_types.py:229-238`) — `;` here means "all of these", the
opposite of the `dataset_id` and `scope` convention where `;` means
"either of these". `cases/v2/imagery/1-104.yaml`'s `notes.rewrite` records the
consequence: a two-level either-or AOI expectation is simply unexpressable.

**`null` vs `0.0`**: `null` only when no `aoi_ids` expectation exists. An
expectation with **no resolved AOI is `0.0`** (`aoi_evaluator.py:52-58`, PR-04
F1) — this used to return `null` and silently raise the row's mean.

**Reason**: none. Evidence is `actuals.aoi_id_match` = `actual_id`, the stringified
list of `src_id`s (`cli.py:42`).

**Gotchas.**
- Normalisation is source-dependent and lossy. For `source == "gadm"`,
  `normalize_gadm_id` truncates at the first `_` and maps `-`→`.`
  (`utils.py:6-10`), so `BRA.25_1` → `bra.25` and **`USA.5_1` and `USA.5_2`
  compare equal** — the GADM level suffix is not checked. Non-GADM sources
  compare lowercased strings only (`aoi_evaluator.py:122-131`).
- The normalisation branch is chosen from the **first** AOI's `source`
  (`aoi_evaluator.py:102`), so a mixed-source multi-AOI result is normalised
  under one rule.
- `expected_aoi_source` is *not* checked here. Only `dashboard_aoi_match` uses it.
- `aoi_selection` is assumed to be a dict; a list-shaped payload would raise
  rather than abstain (`aoi_evaluator.py:84-85`). Every observed payload is a
  dict, so this is latent, not active.

**Stability**: among the most stable gating checks — 0.98, ±0.01, 1 flapping row
over 75 in the 3-trial validation run `20260803T201245Z`.

## `dataset_id_match`

**Measures** whether the agent picked the expected dataset from the registry:
`normalize_value(agent_state["dataset"]["dataset_id"])` against the expected id
(`dataset_evaluator.py:104-113`).

**Fires on** `dataset_id`. Accepts `;`-separated **alternatives** — any one
matching passes (PR-09 H7). This exists because some rows are defensible either
way: 1-003's `dataset_id: "0;11"` covers DIST-ALERT vs integrated alerts.

**`null` vs `0.0`**: `null` with no expectation; `0.0` when an expectation exists
and no dataset was selected at all (`dataset_evaluator.py:85-94`).

**Reason**: none; `actuals.dataset_id_match` = `actual_dataset_id`.

**Gotchas.** `normalize_value` maps `None`, the literal string `"None"`, and
whitespace to `""` (`utils.py:13-17`), so a state field holding the string
`"None"` reads as "no dataset". Dataset id `0` is a real registry id and is
handled correctly here because comparison is on normalised strings, not
truthiness — but see `pull_source_match` for where that distinction had to be
made explicit. `cases/README.md` forbids naming the dataset in the prompt, so
this check is measuring inference, not obedience; 0.91 ±0.06 with 12 flapping
rows over 90 in `20260803T201245Z` reflects genuine agent routing
nondeterminism.

## `dataset_parameter_match`

**Measures** whether the dataset was parameterised as expected — the filters,
class selections, and gas basis that decide *which* number gets computed.
Compares a normalised JSON projection keeping only `name` and `values`
(`dataset_evaluator.py:9-37`, `115-129`).

**Fires on** `dataset_parameters` — **but only when `dataset_id` is also set.**
The evaluator returns all three of its scores as `null` before looking at
parameters if `expected_dataset_id` is empty (`dataset_evaluator.py:69-81`).

**`null` vs `0.0`**: `null` with no expectation, and `null` when the dataset
itself was never selected (`dataset_evaluator.py:88`) — the parameter question
is meaningless without a dataset. Otherwise exact-string comparison of the
normalised projections, so any mismatch is `0.0`.

**Reason**: none; `actuals.dataset_parameter_match` = the actual parameters JSON.

**Gotchas.**
- The `dataset_id` coupling above is a **reconciliation hazard**:
  `buckets.py:199-200` implies this check from `dataset_parameters` alone, so a
  case with parameters but no `dataset_id` will show up as a reconciliation
  miss rather than a silent zero. That is the intended failure mode, but the
  fix is to add `dataset_id` to the case, not to the check.
- If the expected value is not valid JSON, `_normalize_dataset_parameters` falls
  back to `normalize_value` on the raw string (`dataset_evaluator.py:22-23`),
  which will essentially never equal the actual serialised JSON — a malformed
  expectation reads as a hard failure, not an abstention.
- Only `name` and `values` are compared; every other parameter key is invisible
  to this check by design.
- One `cases/v2` row sets it, so its run statistics are not evidence of
  anything (1 case, ±0.00 in `20260803T201245Z`).

## `context_layer_match`

**Measures** whether the agent applied the expected context layer (the
intersecting layer, e.g. a land-cover or driver overlay).

**Fires on** `context_layer`, again **only when `dataset_id` is set**
(`dataset_evaluator.py:69-81`).

**`null` vs `0.0`**: `null` with no expectation or no selected dataset. There is
one sentinel: `context_layer: no_selection` inverts the check — it passes when
the agent selected *no* context layer and fails when it selected any
(`dataset_evaluator.py:134-135`). Otherwise it is exact normalised equality.

**Reason**: none; `actuals.context_layer_match` = `actual_context_layer`.

**Gotcha**: `no_selection` is the only way to express a negative expectation, and
it is compared against normalised emptiness, so a state field holding `"None"`
counts as no selection. 11 rows, 1.00 ±0.00 in `20260803T201245Z` — stable.

## `date_extraction`

**Measures** whether the agent understood the period named in the prompt, read
from the `start_date`/`end_date` **arguments it passed to its own tools** —
`pull_data`, falling back to `pick_dataset` (`data_pull_evaluator.py:25`,
`28-60`). The module docstring (`data_pull_evaluator.py:1-17`) explains why this
and not recorded state: `agent_state["start_date"]` has been observed recording
the requested window, the dataset's full coverage extent, and a rolling window
ending today, for the same query. Tool arguments are the only consistent signal.

**Fires on** `start_date` **and** `end_date` together
(`data_pull_evaluator.py:108-113`). One without the other is `null`.

**`null` vs `0.0`**: `null` when either expected bound is missing or unparseable
by `normalize_start_date`/`normalize_end_date` (`utils.py:46-81`, which accept
`M/D/YYYY`, `YYYY-MM-DD`, and bare `YYYY` — a bare year expands to Jan 1 for a
start and Dec 31 for an end). `0.0` when dates were expected and the agent made
**no** dated tool call at all (`data_pull_evaluator.py:116-118`) — it never
scoped a request, which is a failure and not an absence. `0.0` when dated calls
exist and none matches (`:142`).

**Reason**: none, but three diagnostics are written every run:
`actual_extracted_start_date` / `actual_extracted_end_date` (the matching window,
or the last one observed if nothing matched), `date_extraction_source` (which
tool supplied it), and `actual_extracted_windows` (every observed window as
`tool:start..end`, semicolon-joined). Only the first two are surfaced in
`actuals` (`cli.py:46`).

**Gotchas.**
- **Any** dated call matching passes, so a comparative query that pulls twice is
  not penalised (`data_pull_evaluator.py:121-140`).
- An omitted bound on the agent's side is treated as an open-ended request and
  the missing side is simply not constrained (`:127-131`) — so
  `pull_data(start_date="2001-01-01")` with no end can pass an expectation that
  named both bounds. That is deliberate; coverage of the other side is
  `date_coverage`'s question.
- Only 9 `cases/v2` rows set dates, because `cases/README.md` forbids date
  expectations on annual datasets. 1.00 ±0.00 in `20260803T201245Z`.

## `date_coverage`

**Measures** something different from `date_extraction`: whether the range
*recorded in state* **contains** the requested period — containment, not
equality, because the agent legitimately pulls wider and slices in code
(`data_pull_evaluator.py:188-281`, comparison at `:271-274`).

**Fires on** `start_date` **and** `end_date`.

**Info-only**, and untagged for buckets (`buckets.py:83-90`;
`buckets_for("date_coverage") == ()`). It is excluded from `overall_score` and
from the release gate precisely because the state field it reads is unreliable.

**`null` vs `0.0`**: `null` with no or unparseable expectations. `0.0` when the
expectation is parseable but the recorded range is missing (`:249-255`) or
unparseable (`:262-268`) — a deliberate "missing actual = wrong", which is
tolerable only because the check does not gate.

**Reason**: none; `date_success` mirrors the score, and `actual_start_date` /
`actual_end_date` carry the recorded range (`cli.py:47`).

## `data_pull_exists`

**Measures** whether an analytics pull actually happened and produced something:
the last `statistics` entry must carry a `source_url` or an `id`, or else at
least `min_rows` (default 1) rows of legacy inline data
(`data_pull_evaluator.py:171-185`, `284-338`).

**Fires on** the *derived* expectation `ExpectedData.expects_data_pull()`
(`eval_types.py:264-277`): true when `answer` is set, or when
`dashboard_widgets` contains `insight`; forced false when `clarification` is
`true`. Map-only dashboard rows therefore do not require a pull.

**`null` vs `0.0`**: `null` when no pull is expected (`:312-318`). `0.0` whenever
one is expected and the criteria are unmet, including the no-statistics case
(`:326-329`, `data_pull_error: "no data retrieved"`).

**Reason**: none; `actuals.data_pull_exists` = `data_pull_error`, which is either
`"no data retrieved"` or `"insufficient rows of data retrieved"` (`cli.py:48`).

**Gotcha**: `row_count` is `1` whenever `source_url`/`id` is present, regardless
of the real row count (`:179-180`) — it is a presence flag, not a measurement.
0.94 ±0.04, 6 flapping over 69 rows in `20260803T201245Z`; its flapping is the
head of the nudge-cascade chain, so treat a flip here as the *cause* of the
`chart_produced`/`charts_answer` flips on the same row rather than three
independent findings.

## `answered_without_data`

**Measures** the failure that motivated the guards module: a confident,
substantive answer with **no pull and no dataset selection** behind it
(`guards.py:100-105`). Reference case **1-030** — it pulled no data, selected no
dataset, answered from web knowledge citing `wri.org`, and scored
`agent_answer` 1.0 (`guards.py:6-7`, in the module's reference-failure list).

**Fires on** the derived data-pull expectation (same rule as
`data_pull_exists`).

**`null` vs `0.0`**: `null` when no pull was expected. `0.0` only when *all
three* hold: the final message is ≥ `SUBSTANTIVE_ANSWER_CHARS` (80) characters
(`guards.py:27`), no pull happened (`guards.py:48-55`), and no dataset was
selected (`:91`). Score reads "1.0 = clean, 0.0 = violated".

**Reason**: none, and no `actuals` entry either — read
`actual_agent_answer`/the artifact to see what it answered with.

**Gotchas.**
- The dataset-selection term makes this narrower than "no pull". An agent that
  selects a dataset and then fails to pull passes this guard; that failure is
  `data_pull_exists`'s to report. Deliberate: 1-030 did neither.
- The 80-character threshold is what separates an answer from a refusal or
  greeting; a terse-but-wrong ungrounded answer under 80 chars slips through.

## `pull_source_match`

**Measures** whether the pull that happened actually referenced the expected
dataset — closing the gap where `dataset_id_match` passes on the agent's
*declared* selection while the pull went elsewhere. Compares the statistics
entry's explicit `dataset_id` key (`guards.py:58-69`, `119-153`).

**Fires on** `dataset_id` **and** a pull having happened.

**`null` vs `0.0`**: `null` with no expected dataset or no pull. Also `null` — an
explicit, documented abstention — when the statistics entry carries no
`dataset_id` key at all (3 of 84 live pull-bearing artifacts observed;
`guards.py:130-139`). `0.0` only on a real mismatch.

**Fires on `;`-alternatives** as of PR-09 H7 (`guards.py:146-153`): the expected
value splits on `;` and any alternative matching passes. Before this,
`cases/README.md`'s own sanctioned `dataset_id: "0;11"` pattern could never
match — the practice the case guide recommends guaranteed a failure.

**Reason**: none. `actual_pull_source` is either the pull's dataset id or the
abstention string `"statistics entry carries no dataset_id (source_url=…, id=…);
guard abstained"`. **Only the former reaches the ledger** — the abstention scores
`null`, and `cli.py:68-80` records `actuals` for failing checks only. If you need
to audit abstentions, count them from the artifacts.

**Gotchas.**
- `source_url` and `id` are deliberately **not** compared. Real source URLs
  reference datasets by slug (`/v0/land_change/<slug>/analytics`), never by
  registry id, so with short numeric ids ("0"–"11") a token match against the
  URL would false-positive on date fragments — `11` is also a month in
  `start_date=2024-11-01` — and a non-match would false-negative every correct
  slug URL (`guards.py:121-129`).
- Presence is checked by key, not truthiness, because dataset id `0` is a real
  registry id (`guards.py:66-69`).
- 0.97 ±0.02 over 85 rows in `20260803T201245Z`.

## `state_delta`

**Not in this directory** — it lives in `runner/multiturn.py:45-81` — but it is
tagged as a retrieval check (`buckets.py:58`) and appears in ledgers as
`t<N>.state_delta`, so it belongs in this index.

**Measures** the state transitions a conversation turn asserts, against snapshots
built from the same `actual_*` diagnostics the validators read
(`SNAPSHOT_FIELDS`, `runner/multiturn.py:25-42`). Three assertion kinds:
`changed` (must differ from the previous turn), `retain` (must be identical —
context loss), `absent` (must be empty — carryover contamination).

**Fires on** a turn's `deltas:` block, and only from turn 2 onward (there is no
previous snapshot for turn 1: `runner/multiturn.py:122`).

**`null` vs `0.0`**: `null` when a delta names a field outside `SNAPSHOT_FIELDS`
— it abstains for the whole turn rather than half-checking
(`runner/multiturn.py:67-77`). `schema/case.schema.json` enums the same eight
field names and `tests/test_schema.py` enforces the sync, so a typo should fail
at authoring time rather than silently abstain at runtime. `0.0` when any
asserted transition fails.

**Reason**: `reasons.t<N>.state_delta`, a semicolon-joined list of concrete
transitions, e.g. `"dataset_id should have been retained: '4' -> '0'"`.

**Gotcha**: a turn that errors aborts the conversation, and the un-run turns
contribute **no checks at all** (`runner/multiturn.py:113-115`) — the row becomes
an `error`, not a partial measurement. 8 rows, 0.96 ±0.06 in
`20260803T201245Z`, flagged over-gate on small-n only.

---

# Analysis

## `class_value_match`

**Measures** the failure the headline judge structurally cannot see: a wrong
per-class sub-total hiding under a correct total. It parses
`"mangroves=15,444 hectares; other=3 ha"` into pairs
(`analysis_checks.py:48-62`), finds records whose *string* values contain the
class name, and compares the closest numeric value in those records against the
target within the shared 2% tolerance (`analysis_checks.py:98-114`).

**Fires on** `class_values` (6 `cases/v2` rows).

**Info-only** — see [the closing section](#info-only-checks-and-what-re-admission-requires).

**`null` vs `0.0`**: `null` when the expectation is malformed (any chunk without
`=`, or an empty name/value: `:50-61`, `:76-80`) and `null` when a class's value
text is unparseable by `parse_expected_number` (`:92-96`) — abstain rather than
half-check. `0.0` when there are **no data records at all** (`:83-86`), and
`0.0` when any single class misses (all-or-nothing across classes: `:116`).

**Reason**: none; `actual_class_values` carries either the findings string
(`"mangroves: closest 15,444.00 (0.00%)"` / `"short vegetation: no matching
record"`) or an abstention note. As with `pull_source_match`, abstention text
does not reach the ledger.

**Gotchas.**
- Class matching is **substring containment on any string field of the record**
  (`:98-104`), so a short class name can match the wrong record and a class name
  absent from the chart's own vocabulary reports `"no matching record"`. That is
  exactly the 1-015 finding in `results/recommendations/20260803T201245Z.md`
  item 8: after a prompt rewrite the chart became per-county rather than
  per-class, so the expectation is now unsatisfiable by construction.
- Records are drawn from both `charts_data[*].data` and the last statistics
  entry (`:21-37`), so a class can be satisfied by data the chart never plots.

## `chart_integrity`

**Measures** mis-joined record sets at source: every field an axis references
must be non-null in every record that has that key
(`analysis_checks.py:121-156`). Reference case **1-060** (run 6) zipped a state
ranking and a driver breakdown into one array, null-padding 3 of 10 records in
the pie's own axis fields, and the prose then quoted the wrong figure
(`analysis_checks.py:8-10`).

**Fires on** nothing — it is expectation-free and runs on any row that produced
charts.

**`null` vs `0.0`**: `null` only when there are no charts (`:126-127`); it is a
*chart* integrity check, so a chartless row is genuinely n/a — whether a chart
should have existed is `chart_produced`'s question. Otherwise `1.0`/`0.0`.

**Reason**: `reasons.chart_integrity`, e.g. `"chart 0 (pie): xAxis field 'driver'
is null in 3/10 records — mis-joined record sets"`. This is the most directly
actionable reason string in the suite; it names the chart index, its type, the
axis, the field, and the padding ratio.

**Gotchas.**
- Only `xAxis` and `yAxis` are inspected (`:140`), and only records that *have*
  the key with a `None` value count as padded — a record missing the key
  entirely is not a problem here (it is `chart_well_formed`'s, if the key is
  absent from every record).
- Deliberate overlap with `chart_well_formed`: a broken *spec* is an Output
  failure, a mis-joined *dataset* under a plausible spec is an Analysis failure
  (`output_checks.py:5-8`). The two reason strings read differently on purpose.
- **The most stable check in the suite**: 0.99, ±0.01 over 94 rows in
  `20260803T201245Z`, which is why
  `results/recommendations/20260803T201245Z.md` item 4 treats its verdict on
  1-043/1-060 as trustworthy enough to file upstream as the single
  highest-value fix.

---

# Analysis + Output (shared)

## `charts_answer`

**Measures**, since H5 (2026-08-03), exactly one thing: whether the chart's own
encoded data contains the figure the case expects, within the 2% relative
tolerance (`NUMERIC_TOLERANCE`, `llm_judges.py:18`). The gating verdict comes
from `chart_numeric.evaluate_numeric_support` (`chart_numeric.py:323-371`); the
Haiku appropriateness verdict is recorded but never gates
(`resolve_chart_verdict`, `llm_judges.py:237-292`).

This is the single most important behavioural change to know when reading a run
older than 2026-08-03. Previously the override was asymmetric — `unsupported`
forced 0, but `supported` only annotated the reason and the judge still decided.
Five of the six rows where `charts_answer` flapped across two 3-trial runs were
rows the comparator had already passed or abstained on, so 100% of the movement
was the judge's framing opinion. **1-059** is the proof: the chart's own data
contained the expected global total to 0.07%, the judge failed it twice on
framing ("the user would need to manually sum all regions"), then passed an
identical third trial (`llm_judges.py:243-263`).

**Fires on** `answer` **and** a non-empty serialised charts payload
(`answer_evaluator.py:171`).

**`null` vs `0.0`**: `null` when there is no numeric claim to check — a boolean,
a year, a bare place name, or a figure whose decimal separator is ambiguous
(`chart_numeric.py:99-144`). The row then carries no gating chart verdict at all
rather than a coin-flip aesthetic one. `0.0` when a numeric claim exists and the
chart's closest candidate exceeds tolerance, **including** when the chart data
holds no comparable figure at all (`chart_numeric.py:350-356`).

**Candidate figures** — what counts as "the chart contains it"
(`chart_numeric.py:300-320`):
- every numeric leaf, excluding label-ish keys (`year`, `month`, `date`, `id`,
  `index`, `order`, `position`, `rank`: `:45-58`);
- per-column sums and maxima of every list-of-records (`:167-202`) — a chart
  plotting 25 yearly values supports an expected period total it never draws;
- **cross-column row sums and their grand total** (H6, `:205-259`), for charts
  that split one quantity into several measure columns. Reference case
  **1-002**: São Paulo's alerts are plotted as `high_confidence` and
  `highest_confidence`, and the expected 1,299,278.14 ha is their sum, which was
  not a candidate at all — the row failed every trial while the agent's prose
  was right. Only record sets with ≥2 measure columns contribute, and the
  docstring is explicit that this widens the candidate set and is therefore more
  permissive by choice;
- per-column shares as percentages, **only** when the expected value is a
  percent (`:262-297`, `:318-319`).

**Reason**: `reasons.charts_answer` (note the ledger alias from
`chart_answer_score_reason`, `ledger.py:21`). Four shapes, and the wording tells
you which branch fired (`llm_judges.py:265-292`):
- `"deterministic check: the chart's closest figure to the expected 25,540,000 is
  25,521,080.13, a 0.07% difference, within the 2% tolerance. <judge reason>"` —
  comparator and judge agree;
- `"… — the judge (info-only) disagreed on framing: <judge reason>"` — passed on
  data, judge objected. Nothing to act on unless you are auditing the judge;
- `"… — overriding the judge (info-only), which said: <judge reason>"` — failed on
  data while the judge liked the chart. Act on the numbers;
- `"no numeric claim to check deterministically; not scored. Judge (info-only)
  said: <judge reason>"` — the `null` case.

**Gotchas.**
- `parse_expected_number` takes the **first** number in the `answer` cell and
  stops. A cell whose first number is a bare year abstains entirely (`2015-2020`
  → `null`), which is usually what you want — but a cell like
  `"In 2020, 25.5 Mha were lost"` parses the token `"2020,"`, which the
  `^(19|20)\d{2}$` year guard does *not* match because of the trailing comma, so
  the expected value becomes **2020** and the check compares that against the
  chart. No `cases/v2` row currently has that shape, so this is latent — but it
  is the reason expected answers should be the bare figure and nothing else.
- Sign is load-bearing and now handled (H1, `chart_numeric.py:68-74`): net-flux
  rows express a sink as a negative (1-055: `-286,994 Mg CO2e`), and dropping
  the minus compared +286,994 against a series holding −286,993.69 — an exact
  match reported as an 86.96% miss. The lookbehind stops a word-internal hyphen
  reading as a minus, so `Sentinel-2` yields +2 — the *sign* is fixed, not the
  extraction: a non-numeric expectation that happens to contain a digit still
  produces a numeric claim. Prefer `text` over `answer` for such expectations.
- Scale words are honoured before units (`"25.54 million hectares"` beside
  `"25 Mha"`: `:25-29`, `:135-139`); missing them was worth three false failures
  on the 2026-07-31 run.
- The charts payload handed to both halves is truncated safely — trailing charts
  dropped, then data rows halved, marked `"_truncated": true`, always parseable
  (`answer_evaluator.py:53-94`). The earlier blind 80k slice emitted invalid
  JSON, which `chart_numeric` read as "no candidates" and turned into a forced
  numeric failure (PR-04 F5).
- Post-H5 it evaluates on far fewer rows (26 vs 60) at 0.96 ±0.04, 2 flapping —
  the shrinkage is the `null` rule working as designed
  (`results/recommendations/20260803T201245Z.md` item 13). `tools/flakiness.py`
  still classifies it as **judged** because the registry marks the evaluator
  `kind="mixed"` (`registry.py:120`, `tools/flakiness.py:31-35`), so it is held
  to the 0.10 judged gate.

## `charts_answer_judge`

**Measures** what the Haiku chart judge thought — whether the chart set is an
appropriate and complete way to answer the query, judged on structure and
coverage only (the prompt forbids it from judging numbers,
`llm_judges.py:366-372`). It is written out of `resolve_chart_verdict` as
`judge_score` (`llm_judges.py:292`) and surfaced as its own ledger check
(`answer_evaluator.py:182`, `eval_types.py:86-87`).

**Fires on** exactly the same conditions as [`charts_answer`](#charts_answer):
`answer` set and a non-empty charts payload.

**Info-only**, born that way on 2026-08-03 (H5), and untagged for buckets — it
contributes to no bucket and to no verdict. Its whole purpose is to keep
measuring the surface that used to gate, so its reliability can be tracked
toward re-admission the way `answer_traceability`'s is
(`answer_evaluator.py:164-167`).

**`null` vs `0.0`**: `null` when `charts_answer` did not run at all, and `null`
when the judge call raised (the exception path records only
`charts_answer` in `judge_errors`; `answer_evaluator.py:183-185`). `0.0` when the
judge objected, `1.0` when it approved — including on rows where the deterministic
comparator abstained, which is the population that used to produce coin-flip
verdicts.

**Reason**: it has none of its own. The judge's sentence is embedded in
`reasons.charts_answer`, prefixed by which branch fired — look for
`"the judge (info-only) disagreed on framing"` (comparator passed, judge objected)
or `"overriding the judge (info-only), which said"` (comparator failed, judge
approved).

**Gotcha**: a `charts_answer` 1.0 beside a `charts_answer_judge` 0.0 is the
**expected, non-actionable** shape post-H5. It means the chart's data contains the
figure and the judge disliked the framing. Do not file it as a defect without
first checking whether the objection is the 1-059 pattern ("the user would need to
manually sum all regions"), which is a framing preference, not a data problem.
0.90 ±0.07 with 10 flapping rows over 64 in `20260803T201245Z`.

## `agent_answer`

**Measures** whether the final assistant message captures the expected answer,
judged by Haiku against a typed rubric — boolean, numeric, year, or named entity
(`ANSWER_JUDGE_PROMPT`, `llm_judges.py:46-104`; call at
`answer_evaluator.py:189-201`). This is the one place a judge *is* trusted with
arithmetic, and the trust is explicitly scoped: the tolerance formula and its
worked examples are interpolated from `NUMERIC_TOLERANCE` so prompt and constant
cannot drift (`llm_judges.py:9-44`), and the module comment records that this
judge does the arithmetic reliably while the chart judge does not.

**Fires on** `answer` **and** a non-empty final message text
(`answer_evaluator.py:191`).

**`null` vs `0.0`**: `null` with no `answer` expectation, and `null` when the
final message is empty — there is nothing to judge. `null` also on judge outage,
with `"JUDGE ERROR: …"` in the reason and the check name in `judge_errors`, which
makes the row an `error` (`:199-201`, `buckets.py:115-116`). Otherwise the
judge's 0/1.

**Reason**: `reasons.agent_answer` — one concise sentence from the judge, with
`answer_eval_type` decided internally (it is in the structured output but is not
persisted separately). `actuals.agent_answer` = the full final answer text,
trimmed to 300 chars.

**Gotchas.**
- Shared-tagged (analysis + explanation): a failure here cannot be attributed to
  a bucket, which is why bucket tables report dedicated and shared populations
  separately (`buckets.py:62-66`).
- The prose answer and the chart are scored independently, so
  `agent_answer` 1.0 with `charts_answer` 0.0 is the normal shape of "right
  prose, wrong or incomplete chart" — and `agent_answer` 1.0 with
  `answered_without_data` 0.0 is the 1-030 shape: a confident right-sounding
  answer with nothing behind it.
- 0.91 ±0.09 over 66 rows in `20260803T201245Z` — inside the judged gate but the
  loosest of the three judges.

---

# Explanation

## `expected_text_match`

**Measures** whether the answer contains a stated piece of information, or
satisfies a stated qualitative behaviour — terminology, caveats, resolution
statements, refusal wording (`llm_judge_expected_text`,
`llm_judges.py:416-479`). The prompt accepts semantic equivalence
("30 x 30 resolution" ↔ "30-meter by 30-meter pixels") and treats an
instruction-shaped expectation as satisfied if the response does the thing.

**Fires on** `text` (26 `cases/v2` rows) **and** a non-empty final message.

**`null` vs `0.0`**: `null` with no `text` expectation or an empty answer; `null`
on judge outage (row becomes `error`). `0.0` when the response omits,
contradicts, or only weakly implies the expectation.

**Reason**: `reasons.expected_text_match`, one judge sentence.
`actuals.expected_text_match` = the answer text.

**Gotchas.** `text` is the right home for behavioural and terminological
expectations that `answer` cannot express, but it is a judged surface: two
expectations in one `text` cell can disagree with each other. mt-007 is the
worked example — its `text` said the agent "maintains and re-confirms its
**original** figure" while its `answer` anchored a specific number that turn 1
did not reliably produce, so the two expectations passed on mutually exclusive
trials (`results/recommendations/20260803T201245Z.md` item 9). 0.92 ±0.04 over
25 rows.

## `answer_traceability`

**Measures** whether the headline number the prose asserts is derivable from the
charts shown beside it — the deterministic "does the answer mislead" check
(`explanation_checks.py:55-80`). Evidence from run 6: of 63 extractable headline
numbers, 15 were not traceable to the chart data, and 1-027's
"**679.16 hectares**" appears nowhere in its own chart — all of them scored
`agent_answer` 1.0 (`explanation_checks.py:10-12`).

**Fires on** nothing — expectation-free. It needs charts, a non-empty answer, and
a bolded claim.

**Info-only** — see [the closing section](#info-only-checks-and-what-re-admission-requires).

**`null` vs `0.0`**: `null` when there are no charts or no prose (`:61-64`), and
`null` when no bolded segment carries a parseable number **with a unit**
(`:66-69`). The unit requirement is the precision device: only `**bold**`
segments count as claims (the answer template bolds key findings), and a bold
segment must match `_MEASURE_RE` — a percent sign, or one of a fixed unit
vocabulary including `ha`/`hectares`/`hektar`, `km²`, `tonnes`, `MgCO2e`, and the
scale words (`:40-44`). Bare bold numbers are counts and ranks ("**2**
datasets", "top **5**") and were the dominant false-positive class in the first
live run. `0.0` when a claim exists and the chart data does not support it.

**Reason**: `reasons.answer_traceability` — the same `evaluate_numeric_support`
explanation string as `charts_answer` (`"deterministic check: the chart's closest
figure to the expected … is …, a …% difference, exceeding the 2% tolerance"`), or
`"no bolded numeric claim found"`. `actuals.answer_traceability` = the claim text.

**Gotchas.** Only the **first** qualifying bold claim is checked (`:47-52`) —
this is a headline check, not an audit of every figure. It inherits every
`parse_expected_number` abstention rule, so a multilingual row with locale
decimals is a `null`, never a guess. 0.90 ±0.05 over 86 rows in
`20260803T201245Z`.

## `web_fallback`

**Measures** whether an answer that was supposed to come from a data pull instead
cites the web — the second half of the 1-030 signal (`guards.py:107-117`).

**Fires on** the derived data-pull expectation **and** a non-empty answer.

**`null` vs `0.0`**: `null` when no pull was expected or the answer is empty.
`0.0` when the answer contains **any** link (`https?://…` or `www.…`) outside the
product's own domains (`guards.py:37-38`, `109-115`).

**Reason**: none; `actuals.web_fallback` = `actual_web_links`, up to five
deduplicated sorted links.

**Gotchas.**
- `_OWN_DOMAINS` is `("globalnaturewatch.org", "globalforestwatch.org")`. The
  second was added by H8 (2026-08-03): the product serves its own map tiles from
  `tiles.globalforestwatch.org` and links GFW dashboards for the same figures it
  just pulled, so flagging it made the guard's own premise false on 1-095, which
  had answered correctly from a real pull (`guards.py:29-36`).
- **`wri.org` deliberately still fires.** A `wri.org` citation is the blog-skill
  tell that 1-030 exists to catch, and it is a live finding: mt-007's turn 2
  fails `t2.web_fallback` on all three trials by citing WRI insight pages under
  pushback (`results/recommendations/20260803T201245Z.md` item 2).
- The check is link-shaped, not provenance-shaped. An answer that came entirely
  from web knowledge but cites nothing passes here; that is
  `answered_without_data`'s job. 0.97 ±0.01 over 69 rows.

---

# Output

## `chart_produced`

**Measures** the absence that used to be invisible: a row whose expected answer
implies a chart must produce one (`guards.py:97-98`, PR-04 F2). Before this,
"no chart" made `charts_answer` vanish to `null` and the row scored on its prose
alone — 1-004, 1-008, 1-030 and 1-055 all answered in prose with no chart at all
(`guards.py:8-9`).

**Fires on** `answer` **and** the derived data-pull expectation. The second
condition is what exempts a clarification row (`clarification: true` forces
`expects_data_pull()` false, `eval_types.py:272-273`) even though it may carry an
`answer`.

**`null` vs `0.0`**: `null` when either condition is absent; otherwise `1.0` if
`charts_data` is non-empty, `0.0` if not. There is no middle ground — this is a
presence check, and everything about the chart's quality belongs to
`chart_well_formed`, `chart_integrity`, and `charts_answer`.

**Reason**: none, and no `actuals` entry. A `0.0` here means literally
"`charts_data` was empty".

**Gotchas — read this one before filing anything.** `chart_produced` is currently
**the worst gating check in the suite**: 0.89, ±0.10, 14 flapping rows over 66 in
`20260803T201245Z`, sitting exactly on the admission gate. Two distinct
populations (`docs/specs/caseset-v2-improvement-plan.md` §5, "the other flake
engine"): cascade-driven rows (no pull → no chart), and ~6 standalone rows where
the agent pulls, answers correctly, and simply omits the chart (1-008, 1-012,
1-035, 1-048, 1-050, 1-069). No case edit fixes the second population — it needs
a product stance on whether data answers must always chart. **Both the plan §5
and `results/recommendations/20260803T201245Z.md` item 14 recommend demoting it
to info-only until that stance exists; the code has not done so.** It is in
`DEDICATED` and not in `INFO_ONLY` (`buckets.py:43`, `83-90`), so today it gates.
Treat a lone `chart_produced` flip as weak evidence.

## `chart_well_formed`

**Measures** expectation-free structural sanity: a chart with empty data, or
whose axis fields reference keys absent from its own records, renders as garbage
whatever the analysis computed (`output_checks.py:20-60`).

**Fires on** nothing — any row that produced charts.

**`null` vs `0.0`**: `null` only when there are no charts (`:27-28`). `0.0` for a
non-object chart entry, empty/absent record data, or an axis naming a field that
appears in no record.

**Reason**: `reasons.chart_well_formed`, semicolon-joined per problem, e.g.
`"chart 1 (pie): empty data; chart 1 (pie): xAxis references field 'driver'
absent from data"`.

**Gotchas.** `actual_max_pie_slices` is written when any pie chart exists — it is
surfaced for triage and deliberately **not** thresholded ("thresholded later if
noisy", `:58-59`), so it never affects the score. The overlap with
`chart_integrity` is intentional and the split is by cause: spec broken → Output,
data mis-joined → Analysis. 1.00 ±0.00 over 94 rows in `20260803T201245Z` — the
cleanest check in the suite, which also means a failure here is worth taking
seriously.

## `chart_type_match`

**Measures** whether the **first** chart's `type` is one of the accepted types
(`output_checks.py:63-85`).

**Fires on** `chart_type`, semicolon-separated alternatives, matched
case-insensitively. **No `cases/v2` case sets this field today**, so the check is
present but dormant — `cases/README.md` warns that chart type is the agent's most
nondeterministic surface and that a verdict should not be staked on it, so an
expectation here should always carry alternatives (`chart_type: "bar;table"`).

**`null` vs `0.0`**: `null` with no expectation. `0.0` when a chart-type
expectation exists and **no** chart was produced — a type expectation implies a
chart (`:77-80`). `0.0` on a type mismatch.

**Reason**: none; `actuals.chart_type_match` = `actual_chart_type`.

**Gotcha**: only `charts_data[0]` is inspected. A row whose second chart is the
expected one fails.

## `dashboard_created`

**Measures** whether a dashboard was created this turn, from
`agent_state["dashboard_id"]` (`dashboard_evaluator.py:9-45`).

**Fires on** `dashboard_created` (tri-state `true`/`false`/absent) — **and, on any
row, on an unsolicited dashboard.**

**`null` vs `0.0`** — the full table (`dashboard_evaluator.py:15-22`):
`expected=True/actual=True` → 1.0; `True/False` → 0.0; `False/False` → 1.0;
`False/True` → 0.0 (guardrail); **`None/True` → 0.0** (unsolicited creation is a
guardrail violation on a row that never mentioned dashboards); `None/False` →
`null`. That fifth row is the one to remember: this check can fail a case that
set no dashboard expectation at all.

**Reason**: none; `actuals.dashboard_created` = the boolean.

**Gotchas.** Shared-tagged (output + scope). Dashboards live behind the agent's
`experimental` tool profile: a run launched without `--ff experimental` scores
these rows 0.0 for the *run configuration*, not the agent
(`results/recommendations/20260803T201245Z.md` item 1 — the whole retraction is
worth reading, and the run_id suffix is the tell). In the flag-bearing partial
run `20260803T215155Z_staging_experimental` it was 1.00 ±0.00 over 9 rows; in
the flagless run, 0.22 ±0.00 over 9.

## `dashboard_aoi_match`

**Measures** that the created dashboard is scoped to exactly one AOI, and that it
is the AOI already under test on that row (`dashboard_evaluator.py:48-107`). It
deliberately reuses `aoi_ids`/`aoi_source` rather than introducing a
dashboard-specific column.

**Fires on** `aoi_ids` **and** a successfully fetched dashboard payload.

**`null` vs `0.0`**: `null` when the dashboard is `None` — no dashboard was
created, or the fetch failed and degraded softly rather than erroring the row
(`runner/api.py:142-166`) — and `null` when the row has no `aoi_ids`. `0.0` when
the dashboard has a number of AOIs other than exactly one (`:91-93`), or when the
single AOI's id or source mismatches.

**Reason**: none; `actuals.dashboard_aoi_match` = `actual_dashboard_aoi_id` and
`actual_dashboard_aoi_count`.

**Gotchas.** This is the **only** consumer of `aoi_source`
(`registry.py:160`); an empty `aoi_source` skips the source comparison
(`:103-105`). Id normalisation is `aoi_evaluator._normalize_aoi_ids`, so the
GADM level-suffix blindness described under
[`aoi_id_match`](#aoi_id_match) applies here too. A failed dashboard fetch is
indistinguishable in the ledger from "no dashboard created" — both are `null`
here — so check `actual_dashboard_created` and the run log's
`"Warning: failed to fetch dashboard"` line before concluding.

## `dashboard_widgets_match`

**Measures** widget composition as a **multiset**: order does not matter, counts
do (`dashboard_evaluator.py:159-161`).

**Fires on** `dashboard_widgets` (semicolon-separated, e.g. `insight;map` —
split by `eval_types.py:204-215`) **and** a fetched dashboard.

**`null` vs `0.0`**: `null` when the dashboard is `None` or no widget expectation
exists. `0.0` on any multiset difference, including a missing widget on an
otherwise-correct dashboard.

**Reason**: none; `actuals.dashboard_widgets_match` =
`actual_dashboard_widget_types`, the stringified list.

**Gotcha**: `dashboard_widgets` containing `insight` also switches on the whole
derived data-pull family (`eval_types.py:274-277`) — `data_pull_exists`,
`answered_without_data`, `web_fallback`. A map-only dashboard row does not.

## `dashboard_widgets_valid`

**Measures** whether each widget's content actually resolved, per type
(`_widget_is_valid`, `dashboard_evaluator.py:110-124`): an `insight` widget must
have a non-null `insight`; a `text` widget must have `config.text` (PR-04 F3 —
the API nests the markdown there; the flat `text` key is kept as a fallback for
older payloads); a `map` widget must have a `tile_url` under
`config.dataset` or `config.imagery`. Any **other** widget type returns invalid
(`:124`).

**Fires on** a fetched dashboard with at least one widget, **or** a
`dashboard_widgets` expectation that produced none.

**`null` vs `0.0`** — changed by H7 on 2026-08-03, and this is the version to
read (`dashboard_evaluator.py:163-181`):
- widgets present → `1.0`/`0.0` on their content;
- no widgets **and** widgets were expected → `0.0` (F3's real intent: content was
  requested and is missing);
- no widgets **and** nothing was expected → **`null`**. Previously `0.0`. 1-096's
  prompt is only *"Create a dashboard for brazil"* and sets no widget
  expectation, yet an empty dashboard failed it on 4 of 6 trials, and it passed
  only on trials where the agent volunteered an **unsolicited** text widget —
  while `dashboard_created` treats an unsolicited dashboard as a guardrail
  violation. The rule rewarded exactly what its sibling punished. The code
  comment also records the honest limitation: **there is no syntax for "expect
  zero widgets"** (an empty value parses to `None`, i.e. no expectation), so if
  the product stance really is "a created dashboard must never be empty", that
  needs its own check with its own spec decision.

**Reason**: none, and no `actuals` mapping — read `actual_dashboard_widget_types`
from the sibling check or the artifact's `dashboard_widgets`.

**Gotcha**: an unrecognised widget type fails the whole dashboard, because
`_widget_is_valid` returns `False` by default (`:124`). If the product adds a
widget type, this check will report it as invalid content — which is arguably the
right alarm, but it is a harness update, not an agent regression.

---

# Scope

## `clarification_requested`

**Measures** whether the agent asked for clarification instead of attempting the
task — judged from prose, because there is no state field for "asked a question"
(`clarification_evaluator.py:8-77`, `llm_judges.py:116-202`). The judge reads
`charts_data[0].insight` if present, else the final message
(`llm_judges.py:126-155`), and its prompt explicitly excludes the common
false positive: an answer followed by an optional offer to go further is **not**
a clarification (`llm_judges.py:179-184`).

**Fires on** `clarification`, parsed tri-state (`true`/`1`/`yes` → True,
`false`/`0`/`no` → False, empty → no expectation; `eval_types.py:8-32`).

**`null` vs `0.0`**: `null` when there is no expectation — the check is skipped
entirely before the judge is called (`:42-47`), which also saves the API call.
Otherwise `1.0` on a match and `0.0` on a mismatch in either direction: expected
clarification and got an attempt, or expected an attempt and got a question.
Judge outage → `null` + `judge_errors` → row becomes `error`
(`:57-63`); this used to be swallowed to `False`, which scored **1.0** on
`clarification: false` rows during outages (`llm_judges.py:199-202`).

**Reason**: **not persisted.** The judge's prose lands in
`clarification_explanation`, which matches neither the `_reason` nor the
`_score_reason` pattern (`ledger.py:51-58`), so it is dropped from the ledger
entry. `actuals.clarification_requested` = the boolean only. On a judge outage
the `"JUDGE ERROR: …"` text is lost the same way; only the check name in
`judge_errors` survives.

**Gotchas.** The judge's structured output puts `explanation` before
`is_clarification`, per the working agreement — Haiku commits to the first field
it emits and argues with itself otherwise (PR-04 F6,
`llm_judges.py:119-123`). Only 3 `cases/v2` rows set `clarification`, and at
±0.16 it was flagged over-gate in `20260803T201245Z`; with 3 rows that is a
small-n artifact, but the recommendation is explicit that it is below the
coverage floor and should either gain rows or be read as advisory
(`results/recommendations/20260803T201245Z.md` item 15).

## `suggested_datasets_match`

**Measures** whether the agent's `suggested_datasets` state field is a non-empty
**subset** of the allowed ids: at least one match, and nothing outside the
expected set (`suggested_datasets_evaluator.py:6-68`).

**Fires on** `suggested_datasets` (semicolon-separated). One `cases/v2` row sets
it.

**`null` vs `0.0`**: `null` with no expectation. `0.0` when the expectation exists
and the state field is empty (`:52-56`), and `0.0` when the suggestions are
not a valid non-empty subset.

**Reason**: none; `actuals.suggested_datasets_match` = the semicolon-joined ids.

**Gotcha — this is measuring a dead surface.** `scope_checks.py:41-46` records
that `suggested_datasets` was populated in **0 of 1,298** retained case-trials:
the `pick_aoi`/`pick_dataset` → nudge migration (wri/project-zeno#770) moved
suggestion onto the nudge surface, where `dataset_choice` appears 162 times. So
any row expecting suggestions here will score 0.0 for a product-shape reason,
not an agent failure. `classify_scope` was fixed for this (H4); this check was
not, and does not appear in `20260803T201245Z`'s flakiness table at all because
nothing evaluated it. Prefer `scope: suggest` and/or `nudge_type:
dataset_choice`.

## `nudge_match`

**Measures** the agent's nudge shape — the generic `nudge` state field
`{type, options}` written by `send_nudge` and by the `aoi_choice`/`dataset_choice`
migrations (`nudge_evaluator.py:35-121`). It is the deterministic substitute for
judged clarification detection whenever a case can name the nudge it expects.

**Fires on** `nudge_type` and/or `nudge_options`; either alone is enough, and
each is checked only if provided (`:89-113`).

**`null` vs `0.0`**: `null` only when neither is expected (`:82-87`) —
diagnostics are still extracted, because multi-turn delta snapshots and triage
need them on turns with no expectation. Otherwise `1.0` if the type check and
the options check both pass, `0.0` otherwise. An expectation on options with
**no** options offered is `0.0` (`:98-99`).

**Reason**: none; `actuals.nudge_match` = `actual_nudge_type` and
`actual_nudge_options`.

**Gotchas.** Both comparisons are deliberately loose, because for
`aoi_choice`/`dataset_choice` nudges the type *and* the option wording are
LLM-generated — only the literal `send_nudge`-with-fixed-args case is fully
deterministic (`nudge_evaluator.py:10-16`). `nudge_type` accepts `;`-separated
acceptable values; options match by case-insensitive substring containment **in
either direction** (`_option_matches`, `:22-32`), so `"Odisha, India"` matches
`"Puri, Odisha, India (District)"`. The options rule is subset-shaped: at least
one expected match, and every offered option must be within the expected set, so
an extra unexpected option fails the check. 6 rows, 0.94 ±0.08, flagged
over-gate on small-n.

## `scope_match`

**Measures** whether the agent did the right *kind* of work, classified
deterministically from state instead of from the suite's two flakiest judges
(`scope_checks.py:1-20`, `54-87`). Observable classes, in precedence order — an
agent that pulls data has analysed, whatever else it also did
(`classify_scope`, `:33-51`):

| class | condition |
|---|---|
| `analyse` | a data pull happened (`guards._data_was_pulled`) |
| `suggest` | `suggested_datasets` populated, **or** a `dataset_choice` nudge — no pull |
| `clarify` | any other nudge type — no pull |
| `none` | none of the above; matches an expected `refuse` (`:85`) |

The `dataset_choice` → `suggest` rule is H4 (2026-08-03) and is load-bearing: a
`dataset_choice` nudge *is* a dataset suggestion post-#770, and without this rule
every row expecting `suggest` failed on a field the product no longer writes, so
the "suggest" coverage the case set claimed was fictional (`:42-50`).
`aoi_choice` and friends remain `clarify` — a different class.

**Fires on** `scope` — 102 of the `cases/v2` expectation blocks set it, making
this the widest-firing scope check by far. `analyze` is accepted as an alias for
`analyse` (`:30`).

**`null` vs `0.0`**: `null` when no scope is expected, and `null` when **any**
alternative is invalid — the whole expectation abstains rather than silently
scoring on the remainder, because a typo must be loud, not lenient (`:76-81`).
`0.0` on a genuine class mismatch.

**`;`-alternatives** were added by H3 (`:59-65`): some rows are legitimately
either-way and a single pin makes them flap. 1-089 is the reference — its own
`text` expectation licenses two behaviours ("Refuses … **or** acknowledge and
caution that TCL is annual") and the agent does both across identical trials, so
`refuse;clarify` is the honest expectation.

**Reason**: none; `actuals.scope_match` = `actual_scope`, the observed class —
which makes triage a one-line read ("expected `suggest`, observed `analyse`").
The invalid-expectation abstention string is written to the same field but, being
a `null`, never reaches the ledger.

**Known limitation (S3, deferred, `:13-15`)**: on builds without `send_nudge` the
agent clarifies in prose and leaves the nudge state empty, which classifies as
`none`. Only populate `scope: clarify` on nudge-capable rows. Evidence it earns
its keep: 1-085 ("How do fires impact nature in Spain?") ran a full analysis
where the sheet expected dataset suggestions — caught here as expected `suggest`
vs observed `analyse` (`:17-19`). 0.94 ±0.05 over 88 rows in
`20260803T201245Z`.

---

# Info-only checks, and what re-admission requires

Four checks are reported and never enter a verdict (`buckets.py:83-90`). The
demotion rationale is recorded in the comments immediately above that frozenset
(`buckets.py:68-82`), and `tools/flakiness.py` labels them `info-only` instead of
holding them to a gate.

| Check | Demoted | Why | Re-admission requires |
|---|---|---|---|
| `date_coverage` | at design time | The state field it reads (`agent_state["start_date"]`) is inconsistent about what it records — the requested window, the dataset's full extent, or a rolling window ending today, for the same query (`data_pull_evaluator.py:1-17`). `date_extraction` is the scored date check. | Not stated in code. The blocker is a product-side change to what state records, not a threshold. |
| `answer_traceability` | 2026-08-01, after its first live run | Claim extraction misfired on unitless bold counts and ranks on ~5 of 9 failures. The unit-required rule (`explanation_checks.py:40-44`) now applies. | A 3-trial run with **zero** extraction false positives (PR-08 step 5). It ran 0.90 ±0.05 over 86 rows in `20260803T201245Z`. |
| `class_value_match` | 2026-08-01, after the first 3-trial run | Mean 0.25 over its 4 rows, whose expected values came from unverified sheet scratchpads — i.e. the check was reporting bad expectations, not bad behaviour. | W3's population review verifying the figures. Now 0.44 over 6 rows; two new figures came in verified (1-010's 110.10 ha, 1-027's 679.17 ha) and 1-015's is unsatisfiable against its rewritten chart shape (`results/recommendations/20260803T201245Z.md` item 8). |
| `charts_answer_judge` | born info-only 2026-08-03 (H5) | `charts_answer` is now gated on the deterministic comparator alone. Five of the six rows where `charts_answer` flapped over two 3-trial runs were rows the comparator had already passed or abstained on — all the movement was the judge's framing opinion — and `cases/README.md` forbids staking a verdict on chart choice. | std ≤ 0.10 over 3 trials. It ran **0.90 ±0.07 with 10 flapping rows** over 64 in `20260803T201245Z`, which is the direct measurement of what used to be gated. Item 13 of that run's recommendations says keep it info-only. |

Two notes on how info-only interacts with the rest of the machinery, both worth
knowing before you read a bucket table:

- `date_coverage` and `charts_answer_judge` are in neither `DEDICATED` nor
  `SHARED`, so `buckets_for` returns `()` and they contribute to no bucket.
  `answer_traceability` and `class_value_match` **are** in `DEDICATED`
  (explanation and analysis respectively), and `_tally`/`rows_covered` do not
  filter info-only (`buckets.py:127-160`) — so they *do* count toward those two
  buckets' pass/evaluated tallies and coverage while being excluded from row
  verdicts (`buckets.py:117-121`). Whether that asymmetry is deliberate is not
  stated anywhere in the code or specs; `tests/test_buckets.py` pins the
  tagging-completeness rule but not this interaction. Read bucket figures for
  analysis and explanation with it in mind.
- `implied_checks` never implies a conditional check — `charts_answer`,
  `web_fallback`, `pull_source_match`, the dashboard sub-checks, `date_coverage`
  — precisely so that every reconciliation miss is a real hole
  (`buckets.py:189-193`). A check being absent from the reconciliation line is
  not evidence that it ran. Note the matching asymmetry here: `implied_checks`
  *does* imply the info-only `class_value_match` from `class_values`
  (`buckets.py:221-222`), and `reconcile` counts it, while
  `tools/coverage_doc.py:76` strips info-only checks before reporting coverage —
  so the reconciliation line and the coverage doc are counting slightly
  different populations.

## Adding or changing a check

The two rules that bite hardest, both from `docs/specs/PLAN.md` §6:

1. Decide, and write down in the check's spec, whether an absence is `null` or
   `0.0`. Every section above exists because someone had to reconstruct that
   decision from behaviour.
2. Tag the check in `buckets.py` — `DEDICATED`, `SHARED`, or `INFO_ONLY`.
   `tests/test_buckets.py:17-24` asserts that every registered
   `*_score` field is tagged exactly once, so an untagged check fails the suite
   rather than quietly scoring into nothing.

Deterministic checks ship after a clean run against known-good rows; judged
checks ship info-only until they demonstrate std ≤ 0.10 over 3 trials
(`docs/specs/PLAN.md` §4). And whenever check semantics change, the next run must carry
`--note` — the after-every-run ritual in `CLAUDE.md` depends on it to keep a
`diff_runs` regression from being misread as an agent change.
