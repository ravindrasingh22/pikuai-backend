from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel, Field, field_validator

from app.core.security import create_token, require_admin
from app.db.session import get_connection
from app.modules.guardrails.client import guardrails_public_config, update_guardrails_runtime_config
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


class ChangeParentPlanRequest(BaseModel):
    plan_code: str = Field(min_length=1)
    billing_cycle: str = "monthly"


class GuardrailsConfigPatch(BaseModel):
    enabled: bool | None = None
    text_normalization_enabled: bool | None = None
    text_normalization_url: str | None = None
    text_normalization_system_prompt: str | None = None
    context_enabled: bool | None = None
    context_recent_message_limit: int | None = Field(default=None, ge=0, le=50)
    classified_prompt_enabled: bool | None = None
    classified_prompt_url: str | None = None
    chat_url: str | None = None
    default_system_prompt: str | None = None
    validator_enabled: bool | None = None
    validator_url: str | None = None
    validator_threshold: float | None = Field(default=None, ge=0, le=1)
    fallback_response: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)


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
                    SELECT DISTINCT ON (subscription.parent_user_id)
                           subscription.parent_user_id::text,
                           subscription.plan_code,
                           plan.title AS plan_title,
                           plan.allowed_child_count,
                           subscription.billing_cycle,
                           subscription.status,
                           subscription.starts_at::text,
                           subscription.ends_at::text,
                           subscription.auto_renew,
                           subscription.payment_provider
                    FROM subscriptions AS subscription
                    LEFT JOIN billing_plans plan ON plan.code = subscription.plan_code
                    WHERE subscription.parent_user_id = ANY(%s::uuid[])
                    ORDER BY subscription.parent_user_id, subscription.created_at DESC
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


@router.get("/billing/plans", dependencies=[Depends(require_admin)])
def list_billing_plans() -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code, title, monthly_price_inr, allowed_child_count,
                       features_json AS features, active
                FROM billing_plans
                WHERE active = true
                ORDER BY allowed_child_count ASC
                """
            )
            plans = [dict(row) for row in cursor.fetchall()]
    return envelope(plans)


@router.post("/users/{parent_user_id}/subscription", dependencies=[Depends(require_admin)])
def change_parent_subscription(parent_user_id: str, payload: ChangeParentPlanRequest) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code, title, allowed_child_count
                FROM billing_plans
                WHERE code = %s
                  AND active = true
                """,
                (payload.plan_code,),
            )
            plan = cursor.fetchone()
            if plan is None:
                raise ApiError("NOT_FOUND", "Billing plan was not found.", 404)

            cursor.execute(
                """
                SELECT id::text
                FROM parent_users
                WHERE id = %s
                  AND status <> 'deleted'
                """,
                (parent_user_id,),
            )
            parent = cursor.fetchone()
            if parent is None:
                raise ApiError("NOT_FOUND", "Parent user was not found.", 404)

            cursor.execute(
                """
                INSERT INTO subscriptions (
                  parent_user_id,
                  plan_code,
                  billing_cycle,
                  status,
                  auto_renew,
                  payment_provider
                )
                VALUES (%s, %s, %s, 'active', true, 'admin')
                RETURNING parent_user_id::text, plan_code, billing_cycle, status,
                          auto_renew, starts_at::text, ends_at::text, updated_at::text
                """,
                (parent_user_id, payload.plan_code, payload.billing_cycle),
            )
            subscription = dict(cursor.fetchone())
            subscription["plan_title"] = plan["title"]
            subscription["allowed_child_count"] = plan["allowed_child_count"]
        connection.commit()

    return envelope(subscription, "Parent billing plan updated.")


@router.get("/guardrails/config", dependencies=[Depends(require_admin)])
def get_guardrails_config() -> dict[str, object]:
    return envelope(guardrails_public_config())


@router.patch("/guardrails/config", dependencies=[Depends(require_admin)])
def patch_guardrails_config(payload: GuardrailsConfigPatch) -> dict[str, object]:
    updates = payload.model_dump(exclude_unset=True)
    for key in (
        "text_normalization_url",
        "classified_prompt_url",
        "chat_url",
        "validator_url",
        "text_normalization_system_prompt",
        "default_system_prompt",
        "fallback_response",
    ):
        if key in updates and not str(updates[key]).strip():
            raise ApiError("INVALID_GUARDRAILS_CONFIG", f"{key} cannot be empty.", 422)
    return envelope(update_guardrails_runtime_config(updates), "Guardrails configuration updated.")


