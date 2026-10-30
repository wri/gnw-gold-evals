"""The two judgements the plain baseline adds to the harness's own.

Same client as every harness judge (Haiku 4.5, temperature 0, structured
output with the reason before the verdict). Neither does arithmetic. Both
are new, so the pilot hand-checks them before the full run relies on them.

- ``label``: did the reply answer, decline, or ask the user to choose?
  A decline on a question that expects an answer is reported as Declined,
  never Right, even where a lenient text check would pass it.
- ``offers``: on a question where a fair choice is a right answer, does a
  prose ask-back offer every accepted option? Horizon's nudge is scored by
  ids (``accepted_nudge_match``); Sonnet has no nudge, so its prose is read.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

LABELS = ("answered", "declined", "asked_back")

LABEL_PROMPT = """
You are classifying how an assistant replied to a user's question about
forest, land or nature data. Judge only what the reply does, not whether it
is correct.

QUESTION:
{query}

REPLY:
{reply}

label, one of:
- "answered": the reply answers the question: it gives a figure, a finding,
  a yes or no, a ranking, or an explanation that addresses what was asked,
  even if hedged, approximate or partly from general knowledge.
- "declined": the reply does not answer. It says it cannot access or does not
  have the data, or it only tells the user where or how to look it up.
- "asked_back": the reply does not answer yet. It asks the user to choose or
  clarify something (which place, which dataset, which period) first.

A reply that gives an answer and also suggests where to check it is
"answered". A reply that explains why the question cannot be answered as
asked, without answering it, is "declined".

Return:
- reason: one concise sentence on what the reply does
- label: "answered", "declined" or "asked_back"
"""

OFFER_PROMPT = """
A user asked an assistant a question, and the assistant replied by asking
the user to choose before answering. A fair choice must offer every option
in this list; offering other options as well is fine.

QUESTION:
{query}

OPTIONS THAT MUST ALL BE OFFERED:
{options}

REPLY:
{reply}

Return:
- reason: one concise sentence naming any listed option the reply leaves out
- offers_all: true if the reply offers every listed option, otherwise false
"""


class _Label(BaseModel):
    reason: str
    label: Literal["answered", "declined", "asked_back"]


class _Offer(BaseModel):
    reason: str
    offers_all: bool


def _haiku():
    # Imported here so the module loads without an API key (tests stub these).
    from goldset.models import HAIKU

    return HAIKU


def label(query: str, reply: str) -> dict[str, str]:
    chain = ChatPromptTemplate.from_messages([("user", LABEL_PROMPT)]) | \
        _haiku().with_structured_output(_Label)
    judged = chain.invoke({"query": query, "reply": reply})
    return {"label": judged.label, "reason": judged.reason}


def offers(query: str, reply: str, options: list[str]) -> dict[str, object]:
    chain = ChatPromptTemplate.from_messages([("user", OFFER_PROMPT)]) | \
        _haiku().with_structured_output(_Offer)
    judged = chain.invoke({"query": query, "reply": reply,
                           "options": "\n".join(f"- {o}" for o in options)})
    return {"offers_all": judged.offers_all, "reason": judged.reason}
