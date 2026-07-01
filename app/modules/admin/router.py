from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.security import create_token, require_admin
from app.db.session import get_connection
from app.modules.guardrails.client import get_guardrails_runtime_config, guardrails_public_config, update_guardrails_runtime_config
from app.modules.mail.service import (
    get_email_template,
    list_email_templates,
    send_raw_email,
    send_template_email,
    smtp_config_row,
    smtp_public_config,
    update_email_template,
)
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


class AdminForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address.")
        return normalized


class AdminResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=8, max_length=128)


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
    context_to_text_normalization_enabled: bool | None = None
    context_to_classified_prompt_enabled: bool | None = None
    context_to_chat_enabled: bool | None = None
    context_to_validator_enabled: bool | None = None
    classified_prompt_enabled: bool | None = None
    classified_prompt_url: str | None = None
    chat_url: str | None = None
    api_key: str | None = None
    default_system_prompt: str | None = None
    validator_enabled: bool | None = None
    validator_url: str | None = None
    validator_threshold: float | None = Field(default=None, ge=0, le=1)
    fallback_response: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)


class SmtpConfigPatch(BaseModel):
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    secure: bool | None = None
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)
    mail_from: str | None = Field(default=None, min_length=3, max_length=255)


class SmtpTestRequest(BaseModel):
    to_email: str = Field(min_length=3, max_length=255)

    @field_validator("to_email")
    @classmethod
    def validate_to_email(cls, value: str) -> str:
        normalized = value.strip()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid test email address.")
        return normalized


class EmailTemplatePatch(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    preview_text: str | None = Field(default=None, max_length=255)
    cta_label: str | None = Field(default=None, max_length=80)
    body_text: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None


class EmailTemplateTestRequest(BaseModel):
    to_email: str = Field(min_length=3, max_length=255)

    @field_validator("to_email")
    @classmethod
    def validate_to_email(cls, value: str) -> str:
        normalized = value.strip()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid test email address.")
        return normalized


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


@router.post("/auth/forgot-password")
def admin_forgot_password(payload: AdminForgotPasswordRequest) -> dict[str, object]:
    reset_token: str | None = None
    email = payload.email

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text
                FROM admin_users
                WHERE email = %s
                  AND status = 'active'
                """,
                (email,),
            )
            admin = cursor.fetchone()
            if admin is not None:
                reset_token = secrets.token_urlsafe(32)
                cursor.execute(
                    """
                    UPDATE admin_password_reset_tokens
                    SET used_at = now()
                    WHERE admin_user_id = %s
                      AND used_at IS NULL
                    """,
                    (admin["id"],),
                )
                cursor.execute(
                    """
                    INSERT INTO admin_password_reset_tokens (admin_user_id, token_hash, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        admin["id"],
                        _hash_reset_token(reset_token),
                        datetime.now(UTC) + timedelta(minutes=30),
                    ),
                )

    if reset_token is not None:
        try:
            send_template_email(
                "auth_password_reset_parent",
                email,
                {
                    "parent_first_name": "Admin",
                    "parent_email": email,
                    "reset_link": reset_token,
                    "expiry_minutes": 30,
                },
                raise_on_error=True,
            )
        except Exception as exc:
            raise ApiError("PASSWORD_RESET_EMAIL_FAILED", f"Unable to send reset email: {exc}", 502) from exc

    data: dict[str, object] = {"reset_token_available": settings.node_env == "development" and reset_token is not None}
    if settings.node_env == "development" and reset_token is not None:
        data["reset_token"] = reset_token

    return envelope(
        data,
        "If an active admin account exists for that email, password reset instructions have been prepared.",
    )


