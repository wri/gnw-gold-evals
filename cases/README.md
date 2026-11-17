# Cases: the shared reference

What every case store under `cases/` shares: the stores, the case file and its fields, what `;` means in an expected value, the status lifecycle, and the commands to run after an edit. This file owns the after-edit commands. Terms are in the [glossary](../docs/glossary.md).

How to write a good case depends on the store:

- **CHALLENGE**: [challenge/README.md](challenge/README.md) has the doctrine and how cases get into the store. Numeric cases are generated through [generation/README.md](../generation/README.md).
- **GOLD legacy copy**: [GOLD-AUTHORING.md](GOLD-AUTHORING.md). Write new GOLD cases in project-zeno `evals/gold/`.

## The stores

| Store | Suite | Layout | Notes |
|---|---|---|---|
| `cases/challenge/` | CHALLENGE, and the source of every BENCHMARK member | `<set>/<cohort>/<id>.yaml` | The working store. Tools that take `--suite` default to it. |
| `cases/v2/` | GOLD legacy copy | `<group>/<id>.yaml` | The GOLD working set. |
| `cases/v1/` | GOLD legacy copy | `<group>/<id>.yaml` | Frozen: `tests/test_v1_frozen.py` fails if it changes. |

Each store has its own `MANIFEST.json`, written by `tools/check.py --fix`, with the store's [caseset_version](../docs/glossary.md#caseset-version) and an index from id to uid. `cases/challenge/` and `cases/v2/` also have a generated `COVERAGE.md`, `coverage.json` and `cases_index.json`, written by `tools/coverage_doc.py`. `cases/challenge/TARGETS.yml` holds CHALLENGE's target rates and is edited by hand.

## The case file

One case is one YAML file. `schema/case.schema.json` defines its fields, and `tests/test_schema.py` checks every case file against it. `src/goldset/store.py` reads the files and rejects a top-level key it does not know. A CHALLENGE case, `cases/challenge/aoi/direct/ch-aoi-001.yaml`:

```yaml
id: ch-aoi-001
uid: d368c2c205c3e822
status: ready
set: aoi
group: direct
query: Go to Japan
expected:
  aoi_ids: JPN
notes:
  difficulty: easy
  behaviour: select
  lineage: baseline
  verify_query: Japan
  verified: prod-api 2026-09-01
  source_tab: challenge-aoi-v1
```

