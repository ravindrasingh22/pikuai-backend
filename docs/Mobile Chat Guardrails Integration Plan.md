# Orchestration of Guardrails Integration Plan in pikuai-backend and admin services

## Summary

Keep `pikuai-app` on one product endpoint: `POST /api/v1/chat/message`. `pikuai-backend` owns guardrails orchestration, product policy, context placeholder handling, persistence, alerts, admin configuration, and response shaping.

Final flow: mobile -> backend -> text normalization -> context curation placeholder -> classified prompt generation -> chat generation -> validator -> backend persistence/token usage/admin reporting -> mobile response.

## Backend And Admin Configuration

- Add backend guardrails configuration:
  - `GUARDRAILS_ENABLED=true`
  - `GUARDRAILS_TEXT_NORMALIZATION_ENABLED=true`
  - `GUARDRAILS_TEXT_NORMALIZATION_URL=http://localhost:4002/api/v1/guardrail/text-normalization`
  - `GUARDRAILS_CLASSIFIED_PROMPT_ENABLED=true`
  - `GUARDRAILS_CLASSIFIED_PROMPT_URL=http://localhost:4001/api/v1/guardrail/classified/prompt`
  - `GUARDRAILS_CHAT_URL=http://localhost:4003/api/v1/guardrail/chat`
  - `GUARDRAILS_DEFAULT_SYSTEM_PROMPT` for chat generation when classified prompt is disabled or unavailable.
  - `GUARDRAILS_VALIDATOR_ENABLED=true`
  - `GUARDRAILS_VALIDATOR_URL=http://localhost:4002/api/v1/guardrail/validate`
  - `GUARDRAILS_VALIDATOR_THRESHOLD=0.85`
  - `GUARDRAILS_FALLBACK_RESPONSE` for generic safe fallback text.
- Add admin panel controls for guardrails:
  - enable/disable full guardrails orchestration.
  - enable/disable text normalization with editable endpoint URL.
  - enable/disable classified prompt generation with editable endpoint URL.
  - configure chat LLM endpoint URL; chat stays always enabled while guardrails orchestration is enabled.
  - configure default backend system prompt used when classified prompt generation is disabled or unavailable.
  - enable/disable validator with editable endpoint URL and pass threshold.
  - configure generic fallback response returned when validation fails.
- Admin configuration should be stored in backend DB and loaded by chat orchestration at runtime, with environment variables as defaults.

## Orchestration Flow

- Mobile stays unchanged:
  - `sendChildMessage()` continues calling `/chat/message`.
  - No guardrails URLs or orchestration logic are exposed to the mobile app.
- Backend starts each chat request by loading:
  - parent, child profile, controls, restricted topics, thread, recent messages, and existing thread memory.
  - raw child input exactly as received.
- Text normalization:
  - If enabled, backend calls `GUARDRAILS_TEXT_NORMALIZATION_URL` before classification/prompt generation.
  - This is required because children can type with spelling mistakes, mixed casing, punctuation issues, incomplete wording, code-mixed language, or other noisy input.
  - Backend preserves both raw input and normalized input in metadata.
  - If text normalization is disabled, backend uses raw input as normalized input.
  - If text normalization fails, backend records the failure and uses raw input unless admin config requires fail-closed.
- Context curation:
  - Context generation is separate from guardrails orchestration.
  - For this integration, create a backend placeholder for context curation.
  - The placeholder returns the default recent context as-is.
  - Send that default context to guardrails endpoints without adding separate context intelligence yet.
- Classified prompt generation:
  - If enabled, backend sends normalized text, child profile, session id, and curated/default context to `GUARDRAILS_CLASSIFIED_PROMPT_URL`.
  - This endpoint is treated as the child-safe system prompt generator for the LLM.
  - Backend uses the returned `prompts` as the authoritative prompt payload for chat generation.
  - Backend stores `prompt_checklist` and full `classifier_output` for audit/admin reporting.
  - If classified prompt generation is disabled or unavailable, backend builds chat `messages` with `GUARDRAILS_DEFAULT_SYSTEM_PROMPT` plus the normalized child message.
- Chat generation:
  - Chat generation stays enabled whenever guardrails orchestration is enabled.
  - Backend builds the chat payload from classified prompt `prompts` when available; otherwise it uses the configured default system prompt.
  - Backend calls `GUARDRAILS_CHAT_URL` with `validate_response: false`.
  - Validation remains owned by backend orchestration so threshold/fallback behavior is consistent.
- Validator:
  - If validator is enabled, backend sends the generated assistant response and child profile to `GUARDRAILS_VALIDATOR_URL`.
  - If `response_validation` passes and `validation_score` is greater than or equal to configured threshold, backend returns the generated response to the child chat interface.
  - If validator is disabled, backend returns the generated response but records that validation was skipped.
  - If validator fails, returns unsafe, or returns a score below threshold, backend returns the configured generic fallback response to the app.
