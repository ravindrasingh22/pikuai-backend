from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.core.security import create_token, require_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_dev_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address.")
        return normalized


class ChangeParentPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


@router.post("/auth/login")
def admin_login(payload: AdminLoginRequest) -> dict[str, object]:
    email = payload.email

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM parent_users WHERE email = %s", (email,))
            parent_match = cursor.fetchone()
            cursor.execute(
                """
                SELECT id::text, full_name, email, role, status, created_at::text, updated_at::text
                FROM admin_users
                WHERE email = %s
                  AND password_hash = crypt(%s, password_hash)
                  AND status = 'active'
                """,
                (email, payload.password),
            )
            admin = cursor.fetchone()

    if parent_match is not None and admin is None:
        raise ApiError("ADMIN_ONLY", "Parent accounts cannot log in to the admin panel.", 403)

    if admin is None:
        raise ApiError("AUTH_REQUIRED", "Invalid admin email or password.", 401)

    return envelope(
        {
            "admin_user": dict(admin),
            "access_token": create_token(admin["id"], "admin", "access"),
            "refresh_token": create_token(admin["id"], "admin", "refresh"),
            "token_type": "bearer",
        },
        "Admin authenticated.",
    )


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users() -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, full_name, email, role, status, created_at::text, updated_at::text,
                       'admin' AS user_type
                FROM admin_users
                ORDER BY created_at DESC
                """
            )
            admin_users = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT id::text, full_name, email, status, country, preferred_language,
                       gender, phone_number, city, timezone, onboarding_status,
                       pin_enabled, created_at::text, 'parent' AS user_type
                FROM parent_users
                ORDER BY created_at DESC
                """
            )
            parent_users = [dict(row) for row in cursor.fetchall()]
            parent_ids = [parent["id"] for parent in parent_users]
            children_by_parent: dict[str, list[dict[str, object]]] = {parent_id: [] for parent_id in parent_ids}
            notifications_by_parent: dict[str, list[dict[str, object]]] = {
                parent_id: [] for parent_id in parent_ids
            }
            controls_by_parent: dict[str, dict[str, object]] = {}
            subscriptions_by_parent: dict[str, dict[str, object]] = {}

            if parent_ids:
                cursor.execute(
                    """
                    SELECT id::text, parent_user_id::text, display_name, age_band,
                           auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                           conversation_visibility_rule, daily_time_limit_minutes,
                           topic_restrictions_json, active_status, created_at::text,
                           updated_at::text
                    FROM child_profiles
                    WHERE parent_user_id = ANY(%s::uuid[])
                    ORDER BY display_name ASC
                    """,
                    (parent_ids,),
                )
                for child in cursor.fetchall():
                    children_by_parent[str(child["parent_user_id"])].append(dict(child))

                cursor.execute(
                    """
                    SELECT parent_user_id::text, transcript_visibility_enabled,
                           content_strictness_level, session_limit_enabled,
                           default_session_limit_minutes, sensitive_topic_alerts_enabled,
                           weekly_summary_enabled, optional_personalization_enabled,
                           retention_policy_code, updated_at::text
                    FROM parent_control_settings
                    WHERE parent_user_id = ANY(%s::uuid[])
                    """,
                    (parent_ids,),
                )
                controls_by_parent = {
                    str(row["parent_user_id"]): dict(row) for row in cursor.fetchall()
                }

                cursor.execute(
                    """
                    SELECT parent_user_id::text, plan_code, billing_cycle, status,
                           starts_at::text, ends_at::text, auto_renew, payment_provider
                    FROM subscriptions
                    WHERE parent_user_id = ANY(%s::uuid[])
                    ORDER BY created_at DESC
                    """,
                    (parent_ids,),
                )
                subscriptions_by_parent = {
                    str(row["parent_user_id"]): dict(row) for row in cursor.fetchall()
                }

                cursor.execute(
                    """
                    SELECT id::text, parent_user_id::text, child_profile_id::text,
                           notification_type, title, body, status, created_at::text
                    FROM admin_notifications
                    WHERE parent_user_id = ANY(%s::uuid[])
                    ORDER BY created_at DESC
                    """,
                    (parent_ids,),
                )
                for notification in cursor.fetchall():
                    notifications_by_parent[str(notification["parent_user_id"])].append(
                        dict(notification)
                    )

            enriched_parent_users = []
            for parent in parent_users:
                parent_id = str(parent["id"])
                parent_notifications = notifications_by_parent.get(parent_id, [])
                parent_children = children_by_parent.get(parent_id, [])
                enriched_parent_users.append(
                    {
                        **parent,
                        "children": parent_children,
                        "controls": controls_by_parent.get(parent_id),
                        "subscription": subscriptions_by_parent.get(parent_id),
                        "notifications": parent_notifications,
                        "summary": {
                            "child_count": len(parent_children),
                            "notification_count": len(parent_notifications),
                            "unread_notification_count": len(
                                [
                                    notification
                                    for notification in parent_notifications
                                    if notification["status"] == "unread"
                                ]
                            ),
                        },
                    }
                )

    return envelope(
        {
            "admin_users": admin_users,
            "parent_users": enriched_parent_users,
            "total_admin_users": len(admin_users),
            "total_parent_users": len(parent_users),
        }
    )


@router.post("/users/{parent_user_id}/reset-pin", dependencies=[Depends(require_admin)])
def reset_parent_pin(parent_user_id: str) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_users
                SET pin_enabled = false,
                    pin_hash = NULL,
                    updated_at = now()
                WHERE id = %s
                  AND status <> 'deleted'
                RETURNING id::text, full_name, email, pin_enabled
                """,
                (parent_user_id,),
            )
            parent = cursor.fetchone()

            if parent is None:
                raise ApiError("NOT_FOUND", "Parent user was not found.", 404)

            cursor.execute(
                """
                INSERT INTO admin_notifications (
                  parent_user_id,
                  notification_type,
                  title,
                  body,
                  status
                )
                VALUES (
                  %s,
                  'security',
                  'Parent PIN reset',
                  'An admin reset this parent PIN. The parent must create a new PIN before using PIN-protected controls.',
                  'unread'
                )
                """,
                (parent_user_id,),
            )

    return envelope(dict(parent), "Parent PIN reset.")


@router.post("/users/{parent_user_id}/change-password", dependencies=[Depends(require_admin)])
def change_parent_password(parent_user_id: str, payload: ChangeParentPasswordRequest) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_users
                SET password_hash = crypt(%s, gen_salt('bf')),
                    updated_at = now()
                WHERE id = %s
                  AND status <> 'deleted'
                RETURNING id::text, full_name, email, status
                """,
                (payload.password, parent_user_id),
            )
            parent = cursor.fetchone()

            if parent is None:
                raise ApiError("NOT_FOUND", "Parent user was not found.", 404)

            cursor.execute(
                """
                INSERT INTO admin_notifications (
                  parent_user_id,
                  notification_type,
                  title,
                  body,
                  status
                )
                VALUES (
                  %s,
                  'security',
                  'Parent password changed',
                  'An admin changed this parent account password.',
                  'unread'
                )
                """,
                (parent_user_id,),
            )

    return envelope(dict(parent), "Parent password changed.")
