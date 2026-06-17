from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

import httpx

from app.core.config import settings


class GuardrailsRuntimeConfig(TypedDict):
    enabled: bool
    text_normalization_enabled: bool
    text_normalization_url: str
    text_normalization_system_prompt: str
    context_enabled: bool
    context_recent_message_limit: int
    classified_prompt_enabled: bool
    classified_prompt_url: str
    chat_url: str
    default_system_prompt: str
    validator_enabled: bool
    validator_url: str
    validator_threshold: float
    fallback_response: str
    timeout_seconds: float


@dataclass
class StageTokenUsage:
    stage_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardrailsOrchestrationResult:
    answer_text: str
    ai_model_used: str
    alert_created: bool
    child_safe_status: str
    explanation_code: str
    explanation_text: str
    fallback_used: bool
    fallback_reason: str | None
    llm_provider: str
    llm_used_fallback: bool
    llm_error: str | None
    metadata: dict[str, Any]
    moderation_status: str
    policy_bucket: str
    safety_category: str
    answer_mode: str = "guardrails_orchestrated"
    token_usage: list[StageTokenUsage] = field(default_factory=list)


DEFAULT_TEXT_NORMALIZATION_SYSTEM_PROMPT = settings.guardrails_text_normalization_system_prompt
DEFAULT_GUARDRAILS_SYSTEM_PROMPT = settings.guardrails_default_system_prompt


def guardrails_public_config() -> dict[str, Any]:
    return get_guardrails_runtime_config()


def get_guardrails_runtime_config() -> GuardrailsRuntimeConfig:
    try:
        from app.db.session import get_connection

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT enabled, text_normalization_enabled, text_normalization_url,
                           text_normalization_system_prompt, context_enabled,
                           context_recent_message_limit, classified_prompt_enabled,
                           classified_prompt_url, chat_url, default_system_prompt,
                           validator_enabled, validator_url, validator_threshold,
                           fallback_response, timeout_seconds
                    FROM guardrails_runtime_config
                    WHERE id = true
                    """
                )
                row = cursor.fetchone()
        if row is not None:
            return {
                "enabled": bool(row["enabled"]),
                "text_normalization_enabled": bool(row["text_normalization_enabled"]),
                "text_normalization_url": str(row["text_normalization_url"]),
                "text_normalization_system_prompt": str(row["text_normalization_system_prompt"] or DEFAULT_TEXT_NORMALIZATION_SYSTEM_PROMPT),
                "context_enabled": bool(row["context_enabled"]),
                "context_recent_message_limit": int(row["context_recent_message_limit"]),
                "classified_prompt_enabled": bool(row["classified_prompt_enabled"]),
                "classified_prompt_url": str(row["classified_prompt_url"]),
                "chat_url": str(row["chat_url"]),
                "default_system_prompt": str(row["default_system_prompt"] or DEFAULT_GUARDRAILS_SYSTEM_PROMPT),
                "validator_enabled": bool(row["validator_enabled"]),
                "validator_url": str(row["validator_url"]),
                "validator_threshold": float(row["validator_threshold"]),
                "fallback_response": str(row["fallback_response"] or settings.guardrails_fallback_response),
                "timeout_seconds": float(row["timeout_seconds"]),
            }
    except Exception:
        pass
    return {
        "enabled": settings.guardrails_enabled,
        "text_normalization_enabled": settings.guardrails_text_normalization_enabled,
        "text_normalization_url": settings.guardrails_text_normalization_url,
        "text_normalization_system_prompt": settings.guardrails_text_normalization_system_prompt,
        "context_enabled": settings.guardrails_context_enabled,
        "context_recent_message_limit": settings.guardrails_context_recent_message_limit,
        "classified_prompt_enabled": settings.guardrails_classified_prompt_enabled,
        "classified_prompt_url": settings.guardrails_classified_prompt_url,
        "chat_url": settings.guardrails_chat_url,
        "default_system_prompt": settings.guardrails_default_system_prompt,
        "validator_enabled": settings.guardrails_validator_enabled,
        "validator_url": settings.guardrails_validator_url,
        "validator_threshold": settings.guardrails_validator_threshold,
        "fallback_response": settings.guardrails_fallback_response,
        "timeout_seconds": settings.guardrails_timeout_seconds,
    }


def update_guardrails_runtime_config(updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "enabled",
        "text_normalization_enabled",
        "text_normalization_url",
        "text_normalization_system_prompt",
        "context_enabled",
        "context_recent_message_limit",
        "classified_prompt_enabled",
        "classified_prompt_url",
        "chat_url",
        "default_system_prompt",
        "validator_enabled",
        "validator_url",
        "validator_threshold",
        "fallback_response",
        "timeout_seconds",
    }
    clean = {key: value for key, value in updates.items() if key in allowed and value is not None}
    if not clean:
        return guardrails_public_config()
    assignments = ", ".join(f"{key} = %s" for key in clean)
    values = list(clean.values())
    from app.db.session import get_connection

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE guardrails_runtime_config
                SET {assignments}, updated_at = now()
                WHERE id = true
                """,
                values,
            )
        connection.commit()
    return guardrails_public_config()


