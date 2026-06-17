from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from typing import Literal

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()

AgeBand = Literal["3-5", "6-8", "9-11", "11-13", "14-17"]
ChildGender = Literal["girl", "boy", "not_disclosed"]


class ChildPayload(BaseModel):
    display_name: str = Field(min_length=1)
    age_band: AgeBand
    daily_time_limit_minutes: int | None = Field(default=None, ge=5, le=240)
    avatar_key: str | None = Field(default=None, min_length=1, max_length=24)
    gender: ChildGender = "not_disclosed"
    voice_enabled: bool | None = None


class ChildPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    age_band: AgeBand | None = None
    daily_time_limit_minutes: int | None = Field(default=None, ge=5, le=240)
    topic_restrictions_json: list[str] | None = None
    voice_enabled: bool | None = None
    avatar_key: str | None = Field(default=None, min_length=1, max_length=24)
    gender: ChildGender | None = None


class ChildPinPayload(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")


class VoiceUsagePayload(BaseModel):
    elapsed_seconds: int = Field(ge=0, le=3600)


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


def _subscription_plan(parent_id: str) -> str:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT plan_code
                FROM subscriptions
                WHERE parent_user_id = %s
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (parent_id,),
            )
            row = cursor.fetchone()
    return str(row["plan_code"]) if row else "starter"


def _plan_child_limit(plan_code: str) -> int:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT allowed_child_count
                FROM billing_plans
                WHERE code = %s
                  AND active = true
                """,
                (plan_code,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute("SELECT allowed_child_count FROM billing_plans WHERE code = 'starter'")
                row = cursor.fetchone()
    return int(row["allowed_child_count"]) if row else 1


def _daily_limit_seconds(child: object) -> int:
    daily_minutes = int(child["daily_time_limit_minutes"] or 30)
    return max(0, daily_minutes * 60)


def _voice_usage_response(child: object, usage: object) -> dict[str, object]:
    daily_limit_seconds = _daily_limit_seconds(child)
    used_seconds = min(int(usage["used_seconds"] or 0), daily_limit_seconds)
    return {
        "child_profile_id": child["id"],
        "usage_date": usage["usage_date"],
        "daily_limit_seconds": daily_limit_seconds,
        "used_seconds": used_seconds,
        "remaining_seconds": max(0, daily_limit_seconds - used_seconds),
    }


@router.get("")
@router.get("/")
def list_children(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, parent_user_id::text, display_name, age_band,
                       auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                       conversation_visibility_rule, daily_time_limit_minutes,
                       topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                       created_at::text, updated_at::text
                FROM child_profiles
                WHERE parent_user_id = %s
                  AND active_status = 'active'
                ORDER BY created_at ASC
                """,
                (parent_id,),
            )
            children = [dict(row) for row in cursor.fetchall()]
    return envelope(children)


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_child(payload: ChildPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    plan_code = _subscription_plan(parent_id)
    limit = _plan_child_limit(plan_code)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS child_count FROM child_profiles WHERE parent_user_id = %s AND active_status = 'active'",
                (parent_id,),
            )
            current_count = int(cursor.fetchone()["child_count"])
            if current_count >= limit:
                raise ApiError("ENTITLEMENT_EXCEEDED", "Current plan child profile limit reached.", 403)

            cursor.execute(
                """
                INSERT INTO child_profiles (
                  parent_user_id,
                  display_name,
                  age_band,
                  daily_time_limit_minutes,
                  voice_enabled,
                  avatar_key,
                  gender
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id::text, parent_user_id::text, display_name, age_band,
                          auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                          conversation_visibility_rule, daily_time_limit_minutes,
                          topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                          created_at::text, updated_at::text
                """,
                (
                    parent_id,
                    payload.display_name,
                    payload.age_band,
                    payload.daily_time_limit_minutes or 30,
                    True if payload.voice_enabled is None else payload.voice_enabled,
                    payload.avatar_key or "kid",
                    payload.gender,
                ),
            )
            child = cursor.fetchone()
        connection.commit()

    return envelope(dict(child), "Child profile created.")


