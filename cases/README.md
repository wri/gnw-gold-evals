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

## Run-time ground truth (`ground_truth`)

A numeric case can name **which figure** it is about instead of **what value**
that figure has. The harness fetches the number from the analytics API before
any trial runs, so the case survives every data release with its uid — and its
regression history — intact.

```yaml
expected:
  aoi_ids: MDG.3.4_1
  aoi_source: gadm
  dataset_id: '4'
  ground_truth: sum(carbon_emissions_MgCO2e) WHERE tree_cover_loss_year=2019
  chart_type: bar
  scope: analyse
```

**Grammar** — `AGG(column)` or `AGG(column) WHERE column=value`, with `AGG` one
of `sum`, `max`, `min`, `count`. An explicit aggregate is **mandatory**: a bare
column would be ambiguous whenever the filter matches more than one row, which
is live (1-059 pulls 254 areas).

**No new request fields.** The request is built from expectations the case
already carries — `aoi_ids`, `aoi_source`, `dataset_id`, `context_layer`,
`dataset_parameters`, `start_date`, `end_date` — because a GOLD case already
asserts what query the agent should build. `ground_truth` is purely the
*response* side.

**Four rules, each with a case behind it:**

1. **The selector names the API's column, not the agent's.** The agent renames
   columns in its pandas codeact — 1-076's chart says `loss_area_ha` where the
   API says `area_ha` — so authoring from an artifact's `charts_data` is a trap.
   Read column names from project-zeno's `src/api/services/charts.py`, or from a
   raw `source_url` response.
2. **The metric is often not the obvious column.** 1-046 asks for "tonnes of
   CO2", which is `carbon_emissions_MgCO2e`. Picking `area_ha` would compare
   658,571 against 1,371.15 and report a 99.8% miss as an agent failure.
3. **On annual datasets the year goes in the selector, not the request.** The
   DON'T above still applies: the case carries no dates, the request uses the
   catalog's full window, and `WHERE tree_cover_loss_year=2019` does the
   narrowing.
4. **Spell the selector canonically**: lowercase aggregate function name,
   uppercase `WHERE`, unquoted filter value, no padding inside the expression:
   `sum(area_ha) WHERE year=2019`. Both spellings parse, but the **raw string is
   hashed into the uid**, so `where` and `WHERE` would mint two uids for the
   same test. `tools/audit_cases.py` enforces this and fails `--strict` on a
   selector that is spelled differently or does not parse at all; surrounding
   whitespace is stripped before hashing and is not flagged.

**The migration cost:**

1. **New uid.** Adding `expected.ground_truth` mints a new uid and restarts the
   case's history.
2. **Fewer checks.** `agent_answer`, `charts_answer` and `chart_produced` only
   run when `expected.answer` is present in the YAML, so removing that removes
   these checks. They are replaced by `ground_truth_match`, which is
   deterministic. The other new check is `ground_truth_answer`, which is
   informative only and never fails a row, since a gating check has to be
   deterministic.

The area identity must be explicit and resolvable: the fetch will not geocode
from the prompt, because that would redo the agent's own AOI resolution and let
an AOI regression silently corrupt the ground truth. A case with no `aoi_ids` or
no `aoi_source` aborts the run rather than guessing.

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