@router.post("/auth/reset-password")
def admin_reset_password(payload: AdminResetPasswordRequest) -> dict[str, object]:
    token_hash = _hash_reset_token(payload.token)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT token.id::text, token.admin_user_id::text
                FROM admin_password_reset_tokens token
                JOIN admin_users admin ON admin.id = token.admin_user_id
                WHERE token.token_hash = %s
                  AND token.used_at IS NULL
                  AND token.expires_at > now()
                  AND admin.status = 'active'
                """,
                (token_hash,),
            )
            reset = cursor.fetchone()
            if reset is None:
                raise ApiError("RESET_TOKEN_INVALID", "Reset link is invalid or expired.", 400)

            cursor.execute(
                """
                UPDATE admin_users
                SET password_hash = crypt(%s, gen_salt('bf')),
                    updated_at = now()
                WHERE id = %s
                """,
                (payload.password, reset["admin_user_id"]),
            )
            cursor.execute(
                """
                UPDATE admin_password_reset_tokens
                SET used_at = now()
                WHERE admin_user_id = %s
                  AND used_at IS NULL
                """,
                (reset["admin_user_id"],),
            )

    return envelope({"password_reset": True}, "Admin password reset.")


@router.get("/mail/config", dependencies=[Depends(require_admin)])
def get_smtp_config() -> dict[str, object]:
    return envelope(smtp_public_config(), "SMTP configuration loaded.")


@router.patch("/mail/config", dependencies=[Depends(require_admin)])
def update_smtp_config(payload: SmtpConfigPatch) -> dict[str, object]:
    current = smtp_config_row(include_secret=True)
    password = current["password_optional"] if payload.password is None else payload.password

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE smtp_runtime_config
                SET host = %s,
                    port = %s,
                    secure = %s,
                    username = %s,
                    password_optional = %s,
                    mail_from = %s,
                    updated_at = now()
                WHERE id = true
                """,
                (
                    payload.host if payload.host is not None else current["host"],
                    payload.port if payload.port is not None else current["port"],
                    payload.secure if payload.secure is not None else current["secure"],
                    payload.username if payload.username is not None else current["username"],
                    password,
                    payload.mail_from if payload.mail_from is not None else current["mail_from"],
                ),
            )

    return envelope(smtp_public_config(), "SMTP configuration saved.")


@router.post("/mail/test", dependencies=[Depends(require_admin)])
def send_smtp_test(payload: SmtpTestRequest) -> dict[str, object]:
    try:
        send_raw_email(
            to_email=payload.to_email,
            subject="Pratvim SMTP test",
            body=(
                "This is a Pratvim admin SMTP test email. "
                "If you received this, the configured SMTP connection is working."
            ),
        )
    except Exception as exc:
        raise ApiError("SMTP_TEST_FAILED", f"SMTP test failed: {exc}", 400) from exc

    return envelope({"sent": True}, "SMTP test email sent.")


@router.get("/mail/templates", dependencies=[Depends(require_admin)])
def admin_list_email_templates() -> dict[str, object]:
    return envelope({"templates": list_email_templates()}, "Email templates loaded.")


@router.get("/mail/templates/{template_key}", dependencies=[Depends(require_admin)])
def admin_get_email_template(template_key: str) -> dict[str, object]:
    return envelope(get_email_template(template_key), "Email template loaded.")


@router.patch("/mail/templates/{template_key}", dependencies=[Depends(require_admin)])
def admin_update_email_template(template_key: str, payload: EmailTemplatePatch) -> dict[str, object]:
    return envelope(
        update_email_template(template_key, payload.model_dump(exclude_unset=True)),
        "Email template saved.",
    )