@router.get("/{child_id}")
def get_child(child_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, parent_user_id::text, display_name, age_band,
                       auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                       conversation_visibility_rule, daily_time_limit_minutes,
                       topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                       created_at::text, updated_at::text
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (child_id, parent_id),
            )
            child = cursor.fetchone()
    if child is None:
        raise ApiError("NOT_FOUND", "Child profile was not found.", 404)
    return envelope(dict(child))


@router.get("/{child_id}/voice-usage")
def get_child_voice_usage(child_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, daily_time_limit_minutes
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                  AND active_status = 'active'
                """,
                (child_id, parent_id),
            )
            child = cursor.fetchone()
            if child is None:
                raise ApiError("NOT_FOUND", "Child profile was not found.", 404)

            cursor.execute(
                """
                SELECT CURRENT_DATE::text AS usage_date,
                       COALESCE((
                         SELECT used_seconds
                         FROM child_voice_usage_daily
                         WHERE child_profile_id = %s
                           AND usage_date = CURRENT_DATE
                       ), 0) AS used_seconds
                """,
                (child_id,),
            )
            usage = cursor.fetchone()

    return envelope(_voice_usage_response(child, usage))


@router.post("/{child_id}/voice-usage")
def add_child_voice_usage(
    child_id: str,
    payload: VoiceUsagePayload,
    claims: TokenClaims = Depends(require_parent_or_admin),
) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, daily_time_limit_minutes
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                  AND active_status = 'active'
                """,
                (child_id, parent_id),
            )
            child = cursor.fetchone()
            if child is None:
                raise ApiError("NOT_FOUND", "Child profile was not found.", 404)

            daily_limit_seconds = _daily_limit_seconds(child)
            cursor.execute(
                """
                INSERT INTO child_voice_usage_daily (child_profile_id, usage_date, used_seconds)
                VALUES (%s, CURRENT_DATE, LEAST(%s, %s))
                ON CONFLICT (child_profile_id, usage_date)
                DO UPDATE SET
                  used_seconds = LEAST(child_voice_usage_daily.used_seconds + EXCLUDED.used_seconds, %s),
                  updated_at = now()
                RETURNING CURRENT_DATE::text AS usage_date, used_seconds
                """,
                (child_id, payload.elapsed_seconds, daily_limit_seconds, daily_limit_seconds),
            )
            usage = cursor.fetchone()
        connection.commit()

    return envelope(_voice_usage_response(child, usage), "Voice usage updated.")


@router.patch("/{child_id}")
def patch_child(child_id: str, payload: ChildPatch, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    patch = payload.model_dump(exclude_none=True)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, parent_user_id::text, display_name, age_band,
                       auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                       conversation_visibility_rule, daily_time_limit_minutes,
                       topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                       created_at::text, updated_at::text
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (child_id, parent_id),
            )
            current = cursor.fetchone()
            if current is None:
                raise ApiError("NOT_FOUND", "Child profile was not found.", 404)

            updated_values = {**dict(current), **patch}
            cursor.execute(
                """
                UPDATE child_profiles
                SET display_name = %s,
                    age_band = %s,
                    daily_time_limit_minutes = %s,
                    topic_restrictions_json = %s::jsonb,
                    voice_enabled = %s,
                    avatar_key = %s,
                    gender = %s,
                    updated_at = now()
                WHERE id = %s
                  AND parent_user_id = %s
                RETURNING id::text, parent_user_id::text, display_name, age_band,
                          auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                          conversation_visibility_rule, daily_time_limit_minutes,
                          topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                          created_at::text, updated_at::text
                """,
                (
                    updated_values["display_name"],
                    updated_values["age_band"],
                    updated_values["daily_time_limit_minutes"],
                    Jsonb(updated_values["topic_restrictions_json"]),
                    updated_values["voice_enabled"],
                    updated_values["avatar_key"],
                    updated_values["gender"],
                    child_id,
                    parent_id,
                ),
            )
            updated = cursor.fetchone()
        connection.commit()

    return envelope(dict(updated), "Child profile updated.")


