from typing import Any, TypedDict

import httpx

from app.core.config import settings
from app.db.session import get_connection


class LlmResult(TypedDict):
    text: str
    provider: str
    model: str
    used_fallback: bool
    error: str | None


class LlmRuntimeConfig(TypedDict):
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    temperature: float
    max_tokens: int
    system_prompt_template: str
    user_prompt_template: str


DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are PikuAI, a child-safe learning assistant.\n"
    "Answer the child's actual question first with useful content, then optional enrichment.\n"
    "Use factual accuracy where possible. Be warm, natural, and child-friendly without over-cute filler.\n"
    "Do not use generic filler such as 'that is interesting' when a real answer can be given.\n"
    "Never expose policy labels or moderation internals in final child text.\n"
    "In continuous discussion, do not use the child's name in every answer.\n"
    "Use the child's name only when it feels natural and adds warmth or clarity.\n"
    "For unsafe or too-mature requests, avoid abrupt refusal when possible: soften, reduce detail, redirect safely,\n"
    "and suggest involving a trusted adult where appropriate.\n"
    "Age policy: {age_style_rule}\n"
    "Answer mode policy: {answer_mode_rule}\n"
    "Child profile: name={child_name}, age_group={child_age_group}, gender={child_gender}, pattern={child_pattern}."
)

DEFAULT_USER_PROMPT_TEMPLATE = (
    "Conversation goal:\n{conversation_goal}\n\n"
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
    "Recent turns (last useful turns only):\n{recent_turns}\n\n"
    "Safety metadata:\n"
    "- policy_bucket: {policy_bucket}\n"
    "- safety_category: {safety_category}\n\n"
    "Current child message:\n{message}\n\n"
    "Answer instructions:\n"
    "1) Give the direct answer first.\n"
    "2) Keep age-appropriate depth.\n"
    "3) Keep tone warm and natural.\n"
    "4) Use continuity only if relevant.\n"
    "5) Do not include internal labels in final output."
)


def build_child_safe_prompt(
    *,
    age_band: str,
    answer_mode: str,
    child_gender: str,
    child_name: str,
    child_pattern: str,
    conversation_context: str,
    config: LlmRuntimeConfig,
    language: str,
    message: str,
    policy_bucket: str,
    safety_category: str,
) -> list[dict[str, str]]:
    values = _prompt_values(
        age_band=age_band,
        answer_mode=answer_mode,
        child_gender=child_gender,
        child_name=child_name,
        child_pattern=child_pattern,
        conversation_context=conversation_context,
        language=language,
        message=message,
        policy_bucket=policy_bucket,
        safety_category=safety_category,
    )
    system_prompt = _render_template(config["system_prompt_template"], values)
    user_prompt = _render_template(config["user_prompt_template"], values)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_with_local_llm(
    *,
    age_band: str,
    answer_mode: str,
    child_gender: str,
    child_name: str,
    child_pattern: str = "curious",
    conversation_context: str = "No earlier messages in this thread.",
    fallback_text: str,
    language: str,
    message: str,
    policy_bucket: str,
    safety_category: str,
) -> LlmResult:
    config = get_llm_runtime_config()
    if not config["enabled"]:
        return _fallback_result(fallback_text, "LLM is disabled.")

    messages = build_child_safe_prompt(
        age_band=age_band,
        answer_mode=answer_mode,
        child_gender=child_gender,
        child_name=child_name,
        child_pattern=child_pattern,
        conversation_context=conversation_context,
        config=config,
        language=language,
        message=message,
        policy_bucket=policy_bucket,
        safety_category=safety_category,
    )

    try:
        if config["provider"] == "openai_compatible":
            text = _generate_openai_compatible(messages, config)
        else:
            text = _generate_ollama(messages, config)
    except Exception as exc:
        return _fallback_result(fallback_text, str(exc), config)

    cleaned_text = text.strip()
    if not cleaned_text:
        return _fallback_result(fallback_text, "LLM returned an empty response.")

    return {
        "text": cleaned_text,
        "provider": config["provider"],
        "model": config["model"],
        "used_fallback": False,
        "error": None,
    }


def generate_with_runtime_prompt(*, messages: list[dict[str, str]], fallback_text: str) -> LlmResult:
    config = get_llm_runtime_config()
    if not config["enabled"]:
        return _fallback_result(fallback_text, "LLM is disabled.", config)
    try:
        if config["provider"] == "openai_compatible":
            text = _generate_openai_compatible(messages, config)
        else:
            text = _generate_ollama(messages, config)
    except Exception as exc:
        return _fallback_result(fallback_text, str(exc), config)

    cleaned_text = text.strip()
    if not cleaned_text:
        return _fallback_result(fallback_text, "LLM returned an empty response.", config)
    return {
        "text": cleaned_text,
        "provider": config["provider"],
        "model": config["model"],
        "used_fallback": False,
        "error": None,
    }


def llm_public_config() -> dict[str, Any]:
    config = get_llm_runtime_config()
    available = None
    error = None
    try:
        available = _ollama_model_available(config["model"], config) if config["provider"] == "ollama" else None
    except Exception as exc:
        available = False
        error = str(exc)

    return {
        "enabled": config["enabled"],
        "provider": config["provider"],
        "base_url": config["base_url"],
        "model": config["model"],
        "api_key_configured": bool(config["api_key"]),
        "model_available": available,
        "health_error": error,
        "timeout_seconds": config["timeout_seconds"],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "system_prompt_template": config["system_prompt_template"],
        "user_prompt_template": config["user_prompt_template"],
        "supported_placeholders": sorted(_prompt_values(
            age_band="9-11",
            answer_mode="short_answer",
            child_gender="not_disclosed",
            child_name="Piku",
            child_pattern="curious",
            conversation_context="No earlier messages in this thread.",
            language="en",
            message="Why is the sky blue?",
            policy_bucket="allowed",
            safety_category="general_learning",
        ).keys()),
        "supported_providers": ["ollama", "openai_compatible"],
    }