def orchestrate_guardrails_response(
    *,
    child: dict[str, Any],
    message: str,
    recent_messages: list[dict[str, Any]],
    matched_restricted_topic: str | None,
    session_id: str,
    input_mode: str,
    language: str,
) -> GuardrailsOrchestrationResult:
    config = get_guardrails_runtime_config()
    if matched_restricted_topic:
        fallback = config["fallback_response"]
        return GuardrailsOrchestrationResult(
            answer_text=fallback,
            ai_model_used="backend_parent_topic_policy",
            alert_created=True,
            child_safe_status="controlled",
            explanation_code=f"parent_blocked_topic:{matched_restricted_topic}",
            explanation_text=f"Parent blocked topic matched before guardrails orchestration: {matched_restricted_topic}.",
            fallback_used=True,
            fallback_reason="parent_blocked_topic",
            llm_provider="backend_policy",
            llm_used_fallback=True,
            llm_error=None,
            metadata={
                "guardrails_enabled": config["enabled"],
                "input_mode": input_mode,
                "raw_message": message,
                "normalized_message": message,
                "matched_restricted_topic": matched_restricted_topic,
                "final_response_source": "backend_parent_topic_policy",
            },
            moderation_status="blocked",
            policy_bucket="block_and_redirect",
            safety_category="parent_blocked_topic",
        )

    token_usage: list[StageTokenUsage] = []
    metadata: dict[str, Any] = {
        "guardrails_enabled": True,
        "input_mode": input_mode,
        "raw_message": message,
    }
    child_profile = _child_profile_payload(child, language)
    context = _context_placeholder(recent_messages, config)
    metadata["context_placeholder"] = context
    metadata["context_config"] = {
        "enabled": config["context_enabled"],
        "recent_message_limit": config["context_recent_message_limit"],
    }

    normalized_message = message
    if config["text_normalization_enabled"]:
        normalization_request = {
            "system_prompt": config["text_normalization_system_prompt"],
            "message": message,
            "child_profile": child_profile,
            "session_id": session_id,
            "recent_context": context,
        }
        metadata["text_normalization_request"] = normalization_request
        metadata["text_normalization_system_prompt"] = config["text_normalization_system_prompt"]
        try:
            normalization_response = _post_json(config["text_normalization_url"], normalization_request, config)
            metadata["text_normalization_response"] = normalization_response
            normalized_message = _extract_normalized_text(normalization_response, message)
            usage = _extract_usage(normalization_response, "normalization_usage", "usage", "token_usage")
            if usage:
                token_usage.append(_stage_usage("text_normalization", usage, normalization_response))
        except Exception as exc:
            metadata["text_normalization_error"] = str(exc)
    else:
        metadata["text_normalization_skipped"] = True
    metadata["normalized_message"] = normalized_message

    classified_prompt_response: dict[str, Any] | None = None
    if config["classified_prompt_enabled"]:
        classified_prompt_request = {
            "child_profile": child_profile,
            "session_id": session_id,
            "recent_context": context,
            "message": normalized_message,
        }
        metadata["classified_prompt_request"] = classified_prompt_request
        try:
            classified_prompt_response = _post_json(config["classified_prompt_url"], classified_prompt_request, config)
            metadata["classified_prompt_response"] = classified_prompt_response
            usage = _extract_usage(classified_prompt_response.get("classifier_output", {}), "usage")
            if usage:
                token_usage.append(_stage_usage("classified_prompt", usage, classified_prompt_response))
        except Exception as exc:
            metadata["classified_prompt_error"] = str(exc)
    else:
        metadata["classified_prompt_skipped"] = True

    prompts = _extract_prompts(classified_prompt_response)
    if not prompts:
        prompts = [
            {"role": "system", "content": config["default_system_prompt"]},
            {"role": "user", "content": normalized_message},
        ]
        metadata["default_system_prompt_used"] = True
    metadata["selected_prompts"] = prompts

    chat_request = {
        "messages": prompts,
        "validate_response": False,
        "session_id": session_id,
        "child_profile": child_profile,
    }
    metadata["chat_request"] = chat_request
    try:
        chat_response = _post_json(config["chat_url"], chat_request, config)
        metadata["chat_response"] = chat_response
        answer_text = _extract_chat_text(chat_response)
        chat_usage = _extract_usage(chat_response, "usage", "chat_usage")
        if chat_usage:
            token_usage.append(_stage_usage("chat", chat_usage, chat_response))
        ai_model_used = str(chat_response.get("model") or chat_response.get("ai_model_used") or "guardrails_chat")
        llm_provider = str(chat_response.get("provider") or chat_response.get("llm_provider") or "guardrails_chat")
    except Exception as exc:
        fallback = config["fallback_response"]
        metadata["chat_error"] = str(exc)
        return _fallback_result(
            answer_text=fallback,
            child_profile=child_profile,
            config=config,
            fallback_reason="chat_unavailable",
            metadata=metadata,
            token_usage=token_usage,
        )

    if not answer_text.strip():
        return _fallback_result(
            answer_text=config["fallback_response"],
            child_profile=child_profile,
            config=config,
            fallback_reason="chat_empty_response",
            metadata=metadata,
            token_usage=token_usage,
        )

    validator_response: dict[str, Any] | None = None
    validator_passed = True
    if config["validator_enabled"]:
        validator_request = {
            "message": {"role": "assistant", "content": answer_text},
            "child_profile": child_profile,
            "session_id": session_id,
        }
        metadata["validator_request"] = validator_request
        try:
            validator_response = _post_json(config["validator_url"], validator_request, config)
            metadata["validator_response"] = validator_response
            usage = _extract_usage(validator_response, "validator_usage", "usage")
            if usage:
                token_usage.append(_stage_usage("validator", usage, validator_response))
            validation_label = str(validator_response.get("response_validation") or validator_response.get("status") or "").lower()
            validation_score = float(validator_response.get("validation_score") or validator_response.get("score") or 0)
            validator_passed = validation_label in {"safe", "passed", "pass"} and validation_score >= config["validator_threshold"]
            metadata["validator_passed"] = validator_passed
        except Exception as exc:
            metadata["validator_error"] = str(exc)
            validator_passed = False
    else:
        metadata["validator_skipped"] = True

    classifier_output = (classified_prompt_response or {}).get("classifier_output", {})
    policy_bucket, safety_category, moderation_status, explanation_code, explanation_text, alert_created = _policy_from_classifier(classifier_output)

    if not validator_passed:
        delivered = config["fallback_response"]
        metadata["final_response_source"] = "validator_fallback"
        metadata["fallback_reason"] = "validator_failed_or_below_threshold"
        return GuardrailsOrchestrationResult(
            answer_text=delivered,
            ai_model_used=ai_model_used,
            alert_created=True,
            child_safe_status="controlled",
            explanation_code=explanation_code,
            explanation_text=explanation_text,
            fallback_used=True,
            fallback_reason="validator_failed_or_below_threshold",
            llm_provider=llm_provider,
            llm_used_fallback=True,
            llm_error=None,
            metadata=metadata,
            moderation_status="blocked",
            policy_bucket="block_and_redirect",
            safety_category=safety_category,
            token_usage=token_usage,
        )

    metadata["final_response_source"] = "guardrails_chat"
    return GuardrailsOrchestrationResult(
        answer_text=answer_text.strip(),
        ai_model_used=ai_model_used,
        alert_created=alert_created,
        child_safe_status="safe" if not alert_created else "controlled",
        explanation_code=explanation_code,
        explanation_text=explanation_text,
        fallback_used=False,
        fallback_reason=None,
        llm_provider=llm_provider,
        llm_used_fallback=False,
        llm_error=None,
        metadata=metadata,
        moderation_status=moderation_status,
        policy_bucket=policy_bucket,
        safety_category=safety_category,
        token_usage=token_usage,
    )


