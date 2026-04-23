import re
from typing import Literal

from app.modules.chat.age_style_rules import normalize_age_band

MessageCategory = Literal[
    "factual_learning",
    "imaginative_play",
    "emotional_support",
    "social_relationship",
    "body_growth",
    "risky_sensitive",
    "greeting_smalltalk",
    "follow_up_question",
]

RISKY_PATTERN = re.compile(
    r"\b(mix|tablets?|pills?|medicine|drug|bomb|weapon|poison|hack|kill|hurt)\b",
    re.IGNORECASE,
)
BODY_PATTERN = re.compile(
    r"\b(babies?|baby|period|puberty|pregnan|body|private parts|sex)\b",
    re.IGNORECASE,
)
EMOTIONAL_PATTERN = re.compile(
    r"\b(scared|afraid|sad|lonely|anxious|worried|cry|upset|angry)\b",
    re.IGNORECASE,
)
SOCIAL_PATTERN = re.compile(
    r"\b(friend|friends|classmate|teacher|mom|dad|brother|sister|ignored|talking to me)\b",
    re.IGNORECASE,
)
PLAY_PATTERN = re.compile(
    r"\b(dance|pretend|dragon|unicorn|magic|game|joke|sing|story)\b",
    re.IGNORECASE,
)
GREETING_PATTERN = re.compile(
    r"\b(hi|hello|hey|how are you|good morning|good night)\b",
    re.IGNORECASE,
)
FOLLOW_UP_PATTERN = re.compile(
    r"\b(what about|and then|why that|how so|tell me more|also|then what|sunset)\b",
    re.IGNORECASE,
)


def classify_message(message: str, age_band: str, has_recent_context: bool) -> MessageCategory:
    text = message.strip()
    if not text:
        return "greeting_smalltalk"

    normalized_age = normalize_age_band(age_band)
    if RISKY_PATTERN.search(text):
        return "risky_sensitive"
    if BODY_PATTERN.search(text):
        return "body_growth" if normalized_age in {"11-13", "14-17"} else "risky_sensitive"
    if EMOTIONAL_PATTERN.search(text):
        return "emotional_support"
    if SOCIAL_PATTERN.search(text):
        return "social_relationship"
    if FOLLOW_UP_PATTERN.search(text) and has_recent_context:
        return "follow_up_question"
    if PLAY_PATTERN.search(text):
        return "imaginative_play"
    if GREETING_PATTERN.search(text):
        return "greeting_smalltalk"
    if text.endswith("?"):
        return "factual_learning"
    return "factual_learning"
