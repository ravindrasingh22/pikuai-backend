from random import SystemRandom

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.security import TokenClaims, create_token, decode_token, require_parent
from app.db.session import get_connection
from app.modules.mail.service import send_template_email
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class RegisterParentRequest(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=8)
    country: str = Field(min_length=2)
    preferred_language: str = Field(min_length=2)


class ParentEmailRegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    accepted_terms: bool = Field(alias="acceptedTerms")
    accepted_privacy_policy: bool = Field(alias="acceptedPrivacyPolicy")


class ConfirmParentEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendParentEmailRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class SetParentPasswordRequest(BaseModel):
    password: str = Field(min_length=8)


class PinVerifyRequest(BaseModel):
    profile_type: str = Field(alias="profileType", pattern=r"^(parent|kid)$")
    pin: str = Field(pattern=r"^\d{4}$")
    profile_id: str | None = Field(default=None, alias="profileId")


def _confirmation_code() -> str:
    return f"{SystemRandom().randint(0, 999999):06d}"


def _send_confirmation_email(email: str, code: str, full_name: str = "Parent") -> None:
    send_template_email(
        "auth_email_confirmation_code_parent",
        email,
        {
            "parent_first_name": full_name.split(" ", 1)[0] or "Parent",
            "parent_email": email,
            "confirmation_code": code,
            "expiry_minutes": "15",
            "cta_link": "pratvim://parent/confirm-email",
        },
        to_name=full_name,
    )


def _parent_next_step(cursor, parent_id: str, parent: dict[str, object]) -> str:
    if not bool(parent.get("email_verified", True)):
        return "confirm_email"
    if not parent.get("password_hash") or str(parent.get("full_name") or "").strip().lower() == "parent":
        return "parent_details"
    if str(parent.get("onboarding_status") or "complete") != "complete":
        return "parent_onboarding"
    if not bool(parent.get("pin_enabled")):
        return "setup_parent_pin"
    cursor.execute("SELECT COUNT(*) AS child_count FROM child_profiles WHERE parent_user_id = %s AND active_status = 'active'", (parent_id,))
    child_count = cursor.fetchone()["child_count"]
    if int(child_count) == 0:
        return "kid_setup"
    return "dashboard"


def _login_payload(cursor, parent: dict[str, object]) -> dict[str, object]:
    parent_id = str(parent["id"])
    two_factor_required = bool(parent["two_factor_enabled"])
    return {
        "login_status": "two_factor_required" if two_factor_required else "authenticated",
        "access_token_optional": None if two_factor_required else create_token(parent_id, "parent", "access"),
        "refresh_token_optional": None if two_factor_required else create_token(parent_id, "parent", "refresh"),
        "two_factor_required": two_factor_required,
        "pin_enabled": bool(parent["pin_enabled"]),
        "next_step": "verify_2fa" if two_factor_required else _parent_next_step(cursor, parent_id, parent),
    }


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
                  pin_enabled,
                  email_verified,
                  password_set_at
                )
                VALUES (%s, %s, crypt(%s, gen_salt('bf')), 'active', %s, %s, false, false, true, now())
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

    send_template_email(
        "onboarding_parent_welcome",
        email,
        {
            "parent_first_name": payload.full_name.split(" ", 1)[0],
            "parent_email": email,
            "dashboard_link": "pratvim://parent/home",
            "cta_link": "pratvim://parent/home",
        },
        to_name=payload.full_name,
    )

    return envelope(
        {
            "parent_user_id": parent["id"],
            "account_status": parent["status"],
            "two_factor_required": False,
            "next_step": "setup_parent_pin",
        },
        "Parent account created.",
    )


