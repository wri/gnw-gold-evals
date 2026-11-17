# What and why

<!-- One paragraph. Editing a case gives it a new uid, and this pull
     request is the only record of why: name each changed case and the
     reason. -->

## Checklist

- [ ] `uv run pytest -q` passes
- [ ] `uv run ruff check src tools tests generation` is clean

**Case changes** (commands: "After an edit" in `cases/README.md`):

- [ ] each changed case, and why it changed, is named above
- [ ] no case was changed to make it pass
- [ ] `tools/check.py --fix`, `tools/coverage_doc.py` and `tools/check_benchmark.py` ran, and their output is committed with the edit
- [ ] GOLD legacy copy only: `tools/audit_cases.py --strict` passes

**Runs, manifests and page data:**

- [ ] no smoke run or `--env local` run is committed; each committed run has its suite's after-run steps done
- [ ] regenerated files listed here (for example `results/index.json`, `COVERAGE.md`, a page)
- [ ] a BENCHMARK manifest changed? Say how: draft rebuilt, erratum, or freeze
- [ ] the page data shape changed? Link the matching project-zeno-next change

**Check semantics changes:**

- [ ] a regression test reproduces the old defect
- [ ] the check's docstring and its section of `src/goldset/evaluators/README.md` say whether a missing input scores `null` or `0.0`
- [ ] the first run after merge will carry `--note`