@router.get("/guardrails/reachability", dependencies=[Depends(require_admin)])
def test_guardrails_reachability() -> dict[str, object]:
    config = guardrails_public_config()
    timeout = min(float(config.get("timeout_seconds") or 30), 8)
    checks = [
        ("text_normalization", str(config["text_normalization_url"]), bool(config["text_normalization_enabled"])),
        ("classified_prompt", str(config["classified_prompt_url"]), bool(config["classified_prompt_enabled"])),
        ("chat", str(config["chat_url"]), True),
        ("validator", str(config["validator_url"]), bool(config["validator_enabled"])),
    ]
    results = [_probe_guardrails_endpoint(name, url, enabled, timeout) for name, url, enabled in checks]
    return envelope(
        {
            "ok": all(result["reachable"] or result["skipped"] for result in results),
            "results": results,
        }
    )


def _probe_guardrails_endpoint(name: str, url: str, enabled: bool, timeout: float) -> dict[str, object]:
    if not enabled:
        return {
            "name": name,
            "url": url,
            "enabled": enabled,
            "reachable": False,
            "skipped": True,
            "status_code": None,
            "error": None,
        }
    health_url = _health_url(url)
    try:
        response = httpx.get(health_url, timeout=timeout)
        return {
            "name": name,
            "url": url,
            "enabled": enabled,
            "reachable": response.status_code < 500,
            "skipped": False,
            "status_code": response.status_code,
            "health_url": health_url,
            "error": None if response.status_code < 500 else response.text[:240],
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "enabled": enabled,
            "reachable": False,
            "skipped": False,
            "status_code": None,
            "health_url": health_url,
            "error": str(exc),
        }


def _health_url(url: str) -> str:
    marker = "/api/v1/"
    if marker in url:
        return f"{url.split(marker, 1)[0].rstrip('/')}/health"
    return f"{url.rstrip('/')}/health"


@router.get("/guardrails/chat-calls", dependencies=[Depends(require_admin)])
def list_guardrails_chat_calls(limit: int = 25) -> dict[str, object]:
    bounded_limit = max(1, min(limit, 100))
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT message.id::text,
                       message.thread_id::text,
                       message.parent_user_id::text,
                       message.child_profile_id::text,
                       message.message_text,
                       message.rendered_text,
                       assistant.id::text AS assistant_message_id,
                       assistant.rendered_text AS assistant_rendered_text,
                       message.policy_bucket,
                       message.safety_category,
                       message.moderation_status,
                       message.explanation_text,
                       message.ai_model_used,
                       message.metadata_json,
                       message.created_at::text,
                       COALESCE(
                         jsonb_agg(
                           jsonb_build_object(
                             'stage_name', usage.stage_name,
                             'provider', usage.provider,
                             'model', usage.model,
                             'prompt_tokens', usage.prompt_tokens,
                             'completion_tokens', usage.completion_tokens,
                             'total_tokens', usage.total_tokens,
                             'created_at', usage.created_at::text
                           )
                           ORDER BY usage.created_at ASC
                         ) FILTER (WHERE usage.id IS NOT NULL),
                         '[]'::jsonb
                       ) AS token_usage
                FROM chat_messages message
                LEFT JOIN LATERAL (
                    SELECT id, rendered_text
                    FROM chat_messages candidate
                    WHERE candidate.thread_id = message.thread_id
                      AND candidate.parent_user_id = message.parent_user_id
                      AND candidate.sender_type = 'assistant'
                      AND candidate.created_at >= message.created_at
                    ORDER BY candidate.created_at ASC
                    LIMIT 1
                ) assistant ON true
                LEFT JOIN chat_guardrails_token_usage usage ON usage.message_id = message.id
                WHERE message.sender_type = 'child'
                GROUP BY message.id, assistant.id, assistant.rendered_text
                ORDER BY message.created_at DESC
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
    return envelope(rows)


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
