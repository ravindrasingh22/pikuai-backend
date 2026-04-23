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
def list_alerts(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, parent_user_id::text, child_profile_id::text,
                       thread_id::text, message_id::text,
                       notification_type AS alert_type,
                       CASE WHEN status = 'unread' THEN 'open' ELSE status END AS status,
                       notification_type AS severity,
                       body AS triggered_reason,
                       created_at::text
                FROM admin_notifications
                WHERE parent_user_id = %s
                ORDER BY created_at DESC
                """,
                (parent_id,),
            )
            alerts = [dict(row) for row in cursor.fetchall()]
    return envelope(alerts)


@router.get("/{alert_id}")
def get_alert(alert_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, parent_user_id::text, child_profile_id::text,
                       thread_id::text, message_id::text,
                       notification_type AS alert_type,
                       CASE WHEN status = 'unread' THEN 'open' ELSE status END AS status,
                       notification_type AS severity,
                       body AS triggered_reason,
                       created_at::text
                FROM admin_notifications
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (alert_id, parent_id),
            )
            alert = cursor.fetchone()
    if alert is None:
        raise ApiError("NOT_FOUND", "Safety alert was not found.", 404)
    return envelope(dict(alert))
