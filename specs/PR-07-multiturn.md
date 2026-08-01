# PR-07 — Multiturn cases

## Goal

Measure conversational behaviour — the largest gap in the whole programme —
with GOLD-grade determinism: scripted two-turn cases, per-turn checks, and
state-delta assertions between turns.

## Why

Real users refine, follow up, and push back; the current runner mints a
fresh `thread_id` per case, so none of that is testable. The coverage
overview names multiturn as a known gap and no roadmap addresses it. The
API is already thread-native, so the mechanism is cheap: re-POST
`/api/chat` with the same `thread_id`, read state after each turn — every
existing validator then works per-turn unchanged.

(Also: remove the vestigial single-turn `thread_id` replay path inherited
from gnw-evals — it skips the POST but reads the state of a *fresh* uuid,
so it can never have worked.)

## Scope

**In:** multi-turn case format, runner loop, per-turn evaluation,
state-delta checks, 8 seed cases, ledger extension.

**Out:** LLM user-simulators (exploratory tooling, never scored — a
simulator's drift is indistinguishable from agent drift); conversations
longer than 2 turns (CHALLENGE territory); conversation-level judges
(consistency, correction-robustness) — specced there too, since they need
the judge-admission pipeline at scale.

## Design

### Case format

Multi-turn cases live beside single-turn ones with a `turns` list replacing
`query`/`expected`:

```yaml
id: mt-001
uid: <hash over every turn's query + expectations, in order>
status: ready
group: multiturn
turns:
  - query: "Show me deforestation in Puri"
    expected: {clarification: "TRUE"}
  - query: "Puri in Odisha, India"
    expected: {aoi_ids: "IND.26.20", dataset_id: "4", answer: "..."}
    deltas: {retain: [], changed: [aoi_ids]}
```

- The uid is order-sensitive over all turns (turn order is test content).
- **Determinism rule:** a turn's text may never depend on the agent's
  previous free text. Fixed strings only. One conditional is tolerated —
  *if* the state carries nudge options, send the expected option verbatim,
  else a fixed fallback line — because it branches on deterministic state,
  not prose.

### Runner

Same `thread_id` across turns; after each turn: fetch state, run that
turn's applicable validators, then the `deltas` assertions:

- `changed:` — the field must differ from the previous turn's state
- `retain:` — the field must be identical (catches context loss)
- `absent:` — the field must not appear (catches carryover contamination
  after a topic switch)

Ledger entries gain `turn` indices; the row verdict is the conjunction of
every turn's checks and every delta.

### The 8 seed cases (one per scenario class from the parent plan)

| id | Scenario | Buckets exercised |
|---|---|---|
| mt-001 | clarify → resolve | Scope, Retrieval |
| mt-002 | nudge → accept | Scope, Retrieval |
| mt-003 | refinement ("now 2021") | Retrieval (deltas: dates changed, AOI+dataset retained) |
| mt-004 | follow-up comparison | Analysis |
| mt-005 | ellipsis ("and for Indonesia?") | Retrieval |
| mt-006 | topic switch — contamination | Retrieval (deltas: absent) |
| mt-007 | correction robustness (push back on a *correct* figure) | Explanation — capitulation is a misleading event |
| mt-008 | scope escalation ("add that to a dashboard") | Output, Scope |

mt-007's turn-2 check is `expected_text` ("maintains the original figure,
cites the data") — judged, so it enters info-only per the admission rule.

## Acceptance criteria

- [x] Multi-turn uid covers all turns in order; reordering turns changes it.
- [x] Delta assertions unit-tested against synthetic state pairs.
- [x] Runner fixture test: 2-turn conversation against recorded responses.
- [ ] The 8 seed cases run 3 trials on staging; per-case flakiness recorded
      in the PR (expectation: a 2-turn row is at best as stable as its
      flakiest turn — quantify before growing the set).
- [x] Vestigial replay path removed.

## Test plan

Unit tests (uid, deltas, format validation) + fixture-driven runner test +
the 3-trial staging run committed to the ledger.
