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
def list_notifications(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, notification_type AS type, title, body, status,
                       created_at::text, id::text AS alert_id_optional,
                       child_profile_id::text
                FROM admin_notifications
                WHERE parent_user_id = %s
                ORDER BY created_at DESC
                """,
                (parent_id,),
            )
            notifications = [dict(row) for row in cursor.fetchall()]
    return envelope(notifications)


@router.post("/{notification_id}/read")
def mark_notification_read(notification_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE admin_notifications
                SET status = 'read'
                WHERE id = %s
                  AND parent_user_id = %s
                RETURNING id::text, notification_type AS type, title, body, status,
                          created_at::text, id::text AS alert_id_optional,
                          child_profile_id::text
                """,
                (notification_id, parent_id),
            )
            notification = cursor.fetchone()
        connection.commit()
    if notification is None:
        raise ApiError("NOT_FOUND", "Notification was not found.", 404)
    return envelope(dict(notification), "Notification marked read.")
