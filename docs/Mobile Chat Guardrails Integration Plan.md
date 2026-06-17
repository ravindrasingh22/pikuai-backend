# Mobile Chat Guardrails Integration Plan

## Summary

Keep `pikuai-app` on one product endpoint: `POST /api/v1/chat/message`. `pikuai-backend` will own orchestration, normalization, product policy, prompt selection, persistence, alerts, and response shaping. Guardrails services remain internal model/safety services.

Final flow: mobile -> backend normalize/context -> classified prompt endpoint -> chat generation -> validator -> backend persistence/alerts -> mobile response.

## Key Changes

- Mobile stays unchanged:
  - `sendChildMessage()` continues calling `/chat/message`.
  - No guardrails URLs or safety orchestration are exposed to the mobile app.
- Add backend guardrails config:
  - `GUARDRAILS_CLASSIFIED_PROMPT_URL=http://localhost:4001/api/v1/guardrail/classified/prompt`
  - `GUARDRAILS_CHAT_URL=http://localhost:4003/api/v1/guardrail/chat`
  - `GUARDRAILS_VALIDATOR_URL=http://localhost:4002/api/v1/guardrail/validate`
  - `GUARDRAILS_ENABLED=true`
- Backend chat orchestration:
  - Load parent, child profile, controls, restricted topics, thread memory, and recent messages.
  - Normalize the child input in backend before guardrails calls: trim, collapse whitespace, preserve raw text, derive language/input mode, and build recent context.
  - If parent controls hard-block the topic, skip generation and return backend safe fallback.
  - Call `GUARDRAILS_CLASSIFIED_PROMPT_URL` with normalized message, child profile, session/thread id, and recent context.
  - Use returned `prompts` as the authoritative system/user prompt for generation.
  - Use returned `classifier_output`, `prompt_checklist`, `g1/g2/g3/g4`, flags, age policy, and usage as moderation metadata.
  - Call `GUARDRAILS_CHAT_URL` with the classified prompt messages and `validate_response: false`.
  - Call `GUARDRAILS_VALIDATOR_URL` from backend with the generated assistant response.
  - If validator returns unsafe or is unavailable, fail closed with backend fallback text.
  - Persist child and assistant messages, full metadata, alert state, and report/transcript fields.

## API And Data Flow

- Backend request from mobile remains:
  - `child_profile_id`
  - `thread_id_optional`
  - `message`
  - `answer_mode_optional`
  - `input_mode_optional`
  - `language_optional`
- Classified prompt request from backend:
  - `child_profile`
  - `session_id`
  - normalized `message`
  - `recent_context`
- Classified prompt response used by backend:
  - `prompts`
  - `prompt_checklist`
  - `classifier_output`
- Chat request from backend:
  - `messages: classifiedPrompt.prompts`
  - `session_id`
  - `child_profile`
  - generation config from backend settings
  - `validate_response: false`
- Validator request from backend:
  - assistant message content
  - child profile age group/language
  - session id
- Mobile response remains compatible:
  - `thread_id`
  - `message_id`
  - `answer_text`
  - `policy_bucket`
  - `explanation_summary`
  - `alert_created`
  - `child_safe_status`

## Test Plan

- Backend unit tests:
  - normalized safe input calls classified prompt, chat, validator, then persists response.
  - parent blocked topic skips guardrails chat and returns safe fallback.
  - classified prompt hard-block/escalate output skips chat when required by `g4`.
  - validator unsafe replaces generated response with fallback.
  - classifier/chat/validator timeout fails closed and records metadata.
  - raw and normalized message are both preserved in metadata.
- Integration tests:
  - safe prompt returns generated answer and validator safe metadata.
  - dangerous prompt creates alert and controlled response.
  - existing thread includes recent context in classified prompt request.
  - voice chat passes `input_mode_optional: "voice"` through backend metadata.
- Mobile verification:
  - existing chat UI works without API changes.
  - unsafe/controlled answers render from returned `answer_text`.
  - transcripts, reports, alerts, and admin views still populate.

## Assumptions

- `pikuai-backend` owns text normalization and orchestration.
- `GUARDRAILS_CLASSIFIED_PROMPT_URL` is the classifier-facing endpoint for this integration.
- The classified prompt endpoint is authoritative for generation prompts; backend does not rewrite its safety prompt.
- Backend calls validator directly to avoid split failure handling.
- Guardrails services are internal only; production access should be restricted by network boundary or service token.
