# Context Builder Plan

## Goal

Build a backend context builder that produces a compact, child-safe, token-bounded context payload for the guardrail orchestrator. The guardrail pipeline should use this context during text normalization, classified prompt generation, chat response generation, and optional validation without exposing unnecessary personal data or unbounded chat history.

The current guardrail orchestrator already has runtime switches for:

- `context_enabled`
- `context_recent_message_limit`
- `context_to_text_normalization_enabled`
- `context_to_classified_prompt_enabled`
- `context_to_chat_enabled`
- `context_to_validator_enabled`

Today those settings feed `_context_placeholder(...)` in `app/modules/guardrails/client.py`. This plan replaces that placeholder with a structured context builder.

## Design Principles

- Keep context minimal and purpose-built for safety decisions.
- Prefer structured fields over long prose summaries.
- Never include raw data unless a downstream stage needs it.
- Bound all arrays and string lengths before sending context to guardrail services.
- Keep parent controls and safety state separate from conversational memory.
- Make the context payload deterministic and easy to test.
- Preserve the existing `recent_context` field name initially for compatibility.

## Proposed Module

Create:

```text
app/modules/chat/context_builder.py
```

The module should expose:

```python
def build_guardrails_context(
    *,
    child: dict[str, Any],
    recent_messages: list[dict[str, Any]],
    previous_memory: dict[str, Any] | None,
    matched_restricted_topic: str | None,
    language: str,
    input_mode: str,
    recent_message_limit: int,
    enabled: bool,
) -> dict[str, Any]:
    ...
```

Return an empty-but-typed context when disabled:

```python
{
    "enabled": False,
    "recent_turns": [],
    "thread_memory": None,
    "child_profile": None,
    "parent_controls": None,
    "safety_state": None,
    "limits": {"recent_message_limit": 0},
}
```

## Context Contract

When enabled, return:

```python
{
    "enabled": True,
    "recent_turns": [
        {
            "speaker": "child" | "assistant",
            "text": "bounded text",
            "policy_bucket": "allowed",
            "safety_category": "safe_learning",
            "moderation_status": "passed",
        }
    ],
    "thread_memory": {
        "rolling_summary": "short deterministic summary",
        "unresolved_follow_up": None,
        "emotional_hint": None,
        "recent_entities": [],
        "observed_preferences": [],
        "topic_continuity": "Standalone turn.",
    },
    "child_profile": {
        "age_group": "8-10",
        "language": "en",
        "input_mode": "text",
    },
    "parent_controls": {
        "restricted_topics": [],
        "matched_restricted_topic": None,
    },
    "safety_state": {
        "recent_policy_buckets": [],
        "recent_safety_categories": [],
        "has_recent_escalation": False,
        "has_recent_block": False,
    },
    "limits": {
        "recent_message_limit": 8,
        "max_turn_chars": 280,
        "max_summary_chars": 500,
    },
}
```

## Data Sources

- `child_profiles`: age band, display name only if needed, language preference later, topic restrictions.
- `chat_messages`: sender type, rendered text, policy bucket, safety category, moderation status, metadata.
- Existing `thread_memory` metadata from the latest assistant message.
- Request payload: input mode, language, current matched restricted topic.

Avoid adding new database queries in the orchestrator if `chat/router.py` already has the relevant rows. If more fields are needed, expand the existing recent messages query once and pass the rows into the builder.

## Implementation Steps

1. Add `app/modules/chat/context_builder.py`.
2. Move the bounded recent-turn logic out of `_context_placeholder(...)`.
3. Reuse `build_thread_memory(...)` and `memory_to_json(...)` from `thread_memory_manager.py`.
4. Include recent moderation state from `policy_bucket`, `safety_category`, and `moderation_status` when available.
5. Add a compatibility adapter in `app/modules/guardrails/client.py` so downstream calls still receive `recent_context`.
6. Store the full structured context in `metadata["guardrails"]["context"]`.
7. Keep `metadata["guardrails"]["context_config"]` for debugging and admin visibility.
8. Remove or deprecate `_context_placeholder(...)` after tests cover the new builder.

## Guardrail Orchestrator Integration

Update `orchestrate_guardrails_response(...)` in `app/modules/guardrails/client.py`:

- Build `child_profile` as it does today.
- Build `context` using the new context builder.
- Treat `context_enabled` as the master switch.
- Use the per-stage switches to decide which service receives context.
- Pass context to text normalization:

```python
"recent_context": context if context_to_text_normalization_enabled else []
```

- Pass the same context to classified prompt generation:

```python
"recent_context": context if context_to_classified_prompt_enabled else []
```

- Include context in the chat system prompt if enabled. Do not send it as a separate chat request JSON key:

```python
if context_to_chat_enabled:
    prompts = prompts_with_context_in_system_prompt(prompts, context)
```

- Include context in validator request only if useful for validator behavior. The first implementation can skip this to avoid changing validator semantics.

```python
if context_to_validator_enabled:
    validator_request["recent_context"] = context
```

## Compatibility Strategy

Some guardrail services may currently expect `recent_context` to be a list of strings. To reduce risk:

1. Add a short-term field:

```python
"recent_context_text": ["Child: ...", "Assistant: ..."]
```

2. Send both fields during rollout:

```python
"recent_context": structured_context,
"recent_context_text": legacy_context_strings,
```

3. Once classifier, normalizer, and chat services support the structured contract, remove the legacy field.

## Privacy And Safety Rules

- Do not include parent email, parent user id, child id, thread id, or message ids in context.
- Do not include raw metadata blobs from prior messages.
- Do not include full historical transcripts.
- Truncate every recent turn before sending to external services.
- Include only the topic restriction terms that are already active for the child profile.
- Treat the builder as a safety component: malformed rows should be skipped, not allowed to crash the chat request.

## Tests

Add focused tests for:

- Disabled context returns the empty typed context.
- Recent turns respect `context_recent_message_limit`.
- Long text is truncated.
- Assistant and child speakers are normalized.
- Previous `thread_memory` is reused and merged with recent messages.
- Recent safety state detects prior `block_and_redirect` and `escalate`.
- Parent restricted topics and `matched_restricted_topic` are included.
- Orchestrator sends the new context to normalizer and classifier.
- Legacy `recent_context_text` matches existing list-of-strings behavior during rollout.

Update existing tests in:

```text
tests/test_guardrails_orchestration.py
```

Add new tests in:

```text
tests/test_context_builder.py
```

## Rollout Plan

1. Land the context builder with tests while still preserving legacy context output.
2. Enable structured context in orchestrator metadata first.
3. Send structured context to normalizer and classifier behind `context_enabled`.
4. Confirm guardrail service payload handling in local Docker.
5. Add admin observability for context enabled, recent message limit, and context version.
6. Remove legacy context strings after downstream services no longer depend on them.

## Open Questions

- Should the validator receive conversation context, or should it judge only the final assistant answer?
- Should child display name be excluded entirely, or allowed when it improves age-appropriate response tone?
- Should parent controls include only matched topics or the full restricted topic list?
- Do downstream guardrail services require a version field like `context_version: "v1"`?
