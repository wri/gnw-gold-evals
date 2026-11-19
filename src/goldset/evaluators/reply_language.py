"""Reply-language check: is the final reply in the case's language?

``reply_language_match`` tells English, Spanish, Indonesian, Portuguese and
French apart by counting each language's function words (articles,
prepositions, conjunctions) in the reply's prose. Function words carry the
signal because the rest of a Horizon reply does not: dataset names, units
and numbers stay in English whatever the reply's language, and place names
keep their own. No package and no model is involved, so the same reply
always scores the same.

Before counting, the reply loses what is not prose: fenced and inline code,
markdown table rows and URLs. Words are lower-cased runs of letters, so
numbers drop out.

The check is info-only (``buckets.INFO_ONLY``): a right answer in English
to a Spanish question does not mislead the user, so the wrong language is
reported as a rate beside the accuracy figures and never fails a question
(AJ, 2026-11-18).

Italian is a decoy: it is counted so that an Italian reply is reported as
such (``it``) and scores 0.0 against every case language, and it is never a
case's language. Without it an Italian reply reads as French and would pass
a French case.

Spanish, Portuguese, French and Italian share many function words ("de",
"que", "la"). A word that two lists hold does not count when those two
languages are compared (see ``detect_language``).

A case that sets no language is English, but the older non-English questions
in the stores cannot take a ``language`` without a new uid. When such a
case's own query is clearly not English, its reply is not scored (null), as
the expected language is unknown.

Limits. Only the case languages and Italian are told apart: a reply in any
other language is undecided or reads as its nearest neighbour, and Malay
still reads as Indonesian. A place name can lend a few words to the wrong
side ("Madre de Dios", "La Paz"); ``MIN_RATIO`` absorbs that in any reply
with real prose.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from goldset.canonical import LANGUAGES, require_language
from goldset.evaluators.answer_evaluator import extract_final_answer_text

# The leading language needs this many function words. Fewer is a reply too
# short to read ("Sí.", a bare figure, a one-line question): about two short
# sentences of prose reach it.
MIN_HITS = 4
# ...and this many times the runner-up's count. Below it the reply mixes two
# languages (a Spanish answer with an English paragraph) and neither is "the"
# reply language. Borrowed names stay far under it: measured Spanish and
# Indonesian replies quoting English dataset names lead by 10 to 1 or more.
# Plainly Portuguese and French replies lead their runner-up (often Spanish)
# by at least 4.2 and 9.7 to 1 in 95% of them, medians 8 and 24 (Horizon's
# replies to external users to 2026-10-19).
MIN_RATIO = 2.0

# English, Spanish and Indonesian leave out the words one of them shares with
# another ("a", "no", "me", "para", "per"), and words that double as a unit
# or sit in common place names ("ha" is hectares; "do" is in "Mato Grosso do
# Sul"; "all" is in a dataset name). Portuguese and French share too many
# words with Spanish and with each other to leave them out ("de", "que",
# "entre"), so their lists hold them as the Spanish one does, and the ratio
# ignores a word that both compared lists hold. These two lists were the
# decoys' until 2026-11-19, unchanged: over Horizon's replies to external
# users to 2026-10-19, they read every reply that is plainly Portuguese (164)
# or French (513) as such, and no Spanish reply as either.
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
    "pt": frozenset(
        "o os as um uma uns umas do da dos das no na nos nas num numa em com "
        "não nem é são foi foram era eram ser sido está estão tem têm há mais "
        "mas também já ainda muito muitos seu sua seus suas esse essa isso "
        "isto ao aos à às pelo pela pelos pelas que se de por para entre "
        "sobre como quando onde porque então e ou ele ela eles elas nós "
        "você vocês".split()
    ),
    "fr": frozenset(
        "le la les l un une des du de d et est sont était être que qui "
        "dans pour par sur avec sans sous au aux ce cet cette ces ne pas "
        "plus ou où mais donc car comme aussi très il elle ils elles nous "
        "vous je tu sa son ses leur leurs qu à y entre selon ont a été "
        "dont lors chez vers".split()
    ),
}
assert tuple(FUNCTION_WORDS) == LANGUAGES

# Decoy languages: counted, never a case's language. They may share words
# with another list; ``detect_language`` ignores shared words when it
# compares two languages.
DECOY_WORDS: dict[str, frozenset[str]] = {
    # Italian shares enough words with French, Spanish and Portuguese ("la",
    # "il", "con") to read as one of them. It lists the words it shares with
    # French and Spanish, so the ratio ignores them. "di", "e", "da" and "in"
    # are left out: their count alone makes Italian the runner-up in
    # Indonesian, Portuguese and English replies, which changes how those
    # are compared.
    "it": frozenset(
        "il la le lo gli un una del della delle degli dello dei nel nella "
        "nelle negli nello alla alle agli allo dal dalla dalle dagli dai sul "
        "sulla sulle sui con su a che è sono erano essere stato stata stati "
        "anche più questo questa questi queste quello quella quelli tra "
        "perché quindi però molto ogni dove hanno ho".split()
    ),
}
_VOCABULARIES = {**FUNCTION_WORDS, **DECOY_WORDS}

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

    The language is one of ``LANGUAGES`` or the decoy ``it``.
    ``None`` when no language reaches ``MIN_HITS`` or the leader has less
    than ``MIN_RATIO`` times the runner-up's count. That ratio leaves out the
    words both languages list.
    """
    words = prose_words(text)
    hits = {
        language: sum(1 for word in words if word in vocabulary)
        for language, vocabulary in _VOCABULARIES.items()
    }
    # A stable sort, so a tie keeps listed order. When every word the two
    # share is all the leader has, listed order alone made it the leader;
    # the own-word check below leaves that reply undecided.
    (leader, top), (second, _next) = sorted(
        hits.items(), key=lambda item: -item[1]
    )[:2]
    shared = _VOCABULARIES[leader] & _VOCABULARIES[second]
    leader_own = _VOCABULARIES[leader] - shared
    second_own = _VOCABULARIES[second] - shared
    own = sum(1 for word in words if word in leader_own)
    runner_up = sum(1 for word in words if word in second_own)
    if top < MIN_HITS or own == 0 or own < MIN_RATIO * runner_up:
        return None, hits
    return leader, hits


def evaluate_reply_language(
    agent_state: dict[str, Any], language: str = "en", query: str = ""
) -> dict[str, Any]:
    """reply_language_match: the final reply is in the case's language.

    ``1.0`` when the detected language is the case's; ``0.0`` when it is
    clearly another language. ``null`` when there is no reply, or the reply
    is too short or too mixed to call (``MIN_HITS``, ``MIN_RATIO``).
    Those score ``null`` and not ``0.0`` because an undecided reply is no
    evidence of the wrong language: a ``0.0`` there would report "Sí." or a
    bare table as a reply in the wrong language and pull the rate down.

    An Italian (decoy) reply scores ``0.0``; an ``en`` case whose ``query``
    reads as another language scores ``null`` with a reason (see the module
    docstring).
    """
    require_language(language)
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
    query_language = detect_language(query)[0] if language == "en" else None
    if query_language not in (None, "en"):
        result["reply_language_match_reason"] += (
            f"; not scored: the query reads as {query_language} but the case "
            "sets no language"
        )
    elif detected:
        result["reply_language_match_score"] = 1.0 if detected == language else 0.0
    return result
