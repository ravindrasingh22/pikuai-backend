from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.modules.chat.child_response_service import (
    ChildResponseContext,
    generate_child_response,
    response_metadata,
)
from app.modules.chat.safety import classify_input, render_answer
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class ChatMessageRequest(BaseModel):
    child_profile_id: str = Field(min_length=1)
    thread_id_optional: str | None = None
    message: str = Field(min_length=1, max_length=1000)
    answer_mode_optional: str | None = None
    input_mode_optional: str | None = None
    language_optional: str | None = None


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.post("/message", status_code=201)
def create_message(payload: ChatMessageRequest, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, parent_user_id::text, display_name, age_band,
                       gender, topic_restrictions_json, active_status
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (payload.child_profile_id, parent_id),
            )
            child = cursor.fetchone()

    if child is None:
        raise ApiError("NOT_FOUND", "Child profile was not found.", 404)
    if child["active_status"] != "active":
        raise ApiError("CHILD_PROFILE_INACTIVE", "Archived child profile cannot start chats.", 403)

    existing_thread_id = None
    previous_memory: dict[str, object] | None = None
    recent_messages: list[dict[str, object]] = []
    if payload.thread_id_optional:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id::text
                    FROM chat_threads
                    WHERE id = %s
                      AND parent_user_id = %s
                      AND child_profile_id = %s
                    """,
                    (payload.thread_id_optional, parent_id, child["id"]),
                )
                thread = cursor.fetchone()
                if thread is None:
                    raise ApiError("NOT_FOUND", "Chat thread was not found.", 404)
                existing_thread_id = thread["id"]
                cursor.execute(
                    """
                    SELECT sender_type, rendered_text, metadata_json
                    FROM chat_messages
                    WHERE parent_user_id = %s
                      AND thread_id = %s
                    ORDER BY created_at DESC
                    LIMIT 8
                    """,
                    (parent_id, existing_thread_id),
                )
                recent_rows = cursor.fetchall()
        recent_messages = list(reversed(recent_rows))
        for row in recent_rows:
            if row.get("sender_type") != "assistant":
                continue
            metadata = row.get("metadata_json") or {}
            if not isinstance(metadata, dict):
                continue
            memory = metadata.get("thread_memory")
            if isinstance(memory, dict):
                previous_memory = memory
                break

    restricted_topics = [str(topic).lower() for topic in child.get("topic_restrictions_json", [])]
    matched_restricted_topic = next(
        (topic for topic in restricted_topics if topic and topic in payload.message.lower()),
        None,
    )

    moderation = classify_input(payload.message)
    if matched_restricted_topic and moderation["policy_bucket"] == "allowed":
        moderation = {
            "policy_bucket": "block_and_redirect",
            "category": "parent_blocked_topic",
            "severity": 80,
            "reason_codes": [f"parent_blocked_topic:{matched_restricted_topic}"],
        }

    fallback_answer = render_answer(payload.message, str(child["age_band"]), moderation["policy_bucket"])
    if moderation["policy_bucket"] in {"allowed", "allowed_with_adaptation"}:
        response_orchestration = generate_child_response(
            ChildResponseContext(
                child_age_group=str(child["age_band"]),
                child_gender=str(child.get("gender") or "not_disclosed"),
                child_name=str(child["display_name"]),
                child_pattern="curious",
                language=payload.language_optional or "en",
                policy_bucket=moderation["policy_bucket"],
                safety_category=moderation["category"],
                requested_answer_mode=payload.answer_mode_optional,
                fallback_text=fallback_answer,
                message=payload.message,
                recent_messages=recent_messages,
                previous_memory=previous_memory,
            )
        )
        llm_result = response_orchestration.llm
        answer = llm_result["text"]
    else:
        response_orchestration = None
        llm_result = {
            "text": fallback_answer,
            "provider": "policy_renderer",
            "model": "deterministic_safety_response",
            "used_fallback": False,
            "error": None,
        }
        answer = fallback_answer

    explanation_text = (
        f"Input classified as {moderation['category']}; final bucket "
        f"{moderation['policy_bucket']}; age band {child['age_band']}."
    )
    moderation_status = {
        "allowed": "passed",
        "allowed_with_adaptation": "adapted",
        "block_and_redirect": "blocked",
        "escalate": "escalated",
    }[moderation["policy_bucket"]]
    is_unsafe = moderation["policy_bucket"] in {"escalate", "block_and_redirect"}
    input_mode = "voice" if payload.input_mode_optional == "voice" else "text"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            if existing_thread_id:
                thread_id = existing_thread_id
            else:
                cursor.execute(
                    """
                    INSERT INTO chat_threads (
                      parent_user_id,
                      child_profile_id,
                      title,
                      last_policy_bucket
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id::text
                    """,
                    (parent_id, child["id"], payload.message[:54], moderation["policy_bucket"]),
                )
                thread_id = cursor.fetchone()["id"]

            common_values = (
                thread_id,
                parent_id,
                child["id"],
                child["age_band"],
                moderation["policy_bucket"],
                moderation["category"],
                moderation_status,
                moderation["reason_codes"][0],
                explanation_text,
                (response_orchestration.answer_mode if response_orchestration else "parent_safe_redirect"),
                llm_result["model"],
                Jsonb(
                    {
                        "llm_provider": llm_result["provider"],
                        "llm_used_fallback": llm_result["used_fallback"],
                        "llm_error": llm_result["error"],
                        "unsafe_detected": is_unsafe,
                        "reason_codes": moderation["reason_codes"],
                        "input_mode": input_mode,
                        **(response_metadata(response_orchestration) if response_orchestration else {}),
                    }
                ),
            )
            cursor.execute(
                """
                INSERT INTO chat_messages (
                  thread_id, parent_user_id, child_profile_id, sender_type,
                  message_text, rendered_text, age_band_used, policy_bucket,
                  safety_category, moderation_status, explanation_code,
                  explanation_text, answer_mode, ai_model_used, metadata_json
                )
                VALUES (%s, %s, %s, 'child', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id::text
                """,
                (
                    common_values[0],
                    common_values[1],
                    common_values[2],
                    payload.message,
                    payload.message,
                    *common_values[3:],
                ),
            )
            child_message_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO chat_messages (
                  thread_id, parent_user_id, child_profile_id, sender_type,
                  message_text, rendered_text, age_band_used, policy_bucket,
                  safety_category, moderation_status, explanation_code,
                  explanation_text, answer_mode, ai_model_used, metadata_json
                )
                VALUES (%s, %s, %s, 'assistant', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id::text
                """,
                (
                    common_values[0],
                    common_values[1],
                    common_values[2],
                    answer,
                    answer,
                    *common_values[3:],
                ),
            )
            cursor.fetchone()

            alert_id = None
            if is_unsafe:
                cursor.execute(
                    """
                    INSERT INTO admin_notifications (
                      parent_user_id,
                      child_profile_id,
                      thread_id,
                      message_id,
                      notification_type,
                      title,
                      body,
                      status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'unread')
                    RETURNING id::text
                    """,
                    (
                        parent_id,
                        child["id"],
                        thread_id,
                        child_message_id,
                        moderation["category"],
                        f"{str(moderation['category']).replace('_', ' ').title()} detected",
                        f"{payload.message} | Reasons: {', '.join(moderation['reason_codes'])}",
                    ),
                )
                alert_id = cursor.fetchone()["id"]
                cursor.execute(
                    "UPDATE chat_messages SET alert_id_optional = %s WHERE id = %s",
                    (alert_id, child_message_id),
                )

            cursor.execute(
                """
                UPDATE chat_threads
                SET last_policy_bucket = %s,
                    last_alert_id_optional = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (moderation["policy_bucket"], alert_id, thread_id),
            )
        connection.commit()

    return envelope(
        {
            "thread_id": thread_id,
            "message_id": child_message_id,
            "answer_text": answer,
            "ai_model_used": llm_result["model"],
            "llm_provider": llm_result["provider"],
            "llm_used_fallback": llm_result["used_fallback"],
            "policy_bucket": moderation["policy_bucket"],
            "explanation_summary": explanation_text,
            "available_answer_modes": ["quick_answer", "guided_learning", "comforting", "playful", "parent_safe_redirect"],
            "alert_created": is_unsafe,
            "child_safe_status": "safe" if moderation["policy_bucket"] == "allowed" else "controlled",
        },
        "Message processed safely.",
    )


@router.get("/threads")
def list_threads(
    child_profile_id: str | None = None,
    claims: TokenClaims = Depends(require_parent_or_admin),
) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if child_profile_id is None:
                cursor.execute(
                    """
                    SELECT id::text, child_profile_id::text, title, status,
                           last_policy_bucket, last_alert_id_optional::text,
                           created_at::text, updated_at::text
                    FROM chat_threads
                    WHERE parent_user_id = %s
                    ORDER BY updated_at DESC
                    """,
                    (parent_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id::text, child_profile_id::text, title, status,
                           last_policy_bucket, last_alert_id_optional::text,
                           created_at::text, updated_at::text
                    FROM chat_threads
                    WHERE parent_user_id = %s
                      AND child_profile_id = %s
                    ORDER BY updated_at DESC
                    """,
                    (parent_id, child_profile_id),
                )
            threads = [dict(row) for row in cursor.fetchall()]
    return envelope(threads)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, child_profile_id::text, title, status,
                       last_policy_bucket, last_alert_id_optional::text,
                       created_at::text, updated_at::text
                FROM chat_threads
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (thread_id, parent_id),
            )
            thread = cursor.fetchone()
            if thread is None:
                raise ApiError("NOT_FOUND", "Thread was not found.", 404)
            cursor.execute(
                """
                SELECT id::text, sender_type, rendered_text, policy_bucket,
                       explanation_text, safety_category, created_at::text
                FROM chat_messages
                WHERE thread_id = %s
                  AND parent_user_id = %s
                ORDER BY created_at ASC
                """,
                (thread_id, parent_id),
            )
            messages = [dict(row) for row in cursor.fetchall()]
    return envelope({"thread": dict(thread), "messages": messages})
