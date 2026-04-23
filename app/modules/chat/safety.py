import re
from typing import Literal, TypedDict

AgeBand = Literal["3-5", "6-8", "9-11", "11-13", "14-17"]
PolicyBucket = Literal["allowed", "allowed_with_adaptation", "block_and_redirect", "escalate"]


class ModerationDecision(TypedDict):
    category: str
    severity: int
    reason_codes: list[str]
    policy_bucket: PolicyBucket


def classify_input(message: str) -> ModerationDecision:
    if re.search(r"\b(kill myself|suicide|self harm|hurt myself)\b", message, re.IGNORECASE):
        return {
            "category": "self_harm_indicator",
            "severity": 95,
            "reason_codes": ["SELF_HARM_LANGUAGE"],
            "policy_bucket": "escalate",
        }

    if re.search(r"\b(bomb|weapon|poison|kill|hurt|hack)\b", message, re.IGNORECASE):
        return {
            "category": "dangerous_instruction_attempt",
            "severity": 85,
            "reason_codes": ["DANGEROUS_INSTRUCTIONS"],
            "policy_bucket": "block_and_redirect",
        }

    if re.search(r"\b(baby|babies|period|puberty|private parts)\b", message, re.IGNORECASE):
        return {
            "category": "sensitive_but_answerable",
            "severity": 45,
            "reason_codes": ["SENSITIVE_TOPIC"],
            "policy_bucket": "allowed_with_adaptation",
        }

    return {
        "category": "safe_learning",
        "severity": 10,
        "reason_codes": ["SAFE_LEARNING"],
        "policy_bucket": "allowed",
    }


def render_answer(message: str, age_band: str, bucket: str) -> str:
    if bucket == "escalate":
        return (
            "That sounds really hard. Please talk to a trusted adult near you right now. "
            "I can stay with safe, calm words while you get help."
        )

    if bucket == "block_and_redirect":
        return (
            "I cannot help with dangerous instructions. We can learn safe science instead, "
            "like how volcanoes, magnets, or rockets work."
        )

    if bucket == "allowed_with_adaptation":
        if age_band in {"3-5", "6-8"}:
            return "That is a grown-up topic. A parent or trusted adult can explain it in the right way for you."
        return (
            "That topic can be sensitive, so here is a simple safe version: bodies and families "
            "can be different, and a trusted adult can help explain details."
        )

    topic = _topic_hint(message)
    if age_band == "3-5":
        return f"Good question about {topic}. It works because tiny parts of nature follow patterns. We can explore one step at a time."
    if age_band == "6-8":
        return f"Great question about {topic}. A simple way to think about it is that causes create effects, like clues in a story."
    return f"Good question about {topic}. The short answer is that science and evidence help explain it clearly, and we can go deeper next."


def _topic_hint(message: str) -> str:
    words = [word.strip(".,!? ").lower() for word in message.split()]
    filtered = [word for word in words if word and word not in {"why", "what", "how", "is", "are", "do", "does", "can"}]
    if not filtered:
        return "this topic"
    return " ".join(filtered[:4])
