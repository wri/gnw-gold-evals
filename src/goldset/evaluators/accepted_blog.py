"""Accepted-blog validator: some questions are fairly answered from a blog post.

AJ decided on 2026-10-26 (BENCHMARK draft-4 review of the 19 "why" questions
answered from blogs) that three of them are fairly answered by named WRI or
Land & Carbon Lab Insights posts, and the rest must be answered from data. A
case opts in with ``accept_blog_sources``: ``;``-separated article slugs (the
last path segment of the post's URL, so the WRI and LCL copies of one post
share a slug). A correct pull still passes, so the case has two paths and
each attempt is judged on the one it took:

- **blog path**: the attempt called ``search_blogs`` and pulled no data.
  ``accepted_blog_match`` passes when the final answer links at least one
  listed post. The checks that presuppose a pull (``PULL_PATH_CHECKS`` in
  ``buckets.py``) and the area check are not applicable: a blog answer needs
  neither a pull nor a chosen area.
- **pull path**: anything else. ``accepted_blog_match`` is ``null`` and the
  usual checks score, except that ``web_fallback`` ignores links to the listed
  posts (``guards.py``): citing a post the case accepts is not falling back
  to the web.

Like the accepted-nudge path, rows with an attempt on the blog path are judged
by the majority of attempt verdicts (``buckets.row_verdict``).
"""

from __future__ import annotations

from typing import Any

from goldset.evaluators.answer_evaluator import extract_final_answer_text
from goldset.evaluators.guards import _LINK_RE, _data_was_pulled
from goldset.evaluators.tool_checks import called_tool_names
from goldset.evaluators.utils import link_slug, parse_slugs

SEARCH_BLOGS = "search_blogs"


def blog_path(agent_state: dict[str, Any], accepted: Any) -> bool:
    """True when the attempt answered from search_blogs and pulled no data."""
    if not parse_slugs(accepted) or _data_was_pulled(agent_state):
        return False
    return SEARCH_BLOGS in called_tool_names(agent_state)


def evaluate_accepted_blog(agent_state: dict[str, Any], accepted: Any) -> dict[str, Any]:
    """Score 1.0 when the answer links a listed post, 0.0 when it links none.

    ``null`` when the row lists no posts and on the pull path (the pull checks
    speak for it). A blog-path answer with no links at all scores ``0.0``: the
    case accepts named posts, and an unattributed blog answer cannot be told
    apart from an invented one.
    """
    result: dict[str, Any] = {
        "accepted_blog_match_score": None,
        "actual_blog_sources_cited": None,
    }
    slugs = parse_slugs(accepted)
    if not blog_path(agent_state, accepted):
        return result
    answer = extract_final_answer_text(agent_state.get("messages", []))
    cited = sorted({link_slug(link) for link in _LINK_RE.findall(answer)})
    result["actual_blog_sources_cited"] = "; ".join(cited) or "no links in the answer"
    result["accepted_blog_match_score"] = 1.0 if slugs & set(cited) else 0.0
    return result