def insert_token_usage(
    *,
    child_profile_id: str,
    message_id: str,
    parent_user_id: str,
    thread_id: str,
    usages: list[StageTokenUsage],
) -> None:
    if not usages:
        return
    from psycopg.types.json import Jsonb

    from app.db.session import get_connection

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for usage in usages:
                cursor.execute(
                    """
                    INSERT INTO chat_guardrails_token_usage (
                      parent_user_id, child_profile_id, thread_id, message_id,
                      stage_name, provider, model, prompt_tokens,
                      completion_tokens, total_tokens, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        parent_user_id,
                        child_profile_id,
                        thread_id,
                        message_id,
                        usage.stage_name,
                        usage.provider,
                        usage.model,
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        Jsonb(usage.metadata),
                    ),
                )
        connection.commit()


def _fallback_result(
    *,
    answer_text: str,
    child_profile: dict[str, Any],
    config: GuardrailsRuntimeConfig,
    fallback_reason: str,
    metadata: dict[str, Any],
    token_usage: list[StageTokenUsage],
) -> GuardrailsOrchestrationResult:
    metadata["final_response_source"] = "guardrails_fallback"
    metadata["fallback_reason"] = fallback_reason
    return GuardrailsOrchestrationResult(
        answer_text=answer_text,
        ai_model_used="guardrails_fallback",
        alert_created=True,
        child_safe_status="controlled",
        explanation_code=fallback_reason,
        explanation_text=f"Guardrails orchestration used fallback: {fallback_reason}.",
        fallback_used=True,
        fallback_reason=fallback_reason,
        llm_provider="guardrails",
        llm_used_fallback=True,
        llm_error=fallback_reason,
        metadata={**metadata, "child_profile": child_profile, "validator_threshold": config["validator_threshold"]},
        moderation_status="blocked",
        policy_bucket="block_and_redirect",
        safety_category="guardrails_fallback",
        token_usage=token_usage,
    )


def _post_json(url: str, payload: dict[str, Any], config: GuardrailsRuntimeConfig) -> dict[str, Any]:
    response = httpx.post(url, json=payload, timeout=config["timeout_seconds"])
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {"data": data}


def _child_profile_payload(child: dict[str, Any], language: str) -> dict[str, Any]:
    age_group = str(child.get("age_band") or "9-11")
    return {
        "age": _age_from_band(age_group),
        "age_group": age_group,
        "language": language,
    }


def _age_from_band(age_band: str) -> int:
    parts = [part for part in age_band.replace("_", "-").split("-") if part.isdigit()]
    if not parts:
        return 10
    return int(parts[-1])


def _context_placeholder(recent_messages: list[dict[str, Any]], config: GuardrailsRuntimeConfig) -> list[str]:
    if not config["context_enabled"]:
        return []
    context: list[str] = []
    limit = max(0, int(config["context_recent_message_limit"]))
    for row in recent_messages[-limit:] if limit else []:
        sender = "Child" if row.get("sender_type") == "child" else "Assistant"
        text = str(row.get("rendered_text") or "").strip()
        if text:
            context.append(f"{sender}: {text}")
    return context


def _extract_normalized_text(payload: dict[str, Any], fallback: str) -> str:
    for key in ("normalized_text", "normalized_message", "text", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_normalized_text(data, fallback)
    return fallback


def _extract_prompts(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if not payload:
        return []
    prompts = payload.get("prompts")
    if not isinstance(prompts, list):
        return []
    clean: list[dict[str, str]] = []
    for item in prompts:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role and content:
            clean.append({"role": role, "content": content})
    return clean


def _extract_chat_text(payload: dict[str, Any]) -> str:
    for key in ("answer_text", "response_text", "text", "content", "answer"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return str(message["content"])
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            nested_message = first.get("message")
            if isinstance(nested_message, dict) and isinstance(nested_message.get("content"), str):
                return str(nested_message["content"])
    return ""


def _extract_usage(payload: Any, *keys: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    candidates: list[Any] = [payload]
    candidates.extend(payload.get(key) for key in keys)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if any(key in candidate for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            return candidate
    return None


def _stage_usage(stage_name: str, usage: dict[str, Any], payload: dict[str, Any]) -> StageTokenUsage:
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    return StageTokenUsage(
        stage_name=stage_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        provider=str(payload.get("provider") or payload.get("llm_provider") or "") or None,
        model=str(payload.get("model") or payload.get("ai_model_used") or "") or None,
        metadata={"usage": usage},
    )


def _policy_from_classifier(classifier_output: Any) -> tuple[str, str, str, str, str, bool]:
    if not isinstance(classifier_output, dict):
        return ("allowed", "guardrails_chat", "passed", "guardrails_chat", "Guardrails chat response generated.", False)
    g2 = classifier_output.get("g2") if isinstance(classifier_output.get("g2"), dict) else {}
    g4 = classifier_output.get("g4") if isinstance(classifier_output.get("g4"), dict) else {}
    g2_id = str(g2.get("id") or "guardrails_chat")
    action = str(g4.get("action") or "ALLOW").upper()
    policy_bucket = "allowed"
    moderation_status = "passed"
    alert_created = False
    if action == "BLOCK":
        policy_bucket = "block_and_redirect"
        moderation_status = "blocked"
        alert_created = True
    elif action == "TRANSFORM":
        policy_bucket = "allowed_with_adaptation"
        moderation_status = "adapted"
    reason = str(g2.get("reason") or f"Classified as {g2_id}.")
    return (policy_bucket, g2_id, moderation_status, g2_id, reason, alert_created)