@router.post("/mail/templates/{template_key}/test", dependencies=[Depends(require_admin)])
def admin_test_email_template(template_key: str, payload: EmailTemplateTestRequest) -> dict[str, object]:
    try:
        sent = send_template_email(
            template_key,
            payload.to_email,
            {
                "parent_first_name": "Ravin",
                "parent_email": payload.to_email,
                "confirmation_code": "482913",
                "otp_code": "482913",
                "expiry_minutes": 10,
                "reset_link": "https://pratvim.com/reset/demo",
                "child_profile_name": "Aarav",
                "age_band": "6-8",
                "event_time": "2026-06-29 12:00",
                "plan_code": "family_plus",
                "amount": "INR 499",
                "request_id": "PRTV-DEMO-001",
                "dashboard_link": "https://pratvim.com",
                "cta_link": "https://pratvim.com",
            },
            raise_on_error=True,
        )
    except Exception as exc:
        raise ApiError("EMAIL_TEMPLATE_TEST_FAILED", f"Email template test failed: {exc}", 400) from exc
    return envelope({"sent": sent}, "Email template test sent.")


@router.get("/mail/public-ip", dependencies=[Depends(require_admin)])
def get_public_ip() -> dict[str, object]:
    try:
        response = httpx.get("https://api.ipify.org?format=json", timeout=5)
        response.raise_for_status()
        payload = response.json()
        ip = payload.get("ip")
        if not isinstance(ip, str) or not ip:
            raise ValueError("Missing IP in response.")
        return envelope({"ip": ip, "source": "api.ipify.org"}, "Public IP loaded.")
    except Exception as exc:
        raise ApiError("PUBLIC_IP_UNAVAILABLE", f"Unable to detect public IP: {exc}", 502) from exc


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
                SELECT id::text, full_name, email
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

    send_template_email(
        "billing_family_plan_active_parent",
        parent["email"],
        {
            "parent_first_name": str(parent["full_name"]).split(" ", 1)[0],
            "parent_email": parent["email"],
            "plan_code": subscription["plan_code"],
            "cta_link": "pratvim://parent/billing",
        },
        to_name=parent["full_name"],
    )
    return envelope(subscription, "Parent billing plan updated.")


@router.get("/guardrails/config", dependencies=[Depends(require_admin)])
def get_guardrails_config() -> dict[str, object]:
    return envelope(guardrails_public_config())


@router.patch("/guardrails/config", dependencies=[Depends(require_admin)])
def patch_guardrails_config(payload: GuardrailsConfigPatch) -> dict[str, object]:
    updates = payload.model_dump(exclude_unset=True)
    if "api_key" in updates:
        api_key = str(updates.pop("api_key") or "").strip()
        if api_key:
            updates["api_key_optional"] = api_key
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
    config = get_guardrails_runtime_config()
    timeout = min(float(config.get("timeout_seconds") or 30), 8)
    headers = _guardrails_probe_headers(config)
    checks = [
        ("text_normalization", str(config["text_normalization_url"]), bool(config["text_normalization_enabled"])),
        ("classified_prompt", str(config["classified_prompt_url"]), bool(config["classified_prompt_enabled"])),
        ("chat", str(config["chat_url"]), True),
        ("validator", str(config["validator_url"]), bool(config["validator_enabled"])),
    ]
    results = [_probe_guardrails_endpoint(name, url, enabled, timeout, headers) for name, url, enabled in checks]
    return envelope(
        {
            "ok": all(result["reachable"] or result["skipped"] for result in results),
            "results": results,
        }
    )


def _probe_guardrails_endpoint(name: str, url: str, enabled: bool, timeout: float, headers: dict[str, str] | None = None) -> dict[str, object]:
    if not enabled:
        return {
            "name": name,
            "url": url,
            "enabled": enabled,
            "reachable": False,
            "skipped": True,
            "status_code": None,
            "probe_url": url,
            "error": None,
        }
    payload = _guardrails_probe_payload(name)
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        reachable = 200 <= response.status_code < 300
        return {
            "name": name,
            "url": url,
            "enabled": enabled,
            "reachable": reachable,
            "skipped": False,
            "status_code": response.status_code,
            "probe_url": url,
            "error": None if reachable else response.text[:500] or f"Endpoint probe returned HTTP {response.status_code}.",
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "enabled": enabled,
            "reachable": False,
            "skipped": False,
            "status_code": None,
            "probe_url": url,
            "error": str(exc),
        }


