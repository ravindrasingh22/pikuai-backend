from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class ParentProfilePatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2)
    country: str | None = Field(default=None, min_length=2)
    preferred_language: str | None = Field(default=None, min_length=2)


class PinPayload(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.get("/profile")
def get_profile(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, full_name, email, status, country, preferred_language,
                       two_factor_enabled, pin_enabled, gender, phone_number, city,
                       timezone, onboarding_status, created_at::text, updated_at::text
                FROM parent_users
                WHERE id = %s
                """,
                (parent_id,),
            )
            parent = cursor.fetchone()
    if parent is None:
        raise ApiError("NOT_FOUND", "Parent profile was not found.", 404)
    return envelope(dict(parent))


@router.patch("/profile")
def patch_profile(payload: ParentProfilePatch, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    patch = payload.model_dump(exclude_none=True)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT full_name, country, preferred_language
                FROM parent_users
                WHERE id = %s
                """,
                (parent_id,),
            )
            current = cursor.fetchone()
            if current is None:
                raise ApiError("NOT_FOUND", "Parent profile was not found.", 404)

            updated_values = {**dict(current), **patch}
            cursor.execute(
                """
                UPDATE parent_users
                SET full_name = %s,
                    country = %s,
                    preferred_language = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text, full_name, email, status, country, preferred_language,
                          two_factor_enabled, pin_enabled, gender, phone_number, city,
                          timezone, onboarding_status, created_at::text, updated_at::text
                """,
                (
                    updated_values["full_name"],
                    updated_values["country"],
                    updated_values["preferred_language"],
                    parent_id,
                ),
            )
            parent = cursor.fetchone()
        connection.commit()

    return envelope(dict(parent), "Parent profile updated.")


@router.get("/security-settings")
def security_settings(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT two_factor_enabled, pin_enabled
                FROM parent_users
                WHERE id = %s
                """,
                (parent_id,),
            )
            parent = cursor.fetchone()
    if parent is None:
        raise ApiError("NOT_FOUND", "Parent profile was not found.", 404)
    return envelope(
        {
            "two_factor_enabled": parent["two_factor_enabled"],
            "pin_enabled": parent["pin_enabled"],
            "protected_areas": ["transcripts", "privacy", "payment", "controls", "alerts"],
        }
    )


@router.post("/pin/setup")
def setup_pin(payload: PinPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_users
                SET pin_hash = crypt(%s, gen_salt('bf')),
                    pin_enabled = true,
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text, pin_enabled
                """,
                (payload.pin, parent_id),
            )
            parent = cursor.fetchone()
        connection.commit()
    if parent is None:
        raise ApiError("NOT_FOUND", "Parent profile was not found.", 404)
    return envelope({"pin_enabled": parent["pin_enabled"]}, "Parent PIN configured.")


@router.post("/pin/verify")
def verify_pin(payload: PinPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pin_enabled
                FROM parent_users
                WHERE id = %s
                  AND pin_enabled = true
                  AND pin_hash = crypt(%s, pin_hash)
                """,
                (parent_id, payload.pin),
            )
            parent = cursor.fetchone()
    if parent is None:
        raise ApiError("AUTH_REQUIRED", "Invalid parent PIN.", 401)
    return envelope({"verified": True})
