"""Greetings, thanks and goodbyes: answered directly, without retrieval or the LLM."""

from __future__ import annotations

import re

_GREETING = re.compile(
    r"^(hi|hello|hey|hiya|good (morning|afternoon|evening)|greetings|servus|moin|hallo|"
    r"guten (morgen|tag|abend)|gr[uü](e)?(ß|ss) gott)\b",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^(thanks|thank you|thx|many thanks|cheers|danke|vielen dank)\b", re.IGNORECASE
)
_GOODBYE = re.compile(r"^(bye|goodbye|see you|tsch[uü]ss|ciao)\b", re.IGNORECASE)
# Phrases that may follow a greeting without turning it into a real question.
_FILLER = re.compile(
    r"^(there|everyone|all|signpost|bot|again|so much|a lot|very much|"
    r"i('m| am) new( here)?|i('m| am) (a )?new (student|here)|nice to meet you|"
    r"how are you( doing)?|that('s| is) (all|helpful|great)|"
    r"(that|this) helps?|it helped|for (the|your) help)$",
    re.IGNORECASE,
)

REPLIES = {
    "greeting": (
        "Hi, and welcome! I'm Signpost. I answer questions about arriving at DIT and settling "
        "in Deggendorf, using official public sources: enrolment, fees and re-registration, "
        "student ID and IT accounts, student housing, address registration, residence "
        "permits, health insurance, banking, student jobs and the broadcasting contribution. "
        "What would you like to know?"
    ),
    "thanks": "You're welcome! Let me know if you have another question.",
    "goodbye": "Goodbye, and good luck with your start in Deggendorf!",
}


def detect_smalltalk(message: str) -> str | None:
    """Return "greeting", "thanks" or "goodbye" for pure small talk, else None.

    A message counts as small talk only if, after the greeting words, nothing is left
    but filler such as "I am new here" - "Hi, how do I enrol?" is a real question.
    """
    text = message.strip()
    for kind, pattern in (("greeting", _GREETING), ("thanks", _THANKS), ("goodbye", _GOODBYE)):
        match = pattern.match(text)
        if not match:
            continue
        rest = text[match.end() :]
        parts = [p.strip() for p in re.split(r"[,.!?;:]+", rest) if p.strip()]
        if all(_FILLER.match(p) or _GREETING.match(p) or _THANKS.match(p) for p in parts):
            return kind
    return None
