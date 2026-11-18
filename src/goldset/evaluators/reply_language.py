"""Reply-language check: is the final reply in the case's language?

``reply_language_match`` tells English, Spanish and Indonesian apart by
counting each language's function words (articles, prepositions,
conjunctions) in the reply's prose. Function words carry the signal because
the rest of a Horizon reply does not: dataset names, units and numbers stay
in English whatever the reply's language, and place names keep their own.
No package and no model is involved, so the same reply always scores the
same.

Before counting, the reply loses what is not prose: fenced and inline code,
markdown table rows and URLs. Words are lower-cased runs of letters, so
numbers drop out.

The check is info-only (``buckets.INFO_ONLY``): a right answer in English
to a Spanish question does not mislead the user, so the wrong language is
reported as a rate beside the accuracy figures and never fails a question
(AJ, 2026-11-18).

Limits. Only the three languages are told apart: a reply in Portuguese
reads as Spanish and one in Malay as Indonesian, their nearest neighbours.
A place name can lend a few words to the wrong side ("Madre de Dios",
"La Paz"); ``MIN_RATIO`` absorbs that in any reply with real prose.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from goldset.canonical import LANGUAGES
from goldset.evaluators.answer_evaluator import extract_final_answer_text

# The leading language needs this many function words. Fewer is a reply too
# short to read ("Sí.", a bare figure, a one-line question): about two short
# sentences of prose reach it.
MIN_HITS = 4
# ...and this many times the runner-up's count. Below it the reply mixes two
# languages (a Spanish answer with an English paragraph) and neither is "the"
# reply language. Borrowed names stay far under it: measured Spanish and
# Indonesian replies quoting English dataset names lead by 10 to 1 or more.
MIN_RATIO = 2.0

# Words one of the three shares with another are left out ("a", "no", "me",
# "para", "per"), and so are words that double as a unit or sit in common
# place names ("ha" is hectares; "do" is in "Mato Grosso do Sul"; "all" is in
# a dataset name).
FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        "the of and to in is was for that with this it are as at by from be on "
        "an or which has have had were been between there these those its not "
        "but their more than also during over into about can would you your "
        "what how if we they most each where when while any some such other "
        "here does did will may only both".split()
    ),
    "es": frozenset(
        "de la el que en y los las del se por con una un es al lo como más su "
        "sus este esta estos estas entre son fue han sobre también pero desde "
        "hasta durante según está están hay sin cada donde cuando qué cuánto "
        "cuánta ese esa muy ya le les nos ser sido fueron tiene puede porque "
        "aunque ni".split()
    ),
    "id": frozenset(
        "yang dan di ini itu untuk dengan dari pada adalah tidak akan atau "
        "juga oleh dalam ke sebagai karena lebih telah sudah ada saya anda "
        "kami kita mereka tersebut bahwa antara secara terhadap hingga sejak "
        "selama namun tetapi jika dapat bisa merupakan sekitar seperti apa "
        "berapa atas hanya setiap serta yaitu sebesar sebanyak menjadi belum "
        "bukan lain saat sangat paling masih tentang kepada maupun "
        "bagi".split()
    ),
}
assert tuple(FUNCTION_WORDS) == LANGUAGES

_FENCED_CODE = re.compile(r"```.*?(```|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_TABLE_ROW = re.compile(r"^[ \t]*\|.*$", re.MULTILINE)
_URL = re.compile(r"(https?://|www\.)\S+")
_WORD = re.compile(r"[^\W\d_]+")


def prose_words(text: str) -> list[str]:
    """The reply's prose as lower-cased words: no code, tables or URLs."""
    # A decomposed accent would split "según" into two words.
    text = unicodedata.normalize("NFC", text or "")
    for noise in (_FENCED_CODE, _INLINE_CODE, _TABLE_ROW, _URL):
        text = noise.sub(" ", text)
    return [word.lower() for word in _WORD.findall(text)]


def detect_language(text: str) -> tuple[str | None, dict[str, int]]:
    """The reply's language, and each language's function-word count.

    ``None`` when no language reaches ``MIN_HITS`` or the leader has less
    than ``MIN_RATIO`` times the runner-up's count.
    """
    words = prose_words(text)
    hits = {
        language: sum(1 for word in words if word in vocabulary)
        for language, vocabulary in FUNCTION_WORDS.items()
    }
    # A stable sort, so a tie keeps LANGUAGES order; a tie is undecided anyway.
    (leader, top), (_second, runner_up) = sorted(
        hits.items(), key=lambda item: -item[1]
    )[:2]
    if top < MIN_HITS or top < MIN_RATIO * runner_up:
        return None, hits
    return leader, hits


def evaluate_reply_language(
    agent_state: dict[str, Any], language: str = "en"
) -> dict[str, Any]:
    """reply_language_match: the final reply is in the case's language.

    ``1.0`` when the detected language is the case's; ``0.0`` when it is
    clearly another of the three. ``null`` when there is no reply, or the
    reply is too short or too mixed to call (``MIN_HITS``, ``MIN_RATIO``).
    Those score ``null`` and not ``0.0`` because an undecided reply is no
    evidence of the wrong language: a ``0.0`` there would report "Sí." or a
    bare table as a reply in the wrong language and pull the rate down.
    """
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {LANGUAGES}, got {language!r}")
    result: dict[str, Any] = {
        "reply_language_match_score": None,
        "reply_language_match_reason": None,
        "actual_reply_language": None,
    }
    answer = extract_final_answer_text(agent_state.get("messages", []))
    if not answer.strip():
        return result
    detected, hits = detect_language(answer)
    counts = ", ".join(f"{code} {count}" for code, count in hits.items())
    result["actual_reply_language"] = detected
    result["reply_language_match_reason"] = (
        f"{detected or 'undecided'} (function words: {counts})"
    )
    if detected:
        result["reply_language_match_score"] = 1.0 if detected == language else 0.0
    return result
