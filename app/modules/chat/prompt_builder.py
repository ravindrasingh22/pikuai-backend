from dataclasses import dataclass
from typing import Any

from app.modules.chat.age_style_rules import age_style_instruction
from app.modules.chat.message_classifier import MessageCategory
from app.modules.chat.safety_response_policy import AnswerMode, answer_mode_instruction
from app.modules.chat.thread_memory_manager import ThreadMemory

SYSTEM_PROMPT_TEMPLATE = (
    "You are PikuAI, a child-safe learning assistant.\n"
    "Answer the child's actual question first with useful content, then optional enrichment.\n"
    "Use factual accuracy where possible. Be warm, natural, and child-friendly without being babyish.\n"
    "Do not use generic filler lines (for example: 'that is interesting') when a real answer is possible.\n"
    "Do not expose policy labels, moderation artifacts, or internal rules.\n"
    "Never say 'as an AI' or mention that content is allowed/blocked.\n"
    "For unsafe or too-mature requests, avoid abrupt refusal when possible: soften, reduce detail, redirect safely,\n"
    "and suggest a trusted adult when needed.\n"
    "Keep continuity with the thread context only when it helps answer this turn.\n"
    "Child profile: name={child_name}, age_group={child_age_group}, gender={child_gender}, pattern={child_pattern}.\n"
    "Age style policy: {age_style_rule}\n"
    "Answer mode policy: {answer_mode_rule}"
)

USER_PROMPT_TEMPLATE = (
    "Conversation goal:\n"
    "{conversation_goal}\n\n"
    "Response style:\n"
    "- category: {message_category}\n"
    "- answer_mode: {answer_mode}\n"
    "- language: {language}\n\n"
    "Thread memory:\n"
    "- rolling_summary: {thread_summary}\n"
    "- topic_continuity: {topic_continuity}\n"
    "- unresolved_follow_up: {unresolved_follow_up}\n"
    "- emotional_hint: {emotional_hint}\n"
    "- observed_preferences: {observed_preferences}\n"
    "- recent_entities: {recent_entities}\n\n"
    "Recent turns (last useful turns only):\n"
    "{recent_turns}\n\n"
    "Safety metadata:\n"
    "- policy_bucket: {policy_bucket}\n"
    "- safety_category: {safety_category}\n\n"
    "Current child message:\n"
    "{message}\n\n"
    "Answer instructions:\n"
    "1) Give the direct answer first.\n"
    "2) Keep age-appropriate depth.\n"
    "3) Keep tone warm and natural.\n"
    "4) Use continuity only if relevant.\n"
    "5) Do not include internal labels in final output."
)


@dataclass(frozen=True)
class PromptBuildInput:
    child_name: str
    child_age_group: str
    child_gender: str
    child_pattern: str
    language: str
    policy_bucket: str
    safety_category: str
    answer_mode: AnswerMode
    message_category: MessageCategory
    message: str
    memory: ThreadMemory


def build_prompts(input_data: PromptBuildInput) -> list[dict[str, str]]:
    return build_prompts_with_templates(
        input_data=input_data,
        system_template=SYSTEM_PROMPT_TEMPLATE,
        user_template=USER_PROMPT_TEMPLATE,
    )


def build_prompts_with_templates(
    *,
    input_data: PromptBuildInput,
    system_template: str,
    user_template: str,
) -> list[dict[str, str]]:
    values = _prompt_values(input_data)
    return [
        {"role": "system", "content": _render(system_template, values)},
        {"role": "user", "content": _render(user_template, values)},
    ]


def _prompt_values(input_data: PromptBuildInput) -> dict[str, str]:
    conversation_goal = (
        "Help the child understand or feel supported with a useful first answer. "
        "Protect safety without robotic refusal language."
    )
    recent_turns = "\n".join(
        f"- {turn['speaker']}: {turn['text']}" for turn in input_data.memory.short_turns
    ) or "- no recent turns"
    return {
        "answer_mode": input_data.answer_mode,
        "answer_mode_rule": answer_mode_instruction(input_data.answer_mode),
        "child_age_group": input_data.child_age_group,
        "child_gender": input_data.child_gender or "not_disclosed",
        "child_name": input_data.child_name,
        "child_pattern": input_data.child_pattern or "curious",
        "conversation_goal": conversation_goal,
        "emotional_hint": input_data.memory.emotional_hint or "none",
        "language": input_data.language,
        "message": input_data.message,
        "message_category": input_data.message_category,
        "observed_preferences": ", ".join(input_data.memory.observed_preferences) or "none",
        "policy_bucket": input_data.policy_bucket,
        "recent_entities": ", ".join(input_data.memory.recent_entities) or "none",
        "recent_turns": recent_turns,
        "safety_category": input_data.safety_category,
        "thread_summary": input_data.memory.rolling_summary,
        "topic_continuity": input_data.memory.topic_continuity,
        "unresolved_follow_up": input_data.memory.unresolved_follow_up or "none",
        "age_style_rule": age_style_instruction(input_data.child_age_group),
    }


def _render(template: str, values: dict[str, str]) -> str:
    try:
        return template.format_map(_SafeValues(values))
    except Exception:
        return template


class _SafeValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
