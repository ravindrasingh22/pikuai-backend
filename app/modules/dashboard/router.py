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


@router.get("/overview")
def overview(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS child_count FROM child_profiles WHERE parent_user_id = %s AND active_status = 'active'",
                (parent_id,),
            )
            child_count = int(cursor.fetchone()["child_count"])
            cursor.execute(
                """
                SELECT COALESCE(subscription.plan_code, 'starter') AS plan_code,
                       plan.title AS plan_title,
                       plan.allowed_child_count
                FROM (SELECT %s::uuid AS parent_user_id) parent_scope
                LEFT JOIN LATERAL (
                  SELECT plan_code
                  FROM subscriptions
                  WHERE parent_user_id = parent_scope.parent_user_id
                    AND status = 'active'
                  ORDER BY created_at DESC
                  LIMIT 1
                ) subscription ON true
                LEFT JOIN billing_plans plan
                  ON plan.code = COALESCE(subscription.plan_code, 'starter')
                """,
                (parent_id,),
            )
            subscription = cursor.fetchone()
            cursor.execute(
                "SELECT COUNT(*) AS pending_alerts FROM admin_notifications WHERE parent_user_id = %s AND status = 'unread'",
                (parent_id,),
            )
            pending_alerts = int(cursor.fetchone()["pending_alerts"])
            cursor.execute(
                """
                SELECT id::text, child_profile_id::text, title, last_policy_bucket,
                       updated_at::text
                FROM chat_threads
                WHERE parent_user_id = %s
                  AND last_policy_bucket IN ('block_and_redirect', 'escalate')
                ORDER BY updated_at DESC
                LIMIT 5
                """,
                (parent_id,),
            )
            unsafe_threads = [dict(row) for row in cursor.fetchall()]

    return envelope(
        {
            "child_count": child_count,
            "current_plan": subscription["plan_code"] if subscription else "starter",
            "current_plan_title": subscription["plan_title"] if subscription else "Starter - 1 child plan",
            "allowed_child_count": int(subscription["allowed_child_count"] or 1) if subscription else 1,
            "can_add_child": child_count < (int(subscription["allowed_child_count"] or 1) if subscription else 1),
            "weekly_sessions": 0,
            "pending_alerts": pending_alerts,
            "top_topics": [],
            "recent_activity": unsafe_threads,
        }
    )