@router.post("/{child_id}/archive")
def archive_child(child_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE child_profiles
                SET active_status = 'archived',
                    updated_at = now()
                WHERE id = %s
                  AND parent_user_id = %s
                RETURNING id::text, parent_user_id::text, display_name, age_band,
                          auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                          conversation_visibility_rule, daily_time_limit_minutes,
                          topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                          created_at::text, updated_at::text
                """,
                (child_id, parent_id),
            )
            child = cursor.fetchone()
        connection.commit()

    if child is None:
        raise ApiError("NOT_FOUND", "Child profile was not found.", 404)
    return envelope(dict(child), "Child profile archived.")


@router.delete("/{child_id}")
def delete_child(
    child_id: str,
    delete_chats: bool = False,
    claims: TokenClaims = Depends(require_parent_or_admin),
) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if delete_chats:
                cursor.execute(
                    """
                    DELETE FROM chat_threads
                    WHERE parent_user_id = %s
                      AND child_profile_id = %s
                    """,
                    (parent_id, child_id),
                )
            cursor.execute(
                """
                UPDATE child_profiles
                SET active_status = 'deleted',
                    updated_at = now()
                WHERE id = %s
                  AND parent_user_id = %s
                RETURNING id::text, parent_user_id::text, display_name, age_band,
                          auto_upgrade_enabled, auto_upgrade_requires_parent_review,
                          conversation_visibility_rule, daily_time_limit_minutes,
                          topic_restrictions_json, voice_enabled, avatar_key, gender, child_pin_enabled, active_status,
                          created_at::text, updated_at::text
                """,
                (child_id, parent_id),
            )
            child = cursor.fetchone()
        connection.commit()

    if child is None:
        raise ApiError("NOT_FOUND", "Child profile was not found.", 404)
    return envelope(
        {"child": dict(child), "chats_deleted": delete_chats},
        "Child profile deleted." if delete_chats else "Child profile removed.",
    )


@router.post("/{child_id}/pin/setup")
def setup_child_pin(child_id: str, payload: ChildPinPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE child_profiles
                SET child_pin_hash = crypt(%s, gen_salt('bf')),
                    child_pin_enabled = true,
                    updated_at = now()
                WHERE id = %s
                  AND parent_user_id = %s
                RETURNING id::text, child_pin_enabled
                """,
                (payload.pin, child_id, parent_id),
            )
            child = cursor.fetchone()
        connection.commit()
    if child is None:
        raise ApiError("NOT_FOUND", "Child profile was not found.", 404)
    return envelope({"child_profile_id": child["id"], "child_pin_enabled": child["child_pin_enabled"]}, "Child PIN configured.")


@router.post("/{child_id}/pin/verify")
def verify_child_pin(child_id: str, payload: ChildPinPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                  AND child_pin_enabled = true
                  AND child_pin_hash = crypt(%s, child_pin_hash)
                """,
                (child_id, parent_id, payload.pin),
            )
            child = cursor.fetchone()
    if child is None:
        raise ApiError("AUTH_REQUIRED", "Invalid child PIN.", 401)
    return envelope({"verified": True, "child_profile_id": child["id"]})


@router.post("/{child_id}/age-template/recalculate")
def recalculate_age_template(child_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, age_band, auto_upgrade_requires_parent_review
                FROM child_profiles
                WHERE id = %s
                  AND parent_user_id = %s
                """,
                (child_id, parent_id),
            )
            child = cursor.fetchone()
    if child is None:
        raise ApiError("NOT_FOUND", "Child profile was not found.", 404)
    next_band = {"3-5": "6-8", "6-8": "9-11", "9-11": "11-13", "11-13": "14-17", "14-17": "14-17"}[str(child["age_band"])]
    return envelope(
        {
            "child_profile_id": child_id,
            "current_age_band": child["age_band"],
            "suggested_age_band": next_band,
            "parent_review_required": child["auto_upgrade_requires_parent_review"],
        }
    )
