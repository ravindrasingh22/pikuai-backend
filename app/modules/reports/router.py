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


@router.get("/summary")
def report_summary(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS child_count FROM child_profiles WHERE parent_user_id = %s AND active_status = 'active'",
                (parent_id,),
            )
            child_count = int(cursor.fetchone()["child_count"])
            cursor.execute("SELECT COUNT(*) AS thread_count FROM chat_threads WHERE parent_user_id = %s", (parent_id,))
            thread_count = int(cursor.fetchone()["thread_count"])
            cursor.execute(
                """
                SELECT sender_type, COUNT(*) AS count
                FROM chat_messages
                WHERE parent_user_id = %s
                GROUP BY sender_type
                """,
                (parent_id,),
            )
            message_counts = {str(row["sender_type"]): int(row["count"]) for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT policy_bucket, COUNT(*) AS count
                FROM chat_messages
                WHERE parent_user_id = %s
                  AND sender_type = 'child'
                GROUP BY policy_bucket
                """,
                (parent_id,),
            )
            policy_counts = {str(row["policy_bucket"]): int(row["count"]) for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT safety_category, COUNT(*) AS count
                FROM chat_messages
                WHERE parent_user_id = %s
                  AND sender_type = 'child'
                GROUP BY safety_category
                ORDER BY count DESC
                LIMIT 5
                """,
                (parent_id,),
            )
            category_counts = {str(row["safety_category"]): int(row["count"]) for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM admin_notifications
                WHERE parent_user_id = %s
                GROUP BY status
                """,
                (parent_id,),
            )
            alert_counts = {str(row["status"]): int(row["count"]) for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT id::text, thread_id::text, rendered_text, policy_bucket,
                       explanation_text, created_at::text
                FROM chat_messages
                WHERE parent_user_id = %s
                  AND sender_type = 'child'
                  AND policy_bucket <> 'allowed'
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (parent_id,),
            )
            oversight_rows = [dict(row) for row in cursor.fetchall()]

    return envelope(
        {
            "usage": {
                "children": child_count,
                "threads": thread_count,
                "child_messages": message_counts.get("child", 0),
                "assistant_messages": message_counts.get("assistant", 0),
            },
            "safety": {
                "policy_buckets": policy_counts,
                "top_categories": category_counts,
                "open_alerts": alert_counts.get("unread", 0),
                "reviewed_alerts": alert_counts.get("read", 0),
                "resolved_alerts": alert_counts.get("resolved", 0),
            },
            "oversight": [
                {
                    "message_id": row["id"],
                    "thread_id": row["thread_id"],
                    "highlight": row["rendered_text"],
                    "policy_bucket": row["policy_bucket"],
                    "explanation": row["explanation_text"],
                    "created_at": row["created_at"],
                }
                for row in oversight_rows
            ],
            "report_types": [
                "usage",
                "safety",
                "alerts",
                "transcripts",
                "explainable_oversight",
                "billing",
            ],
        }
    )
