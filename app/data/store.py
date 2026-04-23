from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


DEFAULT_PARENT_ID = "parent_demo"
DEFAULT_ADMIN_ID = "admin_owner"

timestamp = now_iso()

parents: dict[str, dict[str, Any]] = {
    DEFAULT_PARENT_ID: {
        "id": DEFAULT_PARENT_ID,
        "full_name": "Ravin Singh",
        "email": "ravin@example.com",
        "status": "active",
        "country": "IN",
        "preferred_language": "en",
        "two_factor_enabled": True,
        "pin_enabled": True,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
}

admin_users: dict[str, dict[str, Any]] = {
    DEFAULT_ADMIN_ID: {
        "id": DEFAULT_ADMIN_ID,
        "full_name": "PikuAI Owner",
        "email": "admin@pikuai.local",
        "role": "owner",
        "status": "active",
        "password": "admin12345",
        "created_at": timestamp,
        "updated_at": timestamp,
    },
    "admin_safety": {
        "id": "admin_safety",
        "full_name": "Safety Reviewer",
        "email": "safety@pikuai.local",
        "role": "safety_reviewer",
        "status": "active",
        "password": "safety12345",
        "created_at": timestamp,
        "updated_at": timestamp,
    },
    "admin_support": {
        "id": "admin_support",
        "full_name": "Support Admin",
        "email": "support@pikuai.local",
        "role": "support",
        "status": "active",
        "password": "support12345",
        "created_at": timestamp,
        "updated_at": timestamp,
    },
}

children: dict[str, dict[str, Any]] = {}

controls: dict[str, dict[str, Any]] = {
    DEFAULT_PARENT_ID: {
        "id": "controls_demo",
        "parent_user_id": DEFAULT_PARENT_ID,
        "transcript_visibility_enabled": True,
        "content_strictness_level": "balanced",
        "session_limit_enabled": True,
        "default_session_limit_minutes": 30,
        "sensitive_topic_alerts_enabled": True,
        "weekly_summary_enabled": True,
        "optional_personalization_enabled": False,
        "retention_policy_code": "90_days",
        "updated_at": timestamp,
    }
}

subscriptions: dict[str, dict[str, Any]] = {
    DEFAULT_PARENT_ID: {
        "id": "sub_demo",
        "parent_user_id": DEFAULT_PARENT_ID,
        "plan_code": "family_plus",
        "billing_cycle": "monthly",
        "status": "active",
        "starts_at": timestamp,
        "ends_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "auto_renew": True,
    }
}

threads: dict[str, dict[str, Any]] = {}
messages: dict[str, dict[str, Any]] = {}
alerts: dict[str, dict[str, Any]] = {}
policy_logs: dict[str, dict[str, Any]] = {}
consents: dict[str, dict[str, Any]] = {
    "consent_training_demo": {
        "id": "consent_training_demo",
        "parent_user_id": DEFAULT_PARENT_ID,
        "consent_type": "training",
        "granted": False,
        "consent_version": "2026-04",
        "revoked_at_optional": timestamp,
    }
}


def current_parent_id() -> str:
    return DEFAULT_PARENT_ID


def public_admin_user(admin: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in admin.items() if key != "password"}
