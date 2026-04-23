from dataclasses import dataclass
from typing import Any

from app.modules.chat.message_classifier import MessageCategory, classify_message
from app.modules.chat.prompt_builder import PromptBuildInput, build_prompts_with_templates
from app.modules.chat.safety_response_policy import AnswerMode, select_answer_mode
from app.modules.chat.thread_memory_manager import ThreadMemory, build_thread_memory, memory_to_json
from app.modules.llm.client import (
    DEFAULT_SYSTEM_PROMPT_TEMPLATE,
    DEFAULT_USER_PROMPT_TEMPLATE,
    LlmResult,
    generate_with_runtime_prompt,
    get_llm_runtime_config,
)


@dataclass(frozen=True)
class ChildResponseContext:
    child_age_group: str
    child_gender: str
    child_name: str
    child_pattern: str
    language: str
    policy_bucket: str
    safety_category: str
    requested_answer_mode: str | None
    fallback_text: str
    message: str
    recent_messages: list[dict[str, Any]]
    previous_memory: dict[str, Any] | None


@dataclass(frozen=True)
class ChildResponseResult:
    llm: LlmResult
    category: MessageCategory
    answer_mode: AnswerMode
    memory: ThreadMemory
    prompts: list[dict[str, str]]


def generate_child_response(context: ChildResponseContext) -> ChildResponseResult:
    memory = build_thread_memory(context.recent_messages, context.previous_memory)
    category = classify_message(
        message=context.message,
        age_band=context.child_age_group,
        has_recent_context=memory.has_recent_context,
    )
    answer_mode = select_answer_mode(
        requested_mode=context.requested_answer_mode,
        category=category,
        policy_bucket=context.policy_bucket,
    )
    runtime_config = get_llm_runtime_config()
    prompts = build_prompts_with_templates(
        input_data=PromptBuildInput(
            child_name=context.child_name,
            child_age_group=context.child_age_group,
            child_gender=context.child_gender,
            child_pattern=context.child_pattern,
            language=context.language,
            policy_bucket=context.policy_bucket,
            safety_category=context.safety_category,
            answer_mode=answer_mode,
            message_category=category,
            message=context.message,
            memory=memory,
        ),
        system_template=runtime_config.get("system_prompt_template") or DEFAULT_SYSTEM_PROMPT_TEMPLATE,
        user_template=runtime_config.get("user_prompt_template") or DEFAULT_USER_PROMPT_TEMPLATE,
    )
    llm = generate_with_runtime_prompt(messages=prompts, fallback_text=context.fallback_text)
    return ChildResponseResult(
        llm=llm,
        category=category,
        answer_mode=answer_mode,
        memory=memory,
        prompts=prompts,
    )


def response_metadata(result: ChildResponseResult) -> dict[str, Any]:
    return {
        "message_category": result.category,
        "answer_mode_used": result.answer_mode,
        "thread_memory": memory_to_json(result.memory),
    }