| Field | Hashed into the uid | What it holds |
|---|---|---|
| `id` | no | The stable, human-readable name: `ch-aoi-001` or `ch-quant-161` in CHALLENGE, `1-030` or `mt-005` in GOLD. It survives edits, so it links every version of one test. |
| `uid` | it is the hash | Written by `tools/check.py --fix`. Never edit it by hand. |
| `status` | no | `ready`, `todo`, `done` or `not doing`: see [Status lifecycle](#status-lifecycle). |
| `set` | no | CHALLENGE only: the kind of question, such as `aoi`, `dataset` or `quantification`. It is the first directory level. |
| `group` | no | The case's directory. In CHALLENGE it is the cohort within the set: a prompt class in `aoi`, a dataset in the numeric sets. In GOLD it is the capability the case tests. |
| `query` | yes | The user's question. It may hold a `{template}` token, filled in when the run starts. |
| `turns` | yes | A multi-turn case has a list of `{query, expected, deltas}` instead of `query` and `expected`. In `cases/v2` the `deltas` are hashed too. Only GOLD has multi-turn cases today. |
| `expected` | yes, every non-empty value | The values a correct answer must contain, each a string. Each key switches on one or more checks: the [check index](../src/goldset/evaluators/README.md#index) says which. |
| `notes` | no | Annotations, never hashed or scored. |

Editing the query, a turn or any expected value gives the case a new uid. Editing its status, set, group or notes never does. The full rules and their reasons are in [CLAUDE.md, The identity system](../CLAUDE.md#the-identity-system).

**CHALLENGE notes.** No code scores them, but people and some tools read them:

- `difficulty`: `easy`, `medium` or `hard`. BENCHMARK sampling stratifies by it, and a version fixes it per member.
- `behaviour`: the correct behaviour the case expects, such as `select`, `nudge`, `clarify` or `decline`.
- `verified`, `lineage`, `source_tab`: how the expected values were verified, where the case came from, and which seed CSV `tools/import_sheet.py` read it from.
- `expectations`, `review`: who drafted the expected values from which seed CSV, and the evidence for each later change.
- `status_reason`: why a case is `todo` or `not doing`, with a date.
- BENCHMARK membership notes: `benchmark_id`, `benchmark_type` and the benchmark sheet row's facets. `tools/benchmark_from_sheet.py` writes them on every curated build, so a hand edit is overwritten, and drops `benchmark_id` and the sheet facets from cases that leave the sheet. The current sheet's facets are `use_cases`, `engagement`, `aoi_type`, `capability`, `grounding`, `synthetic`, `user_story_refs` and `refresh_risk`. The older sheet used `jtbd` (jobs to be done), `impact_pathway` and `user_groups`.

GOLD's notes, such as `env_gated` and `sentinel`, are described in [GOLD-AUTHORING.md](GOLD-AUTHORING.md).

<a id="semicolons"></a>
## `;` alternatives by field

A `;` inside an expected value does not mean the same thing in every field. Check this table before you write one.

| Field | `a;b` means | How it is matched |
|---|---|---|
| `dataset_id` | any of | the dataset the agent chose must be one of the alternatives; for `pull_source_match`, so must the one it pulled |
| `scope` | any of | the observed scope must be one of them; one invalid alternative makes the check abstain |
| `nudge_type` | any of | the nudge's type must be one of them |
| `chart_type` | any of | the first chart's type must be one of them |
| `aoi_ids` | all of | the set of resolved AOI ids must equal the expected set exactly; GADM ids are compared without their `_N` suffix. `\|` separates alternative sets, and `/` lists one area's equivalent records (below) |
| `class_values` | all of | every `name=value` pair must match within the 2% tolerance |
| `dashboard_widgets` | all of, with counts | widget types are compared as a multiset: `insight;insight;map` means exactly two insight widgets and one map widget |
| `nudge_options` | allowed set | the agent must offer at least one option, and every option it offers must match one in the list: a case-insensitive substring, either way round |
| `suggested_datasets` | allowed set | as `nudge_options`; legacy, because the agent no longer writes this state field |
| `forbidden_tools` | all of | no tool in the list may appear among the agent's tool calls |
| `accept_nudge_offering`, `accept_aoi_nudge_offering` | all of | a nudge passes when it offers every listed id; extra options are allowed |
| `accept_blog_sources` | any of | an answer from `search_blogs` passes when it links at least one listed post |
| `figure` | all of | each `;`-separated figure is checked on its own |
| any other field, such as `answer`, `text` or a date | nothing special | the value is used whole. In `answer` the judge reads `a;b` as written, so a reply that merely names both values can pass |

`|` separates fair alternatives, any one of which passes, in `aoi_ids`, `context_layer`, `accept_nudge_offering` and `figure`. It binds looser than `;`. In `aoi_ids`, `/` lists one area's equivalent records inside a `;` set: `555697863/10906;2017` is two parks, the first under either of two records. The [evaluators README](../src/goldset/evaluators/README.md#index) documents both with each check.

## Status lifecycle

Every case has one of four statuses:

- `ready`: written and expected to run. In CHALLENGE a case that fails stays `ready`: failure is data, and there is no verified-passing status. In GOLD, `ready` also means not yet verified at its current uid.
- `todo`: held by a known problem. A dated `notes.status_reason` says what blocks it, such as a seeded test account the case needs, or an expected value not yet pinned.
- `done`: GOLD only. The case is verified at its current uid ([Promoting to done](#promoting-to-done)).
- `not doing`: parked in GOLD, retired in CHALLENGE. Runs skip it, and `notes.status_reason` says why.

Which statuses run:

- `--suite challenge` skips `not doing` and `todo` by default, because `todo` cases are not pinned yet.
- `--suite gold` skips only `not doing`, so `ready` and `todo` cases are run and scored like `done` ones. The progress line prints each case's status, so a failure on an unverified case reads differently.
- A BENCHMARK version takes only `ready` cases as members, and a `--benchmark` run ignores status.
- `--status-exclude` overrides the default.

COVERAGE.md and the audit count every case except `not doing` as active. COVERAGE.md lists every `todo` and `not doing` case with its reason ([CHALLENGE](challenge/COVERAGE.md#parked-and-held-cases), [GOLD](v2/COVERAGE.md#parked-and-held-cases)).

**Parking.** Set `status: not doing` when a case cannot earn a verdict. Always write a dated `notes.status_reason` with the evidence: which run, what the agent did on how many trials, and why no prompt edit can fix it, or what would. `cases/v2/parent-child/1-011.yaml` is a good example. Notes are never hashed, so parking does not change the uid.

**Unparking.** Treat it as probation: re-test the reason the case was parked, and do not assume it is fixed. An edit that does not touch that reason leaves the case parked. For example, closing the date window on a case parked for an ambiguous area does not unpark it. An unparked case returns as `ready` or `todo`.

## After an edit

After any change to a case file, run these for the store you changed, and commit their output in the same commit as the edit. A change is any edit to the query, expected values, status, set, group or notes, or a new or deleted case.

```bash
uv run python tools/check.py --fix --suite challenge      # uids and MANIFEST.json
uv run python tools/coverage_doc.py --suite challenge     # COVERAGE.md, coverage.json, cases_index.json
uv run python tools/check_benchmark.py                    # BENCHMARK members still match their cases
```

`check_benchmark.py` matters because an edit to the query or an expected value of a member case gives it a new uid, so the BENCHMARK version that lists it no longer runs it. The tool warns on a draft and fails on a frozen version. CI runs all three without `--fix` and fails the pull request when one is out of date.

**GOLD legacy copy.** Edit `cases/v2` only. Run `check.py --fix --suite gold` and `coverage_doc.py --suite gold` instead of the first two commands, then `uv run python tools/audit_cases.py --strict`. The audit is described in [GOLD-AUTHORING.md, The audit gate](GOLD-AUTHORING.md#the-audit-gate).

**A member of a BENCHMARK draft.** When the edited case is a member of a benchmark draft, the steps continue in [challenge/README.md, After an edit](challenge/README.md#after-an-edit). A draft warning from `tools/check_benchmark.py` fails CI: `test_committed_manifests_are_clean` in `tests/test_check_benchmark.py` requires every committed manifest to report no errors and no warnings.

## The catalogue snapshot

`cases/zeno_catalog.json` is a committed copy of the agent's dataset catalogue, `src/agent/datasets/catalog/*.yml` in wri/project-zeno. COVERAGE.md measures dataset coverage against it without network access. It also holds each dataset's analytics endpoint and date window, from which ground-truth requests are built.

When project-zeno adds, removes or changes a dataset:

```bash
uv run python tools/sync_zeno_catalog.py               # reads origin/main of ../project-zeno
uv run python tools/coverage_doc.py --suite challenge
uv run python tools/coverage_doc.py --suite gold
```

Commit the three outputs together. The sync fetches, then reads the ref with `git show`, so it never touches the project-zeno working tree. `--zeno` and `--ref` change the checkout and the ref. The `sync-catalog` skill walks the steps and reads what changed in coverage.

## GOLD legacy copy only

Only GOLD cases use the features below today. The harness supports them for every store.

### Run-time ground truth (`ground_truth`)

A numeric case can name **which figure** it is about instead of **what value** that figure has. The harness fetches the number from the analytics API before any trial runs, so the case survives every data release with its uid, and its result history stays intact.

```yaml
expected:
  aoi_ids: MDG.3.4_1
  aoi_source: gadm
  dataset_id: '4'
  ground_truth: sum(carbon_emissions_MgCO2e) WHERE tree_cover_loss_year=2019
  chart_type: bar
  scope: analyse
```

**Grammar.** `AGG(column)` or `AGG(column) WHERE column=value`, with `AGG` one of `sum`, `max`, `min` or `count`. The aggregate is mandatory: a bare column would be ambiguous whenever the filter matches more than one row, and that happens. Case 1-059 pulls 254 areas.

**No new request fields.** The request is built from the expectations the case already carries: `aoi_ids`, `aoi_source`, `dataset_id`, `context_layer`, `dataset_parameters`, `start_date` and `end_date`. A case already asserts what query the agent should build, so `ground_truth` covers only the response side.

**Four rules, each with a case behind it:**

1. **The selector names the API's column, not the agent's.** The agent renames columns in its pandas code: 1-076's chart says `loss_area_ha` where the API says `area_ha`. So authoring from an artifact's `charts_data` is a trap. Read column names from project-zeno's `src/api/services/charts.py`, or from a raw `source_url` response.
2. **The metric is often not the obvious column.** 1-046 asks for "tonnes of CO2", which is `carbon_emissions_MgCO2e`. Picking `area_ha` would compare 658,571 against 1,371.15 and report a 99.8% miss as an agent failure.
3. **On annual datasets the year goes in the selector, not the request.** GOLD's rule against date expectations on annual datasets still applies ([GOLD-AUTHORING.md, DON'Ts](GOLD-AUTHORING.md#donts)). The case carries no dates, the request uses the catalogue's full window, and `WHERE tree_cover_loss_year=2019` does the narrowing.
4. **Spell the selector canonically**: a lowercase aggregate, an uppercase `WHERE`, an unquoted filter value and no padding inside the expression, as in `sum(area_ha) WHERE year=2019`. Both spellings parse, but the raw string is hashed into the uid, so `where` and `WHERE` would mint two uids for the same test. `tools/audit_cases.py --strict` fails on a selector that is spelled differently or does not parse. Surrounding whitespace is stripped before hashing and is not flagged.

**The cost of moving a case to ground truth:**

1. **A new uid.** Adding `expected.ground_truth` mints a new uid and restarts the case's history.
2. **Fewer checks.** `agent_answer`, `charts_answer` and `chart_produced` run only when the case has `expected.answer`, so removing it removes them. The deterministic `ground_truth_match` replaces them. The other new check, `ground_truth_answer`, is info-only, because a gating check has to be deterministic.

The area must be explicit and resolvable. The fetch will not find the area from the prompt, because that would redo the agent's own area resolution and let an area regression corrupt the ground truth unseen. A case with no `aoi_ids` or no `aoi_source` aborts the run rather than guess.

### Promoting to `done`

A GOLD case is `done` when its row verdict is `pass` at its current uid on a 3-trial run with the same `ff` as the release baseline, which today is the default profile. Cite the run_id and date in `notes.status_reason`, for example `promoted to done <date>: passed at this uid on run <run_id>, 3 trials, default profile`. A 1-trial pass is a smoke signal, not verification. An edit that mints a new uid ends the verification: set the case back to `ready` until it passes again.
