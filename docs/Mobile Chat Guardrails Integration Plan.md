# Orchestration of Guardrails Integration Plan in pikuai-backend and admin services

## Summary

`pikuai-app` stays on one product endpoint: `POST /api/v1/chat/message`. `pikuai-backend` owns guardrails orchestration, product policy, persistence, token accounting, admin configuration, reports, and final response shaping.

Current flow: mobile -> backend -> optional text normalization -> optional context placeholder -> optional classified prompt -> always-on guardrails chat LLM -> optional validator -> persistence/token usage/admin report -> mobile response.

If guardrails orchestration is disabled or unavailable, backend falls back to the legacy local safety/LLM path.

## Runtime Configuration

Configuration is stored in `guardrails_runtime_config`, seeded from environment defaults, and editable from `pikuai-admin` under `Settings -> Guardrails`.

- `GUARDRAILS_ENABLED`
- `GUARDRAILS_TEXT_NORMALIZATION_ENABLED`
- `GUARDRAILS_TEXT_NORMALIZATION_URL`
- `GUARDRAILS_TEXT_NORMALIZATION_SYSTEM_PROMPT`
- `GUARDRAILS_CONTEXT_ENABLED`
- `GUARDRAILS_CONTEXT_RECENT_MESSAGE_LIMIT`
- `GUARDRAILS_CLASSIFIED_PROMPT_ENABLED`
- `GUARDRAILS_CLASSIFIED_PROMPT_URL`
- `GUARDRAILS_CHAT_URL`
- `GUARDRAILS_DEFAULT_SYSTEM_PROMPT`
- `GUARDRAILS_VALIDATOR_ENABLED`
- `GUARDRAILS_VALIDATOR_URL`
- `GUARDRAILS_VALIDATOR_THRESHOLD`
- `GUARDRAILS_FALLBACK_RESPONSE`
- `GUARDRAILS_TIMEOUT_SECONDS`

When backend runs inside Docker and guardrails services run on the host machine, endpoint URLs should use `host.docker.internal`, for example:

```env
GUARDRAILS_TEXT_NORMALIZATION_URL=http://host.docker.internal:4003/api/v1/guardrail/text-normalization
GUARDRAILS_CLASSIFIED_PROMPT_URL=http://host.docker.internal:4001/api/v1/guardrail/classified/prompt
GUARDRAILS_CHAT_URL=http://host.docker.internal:4003/api/v1/guardrail/chat
GUARDRAILS_VALIDATOR_URL=http://host.docker.internal:4002/api/v1/guardrail/validate
```

## Orchestration Behavior

- Text normalization:
  - If enabled, backend calls `GUARDRAILS_TEXT_NORMALIZATION_URL`.
  - The request includes the admin-configured normalization system prompt.
  - Backend stores raw input, normalized input, request, response, prompt snapshot, and errors.
  - If disabled or failed, backend uses raw input as normalized input.
- Context:
  - If enabled, backend sends recent thread context up to `context_recent_message_limit`.
  - If disabled, backend sends `recent_context: []`.
  - Current context curation is intentionally a placeholder; no separate context intelligence is applied yet.
- Classified prompt:
  - If enabled, backend sends normalized input, child profile, session id, and context to `GUARDRAILS_CLASSIFIED_PROMPT_URL`.
  - Returned `prompts` are the authoritative chat messages for guardrails chat.
  - Backend stores full `prompts`, `prompt_checklist`, and `classifier_output`.
  - Backend does not rewrite valid classified prompt messages.
- Default prompt fallback:
  - Backend uses `GUARDRAILS_DEFAULT_SYSTEM_PROMPT` only when classified prompt is disabled, unavailable, or returns no valid `prompts`.
  - A valid prompt item must have non-empty `role` and `content`.
  - Fallback prompt payload is `[{role: "system", content: default_system_prompt}, {role: "user", content: normalized_message}]`.
  - Metadata records `default_system_prompt_used: true`.
- Chat LLM:
  - Chat generation stays enabled whenever guardrails orchestration is enabled.
  - Backend calls `GUARDRAILS_CHAT_URL` with `validate_response: false`.
  - Backend stores full chat request and full raw chat response.
  - If chat returns text and validation passes or validator is disabled, the guardrails chat LLM response is delivered to the child as-is.
- Validator:
  - If enabled, backend validates the generated assistant response with `GUARDRAILS_VALIDATOR_URL`.
  - If `response_validation` is safe/pass and `validation_score >= validator_threshold`, backend delivers the chat response.
  - If validator fails, is unsafe, or score is below threshold, backend returns `GUARDRAILS_FALLBACK_RESPONSE`.
  - If validator is disabled, backend delivers the chat response and records `validator_skipped`.
