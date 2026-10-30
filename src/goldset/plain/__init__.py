"""The plain baseline: Sonnet + web against Horizon on BENCHMARK, reply only.

Both assistants are judged on what the user reads: the four reply checks
(expected text, answer period, figure, figure claim) with the harness's own
evaluators, plus the accepted-nudge check where a fair choice is the right
answer. Figures are checked against reference tables fetched from the
analytics API, not against a pull of the assistant's own, because Sonnet has
none. Plan of record: the "Plain Sonnet on BENCHMARK" doc (AJ, 2026-10-30).

- ``reference``: which area and dataset a question asks about, fetched as of
  the day of the reply.
- ``sonnet``: one question to Sonnet 5.5 through the Messages API.
- ``judges``: the two new Haiku judgements (decline label, ask-back offer).
- ``score``: one attempt through the checks.
- ``outcome``: attempts and questions to right, wrong, declined, uncovered.
- ``overlay``: AJ's per-question calls on top of the frozen cases.
"""