def update_llm_runtime_config(updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "enabled",
        "provider",
        "base_url",
        "model",
        "api_key_optional",
        "timeout_seconds",
        "temperature",
        "max_tokens",
        "system_prompt_template",
        "user_prompt_template",
    }
    clean = {key: value for key, value in updates.items() if key in allowed and value is not None}
    if not clean:
        return llm_public_config()
    assignments = ", ".join(f"{key} = %s" for key in clean)
    values = list(clean.values())
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE llm_runtime_config
                SET {assignments}, updated_at = now()
                WHERE id = true
                """,
                values,
            )
        connection.commit()
    return llm_public_config()


def get_llm_runtime_config() -> LlmRuntimeConfig:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT enabled, provider, base_url, model,
                           COALESCE(api_key_optional, '') AS api_key,
                           timeout_seconds, temperature, max_tokens,
                           system_prompt_template, user_prompt_template
                    FROM llm_runtime_config
                    WHERE id = true
                    """
                )
                row = cursor.fetchone()
        if row is not None:
            return {
                "enabled": bool(row["enabled"]),
                "provider": str(row["provider"]),
                "base_url": str(row["base_url"]),
                "model": str(row["model"]),
                "api_key": str(row["api_key"] or ""),
                "timeout_seconds": float(row["timeout_seconds"]),
                "temperature": float(row["temperature"]),
                "max_tokens": int(row["max_tokens"]),
                "system_prompt_template": str(row["system_prompt_template"] or DEFAULT_SYSTEM_PROMPT_TEMPLATE),
                "user_prompt_template": str(row["user_prompt_template"] or DEFAULT_USER_PROMPT_TEMPLATE),
            }
    except Exception:
        pass
    return {
        "enabled": settings.llm_enabled,
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
        "timeout_seconds": settings.llm_timeout_seconds,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "system_prompt_template": DEFAULT_SYSTEM_PROMPT_TEMPLATE,
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE,
    }


def _ollama_model_available(model: str, config: LlmRuntimeConfig) -> bool:
    response = httpx.get(
        f"{config['base_url'].rstrip('/')}/api/tags",
        timeout=min(config["timeout_seconds"], 5),
    )
    response.raise_for_status()
    models = response.json().get("models", [])
    names = {item.get("name") for item in models} | {item.get("model") for item in models}
    return model in names


def _generate_ollama(messages: list[dict[str, str]], config: LlmRuntimeConfig) -> str:
    response = httpx.post(
        f"{config['base_url'].rstrip('/')}/api/chat",
        json={
            "model": config["model"],
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": config["temperature"],
                "num_predict": config["max_tokens"],
            },
        },
        timeout=config["timeout_seconds"],
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("message", {}).get("content", ""))


def _generate_openai_compatible(messages: list[dict[str, str]], config: LlmRuntimeConfig) -> str:
    headers = {"Authorization": f"Bearer {config['api_key']}"} if config["api_key"] else None
    response = httpx.post(
        f"{config['base_url'].rstrip('/')}/chat/completions",
        json={
            "model": config["model"],
            "messages": messages,
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
        },
        headers=headers,
        timeout=config["timeout_seconds"],
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices", [])
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content", ""))


def _prompt_values(
    *,
    age_band: str,
    answer_mode: str,
    child_gender: str,
    child_name: str,
    child_pattern: str,
    conversation_context: str,
    language: str,
    message: str,
    policy_bucket: str,
    safety_category: str,
) -> dict[str, str]:
    conversation_goal = (
        "Help the child with a useful first answer while keeping safety protections natural and calm."
    )
    return {
        "age_band": age_band,
        "answer_mode": answer_mode,
        "answer_mode_rule": "Match requested answer style while keeping clarity and safety.",
        "child_age_group": age_band,
        "child_gender": child_gender or "not_disclosed",
        "child_name": child_name or "the child",
        "child_pattern": child_pattern or "curious",
        "conversation_context": conversation_context or "No earlier messages in this thread.",
        "conversation_goal": conversation_goal,
        "emotional_hint": "none",
        "language": language,
        "message": message,
        "message_category": "factual_learning",
        "observed_preferences": "none",
        "policy_bucket": policy_bucket,
        "recent_entities": "none",
        "recent_turns": conversation_context or "- no recent turns",
        "safety_category": safety_category,
        "thread_summary": conversation_context or "No prior thread context.",
        "topic_continuity": "Use context only if relevant.",
        "unresolved_follow_up": "none",
        "age_style_rule": "Match depth to child age. Keep explanation clear and concrete.",
    }


def _render_template(template: str, values: dict[str, str]) -> str:
    try:
        return template.format_map(_SafePromptValues(values))
    except Exception:
        return template


class _SafePromptValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _fallback_result(fallback_text: str, error: str, config: LlmRuntimeConfig | None = None) -> LlmResult:
    effective_config = config or get_llm_runtime_config()
    return {
        "text": fallback_text,
        "provider": effective_config["provider"],
        "model": effective_config["model"],
        "used_fallback": True,
        "error": error,
    }
