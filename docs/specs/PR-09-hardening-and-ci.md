# PR-09 — Hardening and CI

## Goal

Close the defects and gaps *discovered while building PR-02..07* — each
verified against the code as written — and stand up the CI the tools were
designed for but which doesn't exist yet.

## The list (each item reproduced before fixing)

### H1 — CI workflow (the biggest absence)

`tools/check.py` was designed as a CI gate; nothing runs it. Add
`.github/workflows/ci.yml`: on push/PR — `uv sync`, `uv run pytest`
(includes the 115-file schema conformance sweep), `uv run python
tools/check.py`. Optional `workflow_dispatch` job: `gold run --env staging
--trials 3` + `diff_runs.py --fail-on-regression` against the latest
committed run — the release gate as a button. Add `ruff` (the repo has no
linter config; gnw-evals uses ruff via pre-commit — mirror it).

### H2 — Ingest can silently re-key drifted expectations

Found while seeding the ledger: the legacy-join fallback matches
`test_id` + exact query only. If a case's **expectations** changed since
the run but the query didn't, the run's results are attributed to the new
uid — exactly the misattribution the uid system exists to prevent. The
detailed CSV carries `expected_*` columns: compare them (normalised)
against the case's expectations during a test_id join; any mismatch →
`stale_case` with a `drift` field naming the columns. The seeded run-6
entry gets re-ingested under the rule.

### H3 — `merge_trials` drops non-final-trial errors

`merged = dict(entries[-1])` means a `judge_errors` or `error` recorded on
trial 1 or 2 vanishes if trial 3 was clean — an error row can read as
clean. Union `judge_errors` and join `error` strings across trials; a
conversation or row that errored in *any* trial must carry the evidence.

### H4 — Multiturn rows are invisible to reconciliation

`reconcile()` reads `case.expected`, which is empty for multi-turn cases —
they contribute zero implied checks, so a multiturn turn whose checks all
vanished would pass the reconciliation line silently (the §6.2 bug class,
reborn). Extend `implied_checks` to accept turns and emit `t<N>.`-prefixed
names; `state_delta` implied for any turn with a `deltas` block.

### H5 — report_run doesn't render multiturn detail

Failing conversations list flattened check names but not which query the
turn sent (`turns_detail` is stored but unrendered). Render per-turn query
+ failed checks for failing/errored multiturn rows.

### H6 — Artifact retention

`results/artifacts/` is gitignored and unbounded — a 3-trial full run
writes ~350 gzips, multiturn doubles per turn. Add `gold prune-artifacts
--keep-runs N` (default 5) and mention it in the CI dispatch job.

### H7 — `expected_dataset_id` cannot express legitimate alternatives

Inherited literally from gnw-evals: `"0;1"` compares as the literal string
and always fails, yet the case set has real defensible-either-way rows —
1-003's own `status_reason` documents the agent picking integrated alerts
(11) where the sheet expected DIST-ALERT (0), and it was parked "not
doing" for exactly this reason. We own the evaluator now: `;`-split
alternatives on `dataset_id` (match any), mirroring `nudge_type`
semantics. Unlocks the W4 triage in CASESET_PLAN.md; uid churn on the rows
that adopt it is intended.

## Acceptance criteria

- [ ] CI green on the stack tip; check.py failure and a schema violation
      each demonstrably fail a PR.
- [x] H2/H3/H4: regression test per item reproducing the original defect.
- [x] H7: evaluator + adapter + docs updated; 1-003 unparked with
      `dataset_id: "0;11"` and its status_reason trimmed.
- [x] report_run renders a failing multiturn row usefully (fixture test).

## Test plan

Unit tests per H-item; CI proves itself by running on this PR.
