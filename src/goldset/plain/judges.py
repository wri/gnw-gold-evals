"""The two judgements the plain baseline adds to the harness's own.

Same client as every harness judge (Haiku 4.5, temperature 0, structured
output with the reason before the verdict). Neither does arithmetic. Both
are new, so the pilot hand-checks them before the full run relies on them.

- ``label``: did the reply answer, decline, or ask the user to choose? And
  does it state its own figure for what was asked? A decline on a question
  that expects an answer is reported as Declined, never Right, even where a
  lenient text check would pass it; an answer that leaves out the asked
  figure (and says nothing wrong) is not a wrong figure.
- ``offers``: on a question where a fair choice is a right answer, does a
  prose ask-back offer every accepted option? Horizon's nudge is scored by
  ids (``accepted_nudge_match``); Sonnet has no nudge, so its prose is read.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

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
"answered". So is a reply that answers and then offers more, or ends with a
follow-up question ("Would you like me to show this for a specific area?"):
"asked_back" is only for a reply that asks before giving any answer. A reply that explains why the question cannot be answered as
asked, without answering it, is "declined". So is a reply that says it
cannot answer the core question and gives only background or related
context instead.

gives_figure: true when the reply states its own number for the quantity
the question asks about (an area, a count, a share, an emission, a change),
even if approximate. False when it gives no number for that quantity, only
numbers for other things (a related dataset, another period, another
place), or none at all.

Return:
- reason: one concise sentence on what the reply does
- label: "answered", "declined" or "asked_back"
- gives_figure: true or false
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
    gives_figure: bool


class _Offer(BaseModel):
    reason: str
    offers_all: bool


def _judge(prompt: str, schema: type[BaseModel], **inputs: Any) -> BaseModel:
    # Imported here so the module loads without an API key (tests stub these).
    from goldset.models import HAIKU

    chain = ChatPromptTemplate.from_messages([("user", prompt)]) | \
        HAIKU.with_structured_output(schema)
    return chain.invoke(inputs)


def label(query: str, reply: str) -> dict[str, Any]:
    judged = _judge(LABEL_PROMPT, _Label, query=query, reply=reply)
    return {"label": judged.label, "reason": judged.reason, "gives_figure": judged.gives_figure}


def offers(query: str, reply: str, options: list[str]) -> dict[str, Any]:
    judged = _judge(OFFER_PROMPT, _Offer, query=query, reply=reply,
                    options="\n".join(f"- {o}" for o in options))
    return {"offers_all": judged.offers_all, "reason": judged.reason}
