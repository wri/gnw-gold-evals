# What & why

<!-- One paragraph. For case edits: editing a case changes its uid, and this
     PR is the only record of why. Name the cases whose uids changed and the
     reason. -->

## Checklist

- [ ] `uv run pytest -q` green
- [ ] `uv run ruff check src tools tests` clean (the pinned ruff CI uses)

**Case edits only** (steps: "Changing cases" in `README.md`; authoring rules: `cases/README.md`):

- [ ] `uv run python tools/check.py --fix` run after every edit, so uids and the manifest match the cases
- [ ] `uv run python tools/coverage_doc.py` run, and `cases/v2/COVERAGE.md` committed with the edit
- [ ] `uv run python tools/audit_cases.py --strict` passes (CI runs the same; it fails on depth and DON'T violations)
- [ ] the four properties hold (capability-anchored, deterministic,
      checkable in depth, environment-honest)
- [ ] `env_gated` noted where the capability is environment-dependent

**Check-semantics changes only:**

- [ ] regression test reproducing the old defect
- [ ] whether a missing input scores `None` or `0.0` is stated in the check's docstring and its section of `src/goldset/evaluators/README.md`
- [ ] first post-merge run carries `--note` so diffs aren't read as agent movement