def _guardrails_probe_payload(name: str) -> dict[str, object]:
    child_profile = {
        "age": 9,
        "age_group": "9-11",
        "language": "en",
    }
    base = {
        "child_profile": child_profile,
        "session_id": "admin-guardrails-probe",
        "message": "Why is the sky blue?",
        "recent_context": [],
    }
    if name == "chat":
        return {
            "child_profile": child_profile,
            "session_id": "admin-guardrails-probe",
            "messages": [
                {"role": "system", "content": "Answer briefly and safely for a child."},
                {"role": "user", "content": "Why is the sky blue?"},
            ],
            "validate_response": False,
            "temperature": 0,
            "max_tokens": 80,
        }
    if name == "validator":
        return {
            "child_profile": child_profile,
            "session_id": "admin-guardrails-probe",
            "message": {"role": "assistant", "content": "The sky looks blue because air scatters blue light from the sun."},
        }
    return base


def _guardrails_probe_headers(config: dict[str, object]) -> dict[str, str] | None:
    api_key = str(config.get("api_key_optional") or "").strip()
    if not api_key:
        return None
    return {"x-api-key": api_key}


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

    send_template_email(
        "security_parent_pin_changed",
        parent["email"],
        {
            "parent_first_name": str(parent["full_name"]).split(" ", 1)[0],
            "parent_email": parent["email"],
            "cta_link": "pratvim://parent/security",
        },
        to_name=parent["full_name"],
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

    send_template_email(
        "auth_password_changed_parent",
        parent["email"],
        {
            "parent_first_name": str(parent["full_name"]).split(" ", 1)[0],
            "parent_email": parent["email"],
            "manage_account_link": "pratvim://parent/security",
            "cta_link": "pratvim://parent/security",
        },
        to_name=parent["full_name"],
    )

    return envelope(dict(parent), "Parent password changed.")


@router.delete("/users/{parent_user_id}", dependencies=[Depends(require_admin)])
def delete_parent_account(parent_user_id: str) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, full_name, email, status
                FROM parent_users
                WHERE id = %s
                """,
                (parent_user_id,),
            )
            parent = cursor.fetchone()

            if parent is None:
                raise ApiError("NOT_FOUND", "Parent user was not found.", 404)

            cursor.execute("SELECT COUNT(*) AS count FROM child_profiles WHERE parent_user_id = %s", (parent_user_id,))
            child_count = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM admin_notifications WHERE parent_user_id = %s", (parent_user_id,))
            notification_count = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM subscriptions WHERE parent_user_id = %s", (parent_user_id,))
            subscription_count = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM chat_threads WHERE parent_user_id = %s", (parent_user_id,))
            thread_count = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM chat_messages WHERE parent_user_id = %s", (parent_user_id,))
            message_count = int(cursor.fetchone()["count"])
            cursor.execute(
                "SELECT COUNT(*) AS count FROM chat_guardrails_token_usage WHERE parent_user_id = %s",
                (parent_user_id,),
            )
            token_usage_count = int(cursor.fetchone()["count"])

            cursor.execute(
                """
                DELETE FROM parent_users
                WHERE id = %s
                RETURNING id::text
                """,
                (parent_user_id,),
            )
            deleted = cursor.fetchone()
            if deleted is None:
                raise ApiError("NOT_FOUND", "Parent user was not found.", 404)

    return envelope(
        {
            "parent_user_id": parent["id"],
            "email": parent["email"],
            "deleted": True,
            "deleted_counts": {
                "children": child_count,
                "notifications": notification_count,
                "subscriptions": subscription_count,
                "chat_threads": thread_count,
                "chat_messages": message_count,
                "guardrails_token_usage": token_usage_count,
            },
        },
        "Parent account and related profile data deleted.",
    )


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
