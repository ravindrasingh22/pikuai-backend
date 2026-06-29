from typing import Any

from app.modules.guardrails import client


def _config(**overrides: Any) -> client.GuardrailsRuntimeConfig:
    base: client.GuardrailsRuntimeConfig = {
        "enabled": True,
        "text_normalization_enabled": True,
        "text_normalization_url": "http://normalizer",
        "text_normalization_system_prompt": "normalize carefully",
        "context_enabled": True,
        "context_recent_message_limit": 8,
        "context_to_text_normalization_enabled": True,
        "context_to_classified_prompt_enabled": True,
        "context_to_chat_enabled": False,
        "context_to_validator_enabled": False,
        "classified_prompt_enabled": True,
        "classified_prompt_url": "http://classifier",
        "chat_url": "http://chat",
        "default_system_prompt": "default safe system prompt",
        "validator_enabled": True,
        "validator_url": "http://validator",
        "validator_threshold": 0.85,
        "fallback_response": "safe fallback",
        "timeout_seconds": 3,
    }
    base.update(overrides)
    return base


def _child() -> dict[str, object]:
    return {"id": "child-1", "age_band": "11-13", "display_name": "Anaya"}


def test_orchestration_forwards_normalization_prompt(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        calls.append((url, payload))
        if url == "http://normalizer":
            return {"normalized_text": "I feel alone.", "usage": {"prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 3}}
        if url == "http://classifier":
            return {
                "prompts": [{"role": "system", "content": "classified system"}, {"role": "user", "content": "I feel alone."}],
                "classifier_output": {"g2": {"id": "EMOTIONAL", "reason": "distress"}, "g4": {"action": "TRANSFORM"}, "usage": {"prompt_tokens": 4}},
            }
        if url == "http://chat":
            return {"answer_text": "I am sorry you feel alone.", "model": "gemma", "provider": "guardrails", "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11}}
        return {"response_validation": "Safe", "validation_score": 0.91, "validator_usage": {"prompt_tokens": 7, "completion_tokens": 0, "total_tokens": 7}}

    monkeypatch.setattr(client, "get_guardrails_runtime_config", lambda: _config())
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="i feel alone",
        recent_messages=[],
        session_id="session-1",
    )

    assert result.answer_text == "I am sorry you feel alone."
    assert calls[0][0] == "http://normalizer"
    assert calls[0][1]["system_prompt"] == "normalize carefully"
    assert calls[1][1]["message"] == "I feel alone."
    assert calls[2][1]["messages"][0]["content"] == "classified system"
    assert calls[2][1]["validate_response"] is False
    assert {usage.stage_name for usage in result.token_usage} == {"text_normalization", "classified_prompt", "chat", "validator"}


def test_classified_prompt_disabled_uses_default_system_prompt(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        calls.append((url, payload))
        if url == "http://normalizer":
            return {"normalized_text": "Why is the sky blue?"}
        if url == "http://chat":
            return {"answer_text": "Because blue light scatters."}
        return {"response_validation": "Safe", "validation_score": 0.9}

    monkeypatch.setattr(client, "get_guardrails_runtime_config", lambda: _config(classified_prompt_enabled=False))
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="why sky blue",
        recent_messages=[],
        session_id="session-1",
    )

    called_urls = [url for url, _ in calls]
    assert "http://classifier" not in called_urls
    chat_payload = next(payload for url, payload in calls if url == "http://chat")
    assert chat_payload["messages"][0] == {"role": "system", "content": "default safe system prompt"}
    assert result.metadata["default_system_prompt_used"] is True


def test_validator_below_threshold_returns_fallback(monkeypatch) -> None:
    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        if url == "http://normalizer":
            return {"normalized_text": payload["message"]}
        if url == "http://classifier":
            return {"prompts": [{"role": "system", "content": "system"}, {"role": "user", "content": payload["message"]}], "classifier_output": {}}
        if url == "http://chat":
            return {"answer_text": "generated answer"}
        return {"response_validation": "Safe", "validation_score": 0.2}

    monkeypatch.setattr(client, "get_guardrails_runtime_config", lambda: _config(validator_threshold=0.85))
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="hello",
        recent_messages=[],
        session_id="session-1",
    )

    assert result.answer_text == "safe fallback"
    assert result.fallback_used is True
    assert result.fallback_reason == "validator_failed_or_below_threshold"


def test_validator_disabled_returns_generated_answer(monkeypatch) -> None:
    called_urls: list[str] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        called_urls.append(url)
        if url == "http://normalizer":
            return {"normalized_text": payload["message"]}
        if url == "http://classifier":
            return {"prompts": [{"role": "system", "content": "system"}, {"role": "user", "content": payload["message"]}], "classifier_output": {}}
        return {"answer_text": "generated answer"}

    monkeypatch.setattr(client, "get_guardrails_runtime_config", lambda: _config(validator_enabled=False))
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="hello",
        recent_messages=[],
        session_id="session-1",
    )

    assert "http://validator" not in called_urls
    assert result.answer_text == "generated answer"
    assert result.metadata["validator_skipped"] is True


def test_context_disabled_sends_empty_recent_context(monkeypatch) -> None:
    classifier_payloads: list[dict[str, Any]] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        if url == "http://normalizer":
            return {"normalized_text": payload["message"]}
        if url == "http://classifier":
            classifier_payloads.append(payload)
            return {"prompts": [{"role": "system", "content": "system"}, {"role": "user", "content": payload["message"]}], "classifier_output": {}}
        if url == "http://chat":
            return {"answer_text": "generated answer"}
        return {"response_validation": "Safe", "validation_score": 0.9}

    monkeypatch.setattr(client, "get_guardrails_runtime_config", lambda: _config(context_enabled=False))
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="hello",
        recent_messages=[{"sender_type": "child", "rendered_text": "Earlier question"}],
        session_id="session-1",
    )

    assert classifier_payloads[0]["recent_context"] == []
    assert result.metadata["context_config"]["enabled"] is False


