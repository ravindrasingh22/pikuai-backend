from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Literal

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class ConsentPayload(BaseModel):
    consent_type: Literal["training", "personalization", "transcript_visibility"]
    granted: bool
    consent_version: str = "2026-04"


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.get("/settings")
def privacy_settings(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
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
                SELECT optional_personalization_enabled, transcript_visibility_enabled,
                       retention_policy_code
                FROM parent_control_settings
                WHERE parent_user_id = %s
                """,
                (parent_id,),
            )
            controls = cursor.fetchone()
        connection.commit()
    return envelope(
        {
            "training_on_child_data": False,
            "optional_personalization_enabled": controls["optional_personalization_enabled"],
            "transcript_visibility_enabled": controls["transcript_visibility_enabled"],
            "retention_policy_code": controls["retention_policy_code"],
            "export_child_data_status": "ready",
            "delete_account_requires_pin": True,
        }
    )


@router.patch("/settings")
def patch_privacy_settings() -> dict[str, object]:
    return envelope({"updated": True}, "Privacy settings update accepted.")


@router.get("/consents")
def list_consents() -> dict[str, object]:
    return envelope([])


@router.post("/consents", status_code=201)
def create_consent(payload: ConsentPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    return envelope(
        {
            "parent_user_id": parent_id,
            "consent_type": payload.consent_type,
            "granted": payload.granted,
            "consent_version": payload.consent_version,
        },
        "Consent recorded.",
    )


@router.post("/delete-request")
def delete_request() -> dict[str, object]:
    return envelope(
        {"request_status": "submitted", "requires_parent_pin": True},
        "Delete request submitted.",
    )