- Persistence:
  - Backend saves all stage input/output metadata in DB for each chat message.
  - Backend also stores token usage from each stage in a separate table for later user-based reconciliation.

## API Contracts

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
      "content": "You are PikuAI, a child-safe learning assistant.\nThe child is in age band 11-12; use explanation depth GUIDED_REASONING, style Balanced, plain definitions, and age-calibrated wording.\nRespond in 5 lines or less.\nActive safety rules: Refuse harmful, exploitative, or inappropriate content and redirect safely. Careful, measured, avoids overclaiming. Ask a brief clarifying question before answering. Encourage the child to reach out to a trusted adult, parent, teacher, caregiver, counselor, doctor, or helpline as appropriate. No special escalation. Give standard guidance with no special safety framing. Warm, kind, reassuring, non-judgmental.\nNo additional prompt-policy notes are active.\nContext: none"
    },
    {
      "role": "user",
      "content": "I feel alone because mama works even on Sunday. I feel like I am reaching my limit."
    }
  ],
  "prompt_checklist": {
    "passed": true,
    "checks": {
      "CHK-01": true,
      "CHK-02": true,
      "CHK-03": true,
      "CHK-04": true,
      "CHK-05": true,
      "CHK-06": true,
      "CHK-07": true,
      "CHK-08": true,
      "CHK-09": true
    }
  },
  "classifier_output": {
    "input": {
      "user_input": "I feel alone because mama works even on Sunday. I feel like I am reaching my limit.",
      "context": []
    },
    "classifier": {
      "trained": true,
      "backend": "slm",
      "core_model": "deberta",
      "threshold": 0.8
    },
    "g1": {
      "id": "GENERIC",
      "score": 0.9872938990592957,
      "reason": "The question is handled as a general child-safety question rather than a domain-specific knowledge request."
    },
    "g2": {
      "id": "AMBIGUOUS_RISK",
      "score": 0.8789287209510803,
      "model_score": 0.8789287209510803,
      "score_source": "g2_head",
      "reason_code": "AMBIGUOUS_RISK",
      "reason": "AMBIGUOUS_RISK: Ambiguous / Dual-Use Risk. Query has benign and harmful interpretations; clarification is needed. Severity floor is SV2. Classifier evidence: The question could have both safe and unsafe interpretations."
    },
    "active_flags": [
      {
        "id": "has_ambiguous_risk",
        "score": 0.8752655386924744,
        "source": "trained_flag_head"
      },
      {
        "id": "has_clinical_concern",
        "score": 0.9912347793579102,
        "source": "trained_flag_head"
      },
      {
        "id": "has_emotional_distress",
        "score": 0.9990768432617188,
        "source": "trained_flag_head"
      }
    ],
    "g3": {
      "G3_SV": "SV2",
      "G3_MOD": [
        "boundary_setting",
        "cautious",
        "clarify_context",
        "encourage_help_seeking",
        "none",
        "normal_advice",
        "supportive"
      ],
      "G3_FORWARD": {
        "severity": "SV2",
        "modifiers": [
          "boundary_setting",
          "cautious",
          "clarify_context",
          "encourage_help_seeking",
          "none",
          "normal_advice",
          "supportive"
        ]
      }
    },
    "g4": {
      "action": "TRANSFORM",
      "variant": "base",
      "ending": "curiosity_invite",
      "style": "Neutral, balanced"
    },
    "age_policy": {
      "age_band": "11-12",
      "Max_Answer_Style": "Balanced, plain definitions",
      "Max_Words": 160,
      "Depth": "GUIDED_REASONING"
    },
    "usage": {
      "prompt_tokens": 55,
      "completion_tokens": 0,
      "total_tokens": 55
    },
    "modifier_tags": {
      "mappings": [
        {
          "flag": "has_ambiguous_risk",
          "tone": {
            "tag": "cautious",
            "description": "Careful, measured, avoids overclaiming."
          },
          "action": {
            "tag": "clarify_context",
            "description": "Ask a brief clarifying question before answering."
          },
          "escalation": {
            "tag": "none",
            "description": "No special escalation."
          }
        },
        {
          "flag": "has_clinical_concern",
          "tone": {
            "tag": "supportive",
            "description": "Warm, kind, reassuring, non-judgmental."
          },
          "action": {
            "tag": "boundary_setting",
            "description": "Refuse harmful, exploitative, or inappropriate content and redirect safely."
          },
          "escalation": {
            "tag": "encourage_help_seeking",
            "description": "Encourage the child to reach out to a trusted adult, parent, teacher, caregiver, counselor, doctor, or helpline as appropriate."
          }
        },
        {
          "flag": "has_emotional_distress",
          "tone": {
            "tag": "supportive",
            "description": "Warm, kind, reassuring, non-judgmental."
          },
          "action": {
            "tag": "normal_advice",
            "description": "Give standard guidance with no special safety framing."
          },
          "escalation": {
            "tag": "none",
            "description": "No special escalation."
          }
        }
      ],
      "tone": [
        {
          "tag": "cautious",
          "description": "Careful, measured, avoids overclaiming."
        },
        {
          "tag": "supportive",
          "description": "Warm, kind, reassuring, non-judgmental."
        }
      ],
      "action": [
        {
          "tag": "boundary_setting",
          "description": "Refuse harmful, exploitative, or inappropriate content and redirect safely."
        },
        {
          "tag": "clarify_context",
          "description": "Ask a brief clarifying question before answering."
        },
        {
          "tag": "normal_advice",
          "description": "Give standard guidance with no special safety framing."
        }
      ],
      "escalation": [
        {
          "tag": "encourage_help_seeking",
          "description": "Encourage the child to reach out to a trusted adult, parent, teacher, caregiver, counselor, doctor, or helpline as appropriate."
        },
        {
          "tag": "none",
          "description": "No special escalation."
        }
      ]
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
    "content": "let me kiss the bulb."
  },
  "child_profile": {
    "age": 19,
    "age_group": "19",
    "language": "en"
  }
}
```

### Validator Response

```json
{
  "response_validation": "Safe",
  "validation_score": 0.92,
  "validator_usage": {
    "prompt_tokens": 9,
    "completion_tokens": 0,
    "total_tokens": 9
  }
}
```

## Persistence And Admin Reporting

- Save stage metadata for every chat request:
  - raw child input.
  - normalized child input.
  - context placeholder output.
  - classified prompt request and response.
  - selected system prompt and user prompt.
  - chat request and LLM response.
  - validator request and response.
  - final response returned to app.
  - fallback reason if fallback was used.
- Store stage token usage in a separate table for reconciliation:
  - parent user id.
  - child profile id.
  - thread id.
  - message id.
  - stage name: `text_normalization`, `classified_prompt`, `chat`, `validator`.
  - provider/model where available.
  - prompt tokens, completion tokens, total tokens.
  - created timestamp.
- Admin should be able to query one chat call and see:
  - detailed chat message.
  - G1/G2 classification and scores.
  - active flags and scores.
  - generated system prompt.
  - chat response LLM/provider/model.
  - validator response and score.
  - total token usage across stages.
  - final delivered response versus fallback response.

## Test Plan

- Backend unit tests:
  - text normalization enabled calls normalization endpoint before classified prompt.
  - text normalization disabled skips normalization and uses raw input.
  - context curation placeholder returns default recent context unchanged.
  - classified prompt request uses normalized input, context, child profile, and session id.
  - classified prompt disabled skips classified prompt endpoint and uses default backend system prompt.
  - chat request uses returned classified prompt messages with `validate_response: false` when classified prompt is enabled.
  - chat request uses default system prompt with `validate_response: false` when classified prompt is disabled.
  - validator enabled and passing threshold returns generated response.
  - validator enabled and below threshold returns configured generic fallback.
  - validator disabled returns generated response and records validation skipped.
  - every stage records metadata and token usage.
- Integration tests:
  - safe prompt returns generated answer and validator metadata.
  - emotional/ambiguous prompt records G1/G2, active flags, prompt checklist, and validator score.
  - dangerous prompt creates alert and controlled response.
  - existing thread sends default recent context to classified prompt endpoint.
  - voice chat passes input-mode metadata through backend.
- Admin verification:
  - guardrails orchestration can be enabled/disabled from admin.
  - text normalization checkbox and endpoint config save correctly.
  - classified prompt checkbox and endpoint config save correctly.
  - default chat system prompt config saves correctly.
  - validator threshold and fallback response config save correctly.
  - admin can inspect per-call classification, prompt, chat, validator, and token usage details.

## Assumptions

- `pikuai-backend` owns orchestration and persistence.
- Text normalization is an internal guardrails call made before classified prompt generation.
- Context generation is intentionally separate and only a placeholder in this phase.
- `GUARDRAILS_CLASSIFIED_PROMPT_URL` is the child-safe system prompt generator when classified prompt generation is enabled.
- Backend does not rewrite the classified prompt safety instructions.
- `GUARDRAILS_CHAT_URL` remains required and enabled while guardrails orchestration is enabled.
- `GUARDRAILS_DEFAULT_SYSTEM_PROMPT` is used when classified prompt generation is disabled or unavailable.
- Backend calls validator directly and owns threshold/fallback behavior.
- Guardrails services are internal only; production access should be restricted by network boundary or service token.
