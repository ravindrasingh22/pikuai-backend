from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class ControlsPatch(BaseModel):
    transcript_visibility_enabled: bool | None = None
    content_strictness_level: Literal["low", "balanced", "strict"] | None = None
    session_limit_enabled: bool | None = None
    default_session_limit_minutes: int | None = Field(default=None, ge=5, le=240)
    sensitive_topic_alerts_enabled: bool | None = None
    weekly_summary_enabled: bool | None = None
    optional_personalization_enabled: bool | None = None
    retention_policy_code: Literal["90_days", "1_year", "delete_on_request"] | None = None


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


def _ensure_controls(parent_id: str) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO parent_control_settings (parent_user_id)
                VALUES (%s)
                ON CONFLICT (parent_user_id) DO NOTHING
                """,
                (parent_id,),
            )
            cursor.execute(
                """
                SELECT parent_user_id::text, transcript_visibility_enabled,
                       content_strictness_level, session_limit_enabled,
                       default_session_limit_minutes, sensitive_topic_alerts_enabled,
                       weekly_summary_enabled, optional_personalization_enabled,
                       retention_policy_code, updated_at::text
                FROM parent_control_settings
                WHERE parent_user_id = %s
                """,
                (parent_id,),
            )
            controls = cursor.fetchone()
        connection.commit()
    return dict(controls)


@router.get("")
@router.get("/")
def get_controls(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    return envelope(_ensure_controls(_parent_id(claims)))


@router.patch("")
@router.patch("/")
def patch_controls(payload: ControlsPatch, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    current = _ensure_controls(parent_id)
    patch = payload.model_dump(exclude_none=True)
    updated_values = {**current, **patch}

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_control_settings
                SET transcript_visibility_enabled = %s,
                    content_strictness_level = %s,
                    session_limit_enabled = %s,
                    default_session_limit_minutes = %s,
                    sensitive_topic_alerts_enabled = %s,
                    weekly_summary_enabled = %s,
                    optional_personalization_enabled = %s,
                    retention_policy_code = %s,
                    updated_at = now()
                WHERE parent_user_id = %s
                RETURNING parent_user_id::text, transcript_visibility_enabled,
                          content_strictness_level, session_limit_enabled,
                          default_session_limit_minutes, sensitive_topic_alerts_enabled,
                          weekly_summary_enabled, optional_personalization_enabled,
                          retention_policy_code, updated_at::text
                """,
                (
                    updated_values["transcript_visibility_enabled"],
                    updated_values["content_strictness_level"],
                    updated_values["session_limit_enabled"],
                    updated_values["default_session_limit_minutes"],
                    updated_values["sensitive_topic_alerts_enabled"],
                    updated_values["weekly_summary_enabled"],
                    updated_values["optional_personalization_enabled"],
                    updated_values["retention_policy_code"],
                    parent_id,
                ),
            )
            controls = cursor.fetchone()
        connection.commit()
    return envelope(dict(controls), "Controls updated.")