@router.post("/parent/register", status_code=201)
def register_parent_email(payload: ParentEmailRegisterRequest) -> dict[str, object]:
    if not payload.accepted_terms or not payload.accepted_privacy_policy:
        raise ApiError("VALIDATION_ERROR", "Terms and Privacy Policy must be accepted.", 422)

    email = payload.email.lower()
    code = _confirmation_code()
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
                  pin_enabled,
                  email_verified,
                  email_confirmation_code_hash,
                  email_confirmation_expires_at,
                  accepted_terms_at,
                  accepted_privacy_policy_at,
                  onboarding_status
                )
                VALUES (
                  'Parent',
                  %s,
                  NULL,
                  'pending_verification',
                  'IN',
                  'en',
                  false,
                  false,
                  false,
                  crypt(%s, gen_salt('bf')),
                  now() + interval '15 minutes',
                  now(),
                  now(),
                  'pending'
                )
                RETURNING id::text, full_name, email, status
                """,
                (email, code),
            )
            parent = cursor.fetchone()
        connection.commit()

    _send_confirmation_email(email, code)
    return envelope(
        {
            "parent_user_id": parent["id"],
            "email": parent["email"],
            "account_status": parent["status"],
            "next_step": "confirm_email",
        },
        "Confirmation code sent.",
    )


@router.post("/parent/confirm-email")
def confirm_parent_email(payload: ConfirmParentEmailRequest) -> dict[str, object]:
    email = payload.email.lower()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_users
                SET email_verified = true,
                    status = 'active',
                    email_confirmation_code_hash = NULL,
                    email_confirmation_expires_at = NULL,
                    updated_at = now()
                WHERE email = %s
                  AND email_verified = false
                  AND email_confirmation_expires_at > now()
                  AND email_confirmation_code_hash = crypt(%s, email_confirmation_code_hash)
                RETURNING id::text, full_name, email, status, two_factor_enabled, pin_enabled,
                          email_verified, password_hash, onboarding_status
                """,
                (email, payload.code),
            )
            parent = cursor.fetchone()
            if parent is None:
                raise ApiError("VALIDATION_ERROR", "Invalid or expired confirmation code.", 422)
            payload_data = _login_payload(cursor, parent)
        connection.commit()

    return envelope(payload_data, "Email confirmed.")


@router.post("/parent/resend-confirmation-code")
def resend_parent_confirmation_code(payload: ResendParentEmailRequest) -> dict[str, object]:
    email = payload.email.lower()
    code = _confirmation_code()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_users
                SET email_confirmation_code_hash = crypt(%s, gen_salt('bf')),
                    email_confirmation_expires_at = now() + interval '15 minutes',
                    updated_at = now()
                WHERE email = %s
                  AND email_verified = false
                RETURNING full_name, email
                """,
                (code, email),
            )
            parent = cursor.fetchone()
        connection.commit()

    if parent is None:
        raise ApiError("NOT_FOUND", "Pending parent registration was not found.", 404)

    _send_confirmation_email(parent["email"], code, parent["full_name"])
    return envelope({"delivery_status": "sent", "expires_in_seconds": 900}, "Confirmation code resent.")


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, full_name, email, status, two_factor_enabled, pin_enabled,
                       email_verified, password_hash, onboarding_status
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

    with get_connection() as connection:
        with connection.cursor() as cursor:
            return envelope(_login_payload(cursor, parent))


@router.post("/parent/login")
def parent_login(payload: LoginRequest) -> dict[str, object]:
    return login(payload)


@router.post("/parent/set-password")
def set_parent_password(payload: SetParentPasswordRequest, claims: TokenClaims = Depends(require_parent)) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parent_users
                SET password_hash = crypt(%s, gen_salt('bf')),
                    password_set_at = now(),
                    updated_at = now()
                WHERE id = %s
                  AND email_verified = true
                RETURNING id::text, full_name, email
                """,
                (payload.password, claims["sub"]),
            )
            parent = cursor.fetchone()
        connection.commit()
    if parent is None:
        raise ApiError("VALIDATION_ERROR", "Confirm parent email before setting a password.", 422)

    send_template_email(
        "auth_password_changed_parent",
        parent["email"],
        {
            "parent_first_name": str(parent["full_name"]).split(" ", 1)[0],
            "parent_email": parent["email"],
            "event_time": "now",
            "support_email": "support@pratvim.ai",
            "cta_link": "pratvim://parent/settings",
        },
        to_name=parent["full_name"],
    )
    return envelope({"password_set": True}, "Parent password configured.")


@router.post("/pin/verify")
def verify_profile_pin(payload: PinVerifyRequest, claims: TokenClaims = Depends(require_parent)) -> dict[str, object]:
    parent_id = claims["sub"]
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if payload.profile_type == "parent":
                cursor.execute(
                    """
                    SELECT id::text
                    FROM parent_users
                    WHERE id = %s
                      AND pin_enabled = true
                      AND pin_hash = crypt(%s, pin_hash)
                    """,
                    (parent_id, payload.pin),
                )
                row = cursor.fetchone()
                profile_id = parent_id
            else:
                if not payload.profile_id:
                    raise ApiError("VALIDATION_ERROR", "Kid profile id is required.", 422)
                cursor.execute(
                    """
                    SELECT id::text
                    FROM child_profiles
                    WHERE id = %s
                      AND parent_user_id = %s
                      AND child_pin_enabled = true
                      AND child_pin_hash = crypt(%s, child_pin_hash)
                    """,
                    (payload.profile_id, parent_id, payload.pin),
                )
                row = cursor.fetchone()
                profile_id = payload.profile_id

    if row is None:
        raise ApiError("AUTH_REQUIRED", "Invalid PIN.", 401)
    return envelope({"verified": True, "profile_type": payload.profile_type, "profile_id": profile_id})


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
