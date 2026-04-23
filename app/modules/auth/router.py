from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

from app.core.security import create_token, decode_token
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class RegisterParentRequest(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=8)
    country: str = Field(min_length=2)
    preferred_language: str = Field(min_length=2)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


@router.post("/register-parent", status_code=201)
def register_parent(payload: RegisterParentRequest) -> dict[str, object]:
    email = payload.email.lower()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM parent_users WHERE email = %s", (email,))
            if cursor.fetchone() is not None:
                raise ApiError("VALIDATION_ERROR", "Email is already registered.", 409)
            cursor.execute(
                """
                INSERT INTO parent_users (
                  full_name,
                  email,
                  password_hash,
                  status,
                  country,
                  preferred_language,
                  two_factor_enabled,
                  pin_enabled
                )
                VALUES (%s, %s, crypt(%s, gen_salt('bf')), 'active', %s, %s, false, false)
                RETURNING id::text, status
                """,
                (
                    payload.full_name,
                    email,
                    payload.password,
                    payload.country,
                    payload.preferred_language,
                ),
            )
            parent = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO subscriptions (
                  parent_user_id,
                  plan_code,
                  billing_cycle,
                  status,
                  starts_at,
                  ends_at,
                  auto_renew,
                  payment_provider
                )
                VALUES (%s, 'starter', 'trial', 'active', now(), now() + interval '7 days', false, 'trial')
                """,
                (parent["id"],),
            )
        connection.commit()

    if parent is None:
        raise ApiError("INTERNAL_ERROR", "Parent account could not be created.", 500)

    return envelope(
        {
            "parent_user_id": parent["id"],
            "account_status": parent["status"],
            "two_factor_required": False,
            "next_step": "setup_parent_pin",
        },
        "Parent account created.",
    )


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, full_name, email, status, two_factor_enabled, pin_enabled
                FROM parent_users
                WHERE email = %s
                  AND password_hash = crypt(%s, password_hash)
                  AND status IN ('active', 'pending_verification')
                """,
                (payload.email.lower(), payload.password),
            )
            parent = cursor.fetchone()

    if parent is None:
        raise ApiError("AUTH_REQUIRED", "Invalid email or password.", 401)

    two_factor_required = bool(parent["two_factor_enabled"])
    return envelope(
        {
            "login_status": "two_factor_required" if two_factor_required else "authenticated",
            "access_token_optional": None if two_factor_required else create_token(parent["id"], "parent", "access"),
            "refresh_token_optional": None if two_factor_required else create_token(parent["id"], "parent", "refresh"),
            "two_factor_required": two_factor_required,
            "pin_enabled": bool(parent["pin_enabled"]),
            "next_step": "verify_2fa" if two_factor_required else ("dashboard" if parent["pin_enabled"] else "setup_parent_pin"),
        }
    )


@router.post("/refresh")
def refresh(payload: RefreshRequest) -> dict[str, object]:
    claims = decode_token(payload.refresh_token)
    if claims["role"] != "parent" or claims["token_type"] != "refresh":
        raise ApiError("AUTH_REQUIRED", "Parent refresh token is required.", 401)
    return envelope(
        {
            "access_token": create_token(claims["sub"], "parent", "access"),
            "refresh_token": create_token(claims["sub"], "parent", "refresh"),
        }
    )


@router.post("/logout")
def logout() -> dict[str, object]:
    return envelope({"logged_out": True})


@router.post("/2fa/send-code")
def send_2fa_code() -> dict[str, object]:
    return envelope({"delivery_status": "sent", "expires_in_seconds": 300})


@router.post("/2fa/verify")
def verify_2fa() -> dict[str, object]:
    return envelope(
        {
            "login_status": "verification_pending",
            "access_token": None,
            "refresh_token": None,
            "next_step": "login",
        }
    )
