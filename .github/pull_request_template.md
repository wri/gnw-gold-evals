# What & why

<!-- One paragraph. For case edits: why did the semantics change?
     uid churn is the record — name what moved and the reason. -->

## Checklist

- [ ] `uv run pytest -q` green
- [ ] `uvx ruff check src tools tests` clean

**Case edits only** (see `cases/README.md`):

- [ ] `uv run python tools/check.py --fix` run after every edit (uids truthful)
- [ ] `uv run python tools/audit_cases.py` — no new depth or DON'T violations
- [ ] the four properties hold (capability-anchored, deterministic,
      checkable in depth, environment-honest)
- [ ] `env_gated` noted where the capability is environment-dependent

**Check-semantics changes only:**

- [ ] regression test reproducing the old defect
- [ ] `None`-vs-`0.0` absence semantics stated in the spec/docstring
- [ ] first post-merge run carries `--note` so diffs aren't read as agent movement