- Parent policy:
  - Parent blocked topics can still short-circuit before guardrails and return a safe fallback.

## Internal Contracts

### Classified Prompt Request

```json
{
  "child_profile": {
    "age": 10,
    "age_group": "11-12",
    "language": "en"
  },
  "session_id": "classify-001",
  "recent_context": [],
  "message": "I feel alone because mama works even on Sunday. I feel like I am reaching my limit."
}
```

### Classified Prompt Response

```json
{
  "prompts": [
    {
      "role": "system",
      "content": "You are PikuAI, a child-safe learning assistant..."
    },
    {
      "role": "user",
      "content": "I feel alone because mama works even on Sunday. I feel like I am reaching my limit."
    }
  ],
  "prompt_checklist": {
    "passed": true,
    "checks": {
      "CHK-01": true
    }
  },
  "classifier_output": {
    "g1": {
      "id": "GENERIC",
      "score": 0.98
    },
    "g2": {
      "id": "AMBIGUOUS_RISK",
      "score": 0.87
    },
    "active_flags": [
      {
        "id": "has_emotional_distress",
        "score": 0.99
      }
    ],
    "usage": {
      "prompt_tokens": 55,
      "completion_tokens": 0,
      "total_tokens": 55
    }
  }
}
```

### Chat Request From Backend

```json
{
  "messages": [
    {
      "role": "system",
      "content": "system prompt from classified prompt response"
    },
    {
      "role": "user",
      "content": "normalized child message"
    }
  ],
  "validate_response": false,
  "session_id": "chat-001",
  "child_profile": {
    "age": 10,
    "age_group": "11-12",
    "language": "en"
  }
}
```

### Validator Request

```json
{
  "message": {
    "role": "assistant",
    "content": "assistant response text"
  },
  "child_profile": {
    "age": 10,
    "age_group": "11-12",
    "language": "en"
  },
  "session_id": "chat-001"
}
```

## Persistence And Reporting

Backend stores orchestration metadata on `chat_messages.metadata_json.guardrails`, including:

- raw message and normalized message.
- text normalization request/response/error.
- context config and context placeholder output.
- classified prompt request/response/error.
- selected prompt messages.
- chat request and raw chat response.
- validator request/response/error.
- final response source.
- fallback reason when fallback is used.
- whether default prompt was used.

Backend stores stage token usage in `chat_guardrails_token_usage`:

- parent user id.
- child profile id.
- thread id.
- message id.
- stage name: `text_normalization`, `classified_prompt`, `chat`, `validator`.
- provider/model when available.
- prompt tokens, completion tokens, total tokens.
- metadata and timestamp.

Admin reports are available at `pikuai-admin /reports`, using `GET /api/v1/admin/guardrails/chat-calls`.

The first report is `Chat Classification` and shows:

- text input and normalized input.
- text normalization status.
- complete classified prompt `system` and `user` messages.
- G1, G2, active flags, and scores.
- full chat LLM request and response.
- delivered assistant response.
- validation status and score.
- whether the call went through guardrails.
- response source and token usage.
- filters for text, G1, and G2.
- client-side pagination.

Admin settings are path-based, so refresh preserves pages such as `/settings` and `/reports`.

## Admin Endpoints

- `GET /api/v1/admin/guardrails/config`
- `PATCH /api/v1/admin/guardrails/config`
- `GET /api/v1/admin/guardrails/reachability`
- `GET /api/v1/admin/guardrails/chat-calls`

Reachability checks derive `/health` from configured service URLs and skip disabled optional services.

## Test Coverage

Backend tests cover:

- text normalization request includes configured system prompt.
- classified prompt disabled path uses default system prompt.
- validator below threshold returns configured fallback.
- validator disabled returns generated chat response.
- context disabled sends `recent_context: []`.

Verified commands:

```bash
PYTHONPATH=. pytest -q
python -m compileall app
```

Admin verification:

```bash
npm run build
```

## Assumptions

- `pikuai-backend` owns orchestration and persistence.
- `pikuai-app` stays unchanged and calls only `/chat/message`.
- Guardrails service URLs are internal runtime configuration.
- Valid classified prompt messages are never rewritten by backend.
- Chat response is delivered as-is when validation passes or validator is disabled.
- Fallback response is used only for parent-topic short-circuit, chat failure/empty response, validator failure/unsafe/below threshold, or full legacy fallback when guardrails orchestration is disabled/unavailable.
