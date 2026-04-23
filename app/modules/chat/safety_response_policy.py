from typing import Literal

from app.modules.chat.message_classifier import MessageCategory

AnswerMode = Literal[
    "quick_answer",
    "guided_learning",
    "comforting",
    "playful",
    "parent_safe_redirect",
]


def normalize_answer_mode(mode: str | None) -> AnswerMode:
    if mode in {"quick_answer", "guided_learning", "comforting", "playful", "parent_safe_redirect"}:
        return mode
    if mode in {"short_answer", "short answer"}:
        return "quick_answer"
    if mode in {"learn_more", "learn more", "give example", "explain simply"}:
        return "guided_learning"
    return "quick_answer"


def select_answer_mode(
    requested_mode: str | None,
    category: MessageCategory,
    policy_bucket: str,
) -> AnswerMode:
    if policy_bucket in {"block_and_redirect", "escalate"}:
        return "parent_safe_redirect"

    normalized_requested = normalize_answer_mode(requested_mode)
    if normalized_requested != "quick_answer":
        return normalized_requested

    if category == "emotional_support":
        return "comforting"
    if category == "imaginative_play":
        return "playful"
    if category in {"factual_learning", "follow_up_question", "body_growth"}:
        return "guided_learning"
    return "quick_answer"


def answer_mode_instruction(answer_mode: AnswerMode) -> str:
    if answer_mode == "quick_answer":
        return "Give the minimum useful direct answer first. Keep it tight and clear."
    if answer_mode == "guided_learning":
        return "Give a direct answer, then one tiny example or analogy to deepen understanding."
    if answer_mode == "comforting":
        return "Lead with emotional grounding, then one practical next step the child can try."
    if answer_mode == "playful":
        return "Keep it light and imaginative while still giving a useful response."
    return (
        "Use safe redirection: give a brief partial answer when safe, avoid explicit detail, "
        "and suggest involving a trusted adult."
    )
