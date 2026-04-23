from fastapi import APIRouter, Depends

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.get("")
@router.get("/")
def list_transcripts(
    child_profile_id: str | None = None,
    status: str | None = None,
    claims: TokenClaims = Depends(require_parent_or_admin),
) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if child_profile_id is None:
                cursor.execute(
                    """
                    SELECT id::text, child_profile_id::text, title, status,
                           last_policy_bucket, created_at::text, updated_at::text
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
                           last_policy_bucket, created_at::text, updated_at::text
                    FROM chat_threads
                    WHERE parent_user_id = %s
                      AND child_profile_id = %s
                    ORDER BY updated_at DESC
                    """,
                    (parent_id, child_profile_id),
                )
            threads = [dict(row) for row in cursor.fetchall()]
            for thread in threads:
                if status is None:
                    cursor.execute(
                        """
                        SELECT id::text, sender_type, rendered_text, policy_bucket,
                               explanation_text, safety_category,
                               metadata_json->>'input_mode' AS input_mode,
                               created_at::text
                        FROM chat_messages
                        WHERE parent_user_id = %s
                          AND thread_id = %s
                        ORDER BY created_at ASC
                        """,
                        (parent_id, thread["id"]),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id::text, sender_type, rendered_text, policy_bucket,
                               explanation_text, safety_category,
                               metadata_json->>'input_mode' AS input_mode,
                               created_at::text
                        FROM chat_messages
                        WHERE parent_user_id = %s
                          AND thread_id = %s
                          AND policy_bucket = %s
                        ORDER BY created_at ASC
                        """,
                        (parent_id, thread["id"], status),
                    )
                thread["messages"] = [dict(row) for row in cursor.fetchall()]
    return envelope(threads)


@router.get("/threads/{thread_id}")
def get_transcript_thread(thread_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, child_profile_id::text, title, status,
                       last_policy_bucket, created_at::text, updated_at::text
                FROM chat_threads
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (thread_id, parent_id),
            )
            thread = cursor.fetchone()
            if thread is None:
                raise ApiError("NOT_FOUND", "Transcript thread was not found.", 404)
            cursor.execute(
                """
                SELECT id::text, sender_type, rendered_text, policy_bucket,
                       explanation_text, safety_category,
                       metadata_json->>'input_mode' AS input_mode,
                       created_at::text
                FROM chat_messages
                WHERE parent_user_id = %s
                  AND thread_id = %s
                ORDER BY created_at ASC
                """,
                (parent_id, thread_id),
            )
            messages = [dict(row) for row in cursor.fetchall()]
    return envelope({"thread": dict(thread), "messages": messages})