def test_context_stage_switches_route_context_independently(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        calls.append((url, payload))
        if url == "http://normalizer":
            return {"normalized_text": payload["message"]}
        if url == "http://classifier":
            return {"prompts": [{"role": "system", "content": "system"}, {"role": "user", "content": payload["message"]}], "classifier_output": {}}
        if url == "http://chat":
            return {"answer_text": "generated answer"}
        return {"response_validation": "Safe", "validation_score": 0.9}

    monkeypatch.setattr(
        client,
        "get_guardrails_runtime_config",
        lambda: _config(
            context_to_text_normalization_enabled=True,
            context_to_classified_prompt_enabled=False,
            context_to_chat_enabled=True,
            context_to_validator_enabled=True,
        ),
    )
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="hello",
        recent_messages=[{"sender_type": "child", "rendered_text": "Earlier question"}],
        session_id="session-1",
    )

    normalizer_payload = next(payload for url, payload in calls if url == "http://normalizer")
    classifier_payload = next(payload for url, payload in calls if url == "http://classifier")
    chat_payload = next(payload for url, payload in calls if url == "http://chat")
    validator_payload = next(payload for url, payload in calls if url == "http://validator")

    assert normalizer_payload["recent_context"] == ["Child: Earlier question"]
    assert classifier_payload["recent_context"] == []
    assert "recent_context" not in chat_payload
    assert "Recent conversation context" in chat_payload["messages"][0]["content"]
    assert "Child: Earlier question" in chat_payload["messages"][0]["content"]
    assert validator_payload["recent_context"] == ["Child: Earlier question"]
    assert result.metadata["context_stage_delivery"] == {
        "text_normalization": True,
        "classified_prompt": False,
        "chat": True,
        "validator": True,
    }


def test_chat_and_validator_context_are_omitted_by_default(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        calls.append((url, payload))
        if url == "http://normalizer":
            return {"normalized_text": payload["message"]}
        if url == "http://classifier":
            return {"prompts": [{"role": "system", "content": "system"}, {"role": "user", "content": payload["message"]}], "classifier_output": {}}
        if url == "http://chat":
            return {"answer_text": "generated answer"}
        return {"response_validation": "Safe", "validation_score": 0.9}

    monkeypatch.setattr(client, "get_guardrails_runtime_config", lambda: _config())
    monkeypatch.setattr(client, "_post_json", fake_post)

    client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="hello",
        recent_messages=[{"sender_type": "child", "rendered_text": "Earlier question"}],
        session_id="session-1",
    )

    chat_payload = next(payload for url, payload in calls if url == "http://chat")
    validator_payload = next(payload for url, payload in calls if url == "http://validator")

    assert "recent_context" not in chat_payload
    assert "recent_context" not in validator_payload


def test_chat_context_enabled_with_default_prompt_embeds_context_in_system_prompt(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, payload: dict[str, Any], config: client.GuardrailsRuntimeConfig) -> dict[str, Any]:
        calls.append((url, payload))
        if url == "http://normalizer":
            return {"normalized_text": payload["message"]}
        if url == "http://chat":
            return {"answer_text": "generated answer"}
        return {"response_validation": "Safe", "validation_score": 0.9}

    monkeypatch.setattr(
        client,
        "get_guardrails_runtime_config",
        lambda: _config(classified_prompt_enabled=False, context_to_chat_enabled=True),
    )
    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.orchestrate_guardrails_response(
        child=_child(),
        input_mode="text",
        language="en",
        matched_restricted_topic=None,
        message="hello",
        recent_messages=[{"sender_type": "assistant", "rendered_text": "We were learning fractions"}],
        session_id="session-1",
    )

    chat_payload = next(payload for url, payload in calls if url == "http://chat")

    assert "recent_context" not in chat_payload
    assert chat_payload["messages"][0]["role"] == "system"
    assert chat_payload["messages"][0]["content"].startswith("default safe system prompt")
    assert "Recent conversation context" in chat_payload["messages"][0]["content"]
    assert "Assistant: We were learning fractions" in chat_payload["messages"][0]["content"]
    assert result.metadata["default_system_prompt_used"] is True
