# Mobile Chat Guardrails Integration Plan

## Summary
Use `pikuai-backend` as the single product-facing orchestration layer. The mobile app should continue calling only `POST /api/v1/chat/message`; it should not call guardrails directly. `pikuai-backend` will call the guardrails services internally in this order: classifier -> chat generation -> validator -> persistence/alerts/response.

This is the right shape because `pikuai-backend` already owns auth, parent/child lookup, controls, thread memory, transcript persistence, reports, and alerts. Guardrails should stay focused on safety/model decisions, not product state.

## Key Changes
- Keep mobile API stable:
  - `pikuai-app` continues using `sendChildMessage()` -> `/chat/message`.
  - No classifier/chat/validator URLs or safety logic are exposed to the app.
- Add guardrails service config in `pikuai-backend`:
  - `GUARDRAILS_CLASSIFIER_URL=http://localhost:4001/api/v1/guardrail/classify`
  - `GUARDRAILS_CHAT_URL=http://localhost:4003/api/v1/guardrail/chat`
  - `GUARDRAILS_VALIDATOR_URL=http://localhost:4002/api/v1/guardrail/validate`
  - `GUARDRAILS_ENABLED=true`
  - timeouts and fail-closed behavior per service.
- Add a backend guardrails client/orchestrator:
  - Build classifier payload from child profile, message, thread context, language, and session/thread id.
  - Map classifier `g1`, `g2`, `g3`, `g4`, flags, age policy, and usage into backend moderation metadata.
  - If classifier returns hard block/escalate, skip generation and render a safe redirect/fallback.
  - If transform/allow, build chat messages using backend prompt/thread memory plus classifier age policy and modifier tags.
  - Send generation request to guardrails chat with `validate_response: false`; backend calls validator itself so it controls retries/fallbacks consistently.
  - Validate final assistant text with validator.
  - If validator says unsafe or validator is unavailable, fail closed with backend safe fallback text.
- Persist full audit metadata in `chat_messages.metadata_json`:
  - classifier output, selected route/action, chat model/provider/usage, validator result/score/usage, fallback reason, and service errors.
  - Keep existing `policy_bucket`, `safety_category`, `moderation_status`, alerts, reports, and explainability behavior compatible.

## API And Data Flow
- Mobile request remains:
  - `child_profile_id`
  - `thread_id_optional`
  - `message`
  - `answer_mode_optional`
  - `input_mode_optional`
  - `language_optional`
- Backend response remains compatible:
  - `thread_id`
  - `message_id`
  - `answer_text`
  - `policy_bucket`
  - `explanation_summary`
  - `alert_created`
  - `child_safe_status`
  - optional additions: `classification`, `validation`, `ai_model_used`, `llm_provider` if useful for admin/debug.
- Internal backend flow:
  - Authenticate parent.
  - Load child profile, parent controls, restricted topics, thread memory, recent messages.
  - Call classifier.
  - Apply parent controls/topic restrictions as backend override after classifier.
  - Generate answer only when allowed/transform route permits it.
  - Validate answer.
  - Store child + assistant messages.
  - Create alert if classifier/validator/backend policy requires it.
  - Return safe final response to mobile.

## Test Plan
- Backend unit tests:
  - allowed message calls classifier, chat, validator, then persists safe assistant response.
  - hard-block classifier result skips chat and creates controlled safe fallback.
  - validator unsafe result replaces generated answer with fallback and marks metadata.
  - classifier/chat/validator timeout fails closed without crashing mobile.
  - parent blocked topic overrides classifier allow.
  - existing thread memory is included in classifier/chat payload.
- Mobile tests:
  - existing chat screen still works with unchanged `/chat/message` contract.
  - unsafe response state displays returned `answer_text` and `policy_bucket`.
  - voice chat still passes `input_mode_optional: "voice"`.
- Integration checks:
  - run classifier on port `4001`, validator on `4002`, chat on `4003`, backend on `4000`.
  - send one safe prompt, one dangerous prompt, one validator-triggering unsafe generated answer mock.
  - confirm transcripts, reports, alerts, and admin views still populate.

## Assumptions
- Next milestone uses separate internal guardrails services, not one public pipeline endpoint.
- `pepiko-gaurdrails` is the current guardrails repo, despite the user-facing name `pikuai-gaurdrails`.
- Backend should be the only service trusted by mobile clients.
- Guardrails services are internal and unauthenticated locally; production should restrict them by network boundary or service token.
- Chat service’s built-in validator call should be disabled for backend orchestration to avoid double validation and split failure handling.
