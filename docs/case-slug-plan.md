# Readable case slugs — plan

**Goal (2026-08-04):** replace `1-XXX` / `mt-YYY` with short, readable, easily
distinguished slugs, derived deterministically from the prompt.

**Recommendation: adopt slugs, but as a derived *display and filename* handle
alongside `id` — and freeze each slug at authoring time rather than recomputing it
from the prompt forever.** The readability win is real and cheap. Making the slug a
live function of the prompt text is the one part that would cost more than it
returns, for a reason this repo has just demonstrated at scale.

---

## 1. Why full-prompt determinism conflicts with a load-bearing property

`CLAUDE.md` defines the roles precisely:

> `uid` = `sha256(canonical_json(query + non-empty expected values))[:16]` … changing
> the prompt or any `expected` value mints a new uid — that is the versioning
> mechanism.
> `id` (the sheet's `test_id`) is **the stable lineage handle across versions**.

So the split is deliberate: **`uid` is content, `id` is identity.** A case's history
is `id` plus the sequence of uids git records for it. If the human-facing handle is
a pure function of the prompt, it moves whenever the prompt moves — and then the
repo has *no* stable handle at all.

This is not hypothetical. The 2026-08-03/04 improvement cycle rewrote prompts on
**32 cases in a single programme**. Under prompt-derived slugs, every one would
have been renamed mid-flight, and each rename would have invalidated:

- the case's own filename and git blame continuity,
- every cross-reference in `docs/caseset-v2-improvement-plan.md`, four
  `results/recommendations/*.md`, and a dozen commit messages,
- the `test_id` join that `tools/import_sheet.py` and
  `tools/export_sheet_csv.py` use to round-trip with the team's sheet
  (`import_sheet.py:112`, `export_sheet_csv.py:194`),
- `cases/v1`, which is frozen by `tests/test_v1_frozen.py` precisely so
  improvement claims stay measurable against a fixed baseline.

Worse, the rename would be *silent about why*: `sao-paulo-alerts-high-conf` →
`sao-paulo-alerts-high-and-highest` reads like a different test rather than the same
test at a new version. The uid already carries "this is a new version" honestly.

**Conclusion:** derive the slug from the prompt (deterministic, no bikeshedding, no
hand-naming), but **freeze it in the file at creation**. Regeneration becomes an
explicit, reviewable act rather than a side effect of fixing a typo.

---

## 2. The slug format

```
<aoi>-<metric>-<qualifier>          e.g.  sao-paulo-alerts-h2-2024
                                          brazil-tcl-trends
                                          welsh-counties-short-veg-2024
                                          uk-net-ghg-flux-vs-ireland
mt-<slug>                           e.g.  mt-puri-clarify-resolve
                                          mt-indonesia-tcl-pushback
```

Derivation, deterministic and implemented once in
`src/goldset/slugs.py`:

1. Lowercase the prompt (turn 1's prompt for multi-turn), strip punctuation.
2. Drop stopwords and eval-boilerplate: articles, `how much`, `what`, `which`,
   `show me`, `true or false`, `in`, `of`, `the`, `between`, `was`, `did`, `there`.
3. Map a small controlled vocabulary of long metric names to stable abbreviations —
   `tree cover loss` → `tcl`, `greenhouse gas` → `ghg`, `disturbance alerts` →
   `alerts`, `short vegetation` → `short-veg`, `natural grassland` → `grassland`.
   This is the only hand-maintained part, it lives in one dict, and it is what makes
   the slugs short *and* recognisable.
4. Take the first 3–5 surviving tokens, hyphenate, cap at 40 characters.
5. Prefix `mt-` for multi-turn, preserving the existing visual distinction.
6. On collision, append `-2`, `-3`, … in `id` order, so collision resolution is
   itself deterministic and does not depend on insertion order.

Group stays in the directory path, as now — `cases/v2/<group>/<slug>.yaml` — so it
does not need repeating in the slug.

---

## 3. What changes, and what does not

| | today | after |
|---|---|---|
| lineage handle | `id: 1-002` | `id: 1-002` — **unchanged** |
| content hash | `uid` | `uid` — **unchanged**, still covers query + expected |
| filename | `cases/v2/direct/1-002.yaml` | `cases/v2/direct/sao-paulo-alerts-h2-2024.yaml` |
| new field | — | `slug:` — frozen at creation, **not** part of the uid |
| CLI selection | `--id 1-002` | `--id 1-002` *or* `--id sao-paulo-alerts-h2-2024` |
| ledger entries | `id`, `uid` | `id`, `uid`, `slug` (additive; existing runs stay valid) |
| reports | `1-002` | `sao-paulo-alerts-h2-2024` with `1-002` shown small |
| sheet round-trip | `test_id` ↔ `id` | **unchanged** |
| `cases/v1` | frozen | **untouched** — slugs land in v2 only |

`slug` must be excluded from the uid hash, like `status`, `group` and `notes`. That
is a one-line addition to the `canonical.py` exclusion set and a test asserting a
slug change leaves `caseset_version` untouched — the same proof Phase 0 used for
notes.

---

## 4. Sequencing

**S1 — `src/goldset/slugs.py` + tests.** Pure function, no I/O. Test: determinism,
the abbreviation vocabulary, collision suffixes, multi-turn prefixing, and stability
under trivial prompt edits (`"was impacted"` → `"was affected by"` must **not**
change a frozen slug, but *would* produce a different slug if regenerated — assert
both, so the freeze is a deliberate documented behaviour).

**S2 — `slug` field.** Add to `Case`, the schema, and the canonical-hash exclusion
set. Assert `caseset_version` is unchanged by adding slugs to every case — that is
the safety proof for the whole migration.

**S3 — `tools/slugify_cases.py`.** Populates `slug` for every case in `cases/v2`,
renames files with `git mv` so blame follows, and prints the mapping. Idempotent.
Ships with the generated `docs/case-slug-map.md` (old id → slug), which is what makes
every historical cross-reference in the repo still resolvable.

**S4 — Reader tolerance.** `--id` accepts either handle; `store.load_store` reads
both filename styles. Land *before* the rename so nothing has a broken window.

**S5 — The rename commit.** Mechanical, `git mv` only, no content edits, so it
reviews as a pure rename and `caseset_version` provably does not move.

**S6 — Display.** Reports, `render_inspector.py`, `diff_runs.py`, `flakiness.py`
and `coverage_doc.py` lead with the slug and keep `id` as secondary. Ledger writing
gains `slug` — additive, so `validate_run` accepts old runs unchanged.

**S7 — Rubric.** `cases/README.md` gains the naming rule, and a `--check` mode in
`slugify_cases.py` for CI that flags a case whose slug is missing (but **not** one
whose slug has drifted from its prompt — that drift is legitimate and expected).

---

## 5. The reslug escape hatch

When a prompt changes so much that the slug is actively misleading —
`brazil-tcl-2010` for a row now asking about 2000 — regenerate deliberately:

```bash
uv run python tools/slugify_cases.py --reslug 1-056 --reason "query moved to the 2000 baseline"
```

That writes the new slug, `git mv`s the file, appends to `docs/case-slug-map.md`, and
requires the reason, which lands in the commit. One reviewable act, never a side
effect.

---

## 6. Risks

- **Two handles to learn.** Mitigated by `id` retreating to small print everywhere
  except the sheet round-trip; most people will only ever type slugs.
- **Slug drifts from its prompt over time.** Accepted, and cheaper than the
  alternative: a stale-but-stable name beats a name that renames on every edit. The
  `--reslug` path exists for when drift becomes misleading.
- **The abbreviation vocabulary is hand-maintained.** Kept to one dict, and only
  additive — changing an existing mapping would retroactively alter derivations, so
  treat that dict as append-only.
- **Renames obscure history for tools that do not follow them.** `git mv` plus
  `git log --follow` handles the repo; `docs/case-slug-map.md` handles the docs and
  the committed ledgers, which keep their `id` values regardless.

---

## 7. Alternative considered and rejected

**Slug replaces `id` outright, always recomputed from the prompt.** Simplest mental
model — one handle — and it is what "deterministic based on the prompt" implies most
literally. Rejected because it deletes the lineage property `CLAUDE.md` calls out
explicitly, breaks the sheet `test_id` join in both directions, and would have
renamed 32 cases during a single improvement cycle. The uid already exists to say
"the content changed"; the human handle should say "this is still the same test".
