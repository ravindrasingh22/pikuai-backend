from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
from typing import Literal, TypedDict

from fastapi import Header

from app.core.config import settings
from app.shared.exceptions import ApiError

UserRole = Literal["admin", "parent"]
TokenType = Literal["access", "refresh"]


class TokenClaims(TypedDict):
    sub: str
    role: UserRole
    token_type: TokenType
    exp: int
    iat: int


def create_token(user_id: str, role: UserRole, token_type: TokenType = "access") -> str:
    now = datetime.now(UTC)
    expires_at = (
        now + timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else now + timedelta(days=settings.refresh_token_days)
    )
    payload: TokenClaims = {
        "sub": user_id,
        "role": role,
        "token_type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return _encode_jwt(payload)


def decode_token(token: str) -> TokenClaims:
    try:
        payload = _decode_jwt(token)
    except ValueError as exc:
        raise ApiError("AUTH_REQUIRED", "Invalid authentication token.", 401) from exc

    if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
        raise ApiError("TOKEN_EXPIRED", "Session expired. Login again.", 401)
    if not isinstance(payload.get("sub"), str) or payload.get("role") not in {"admin", "parent"}:
        raise ApiError("AUTH_REQUIRED", "Invalid authentication token.", 401)
    if payload.get("token_type") not in {"access", "refresh"}:
        raise ApiError("AUTH_REQUIRED", "Invalid authentication token.", 401)
    return payload  # type: ignore[return-value]


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("AUTH_REQUIRED", "Bearer token is required.", 401)
    return authorization.split(" ", 1)[1].strip()


def require_access_token(
    expected_role: UserRole,
    authorization: str | None = Header(default=None),
) -> TokenClaims:
    claims = decode_token(_bearer_token(authorization))
    if claims["token_type"] != "access":
        raise ApiError("AUTH_REQUIRED", "Access token is required.", 401)
    if claims["role"] != expected_role:
        raise ApiError("FORBIDDEN", f"{expected_role.title()} access is required.", 403)
    return claims


def require_admin(authorization: str | None = Header(default=None)) -> TokenClaims:
    return require_access_token("admin", authorization)


def require_parent(authorization: str | None = Header(default=None)) -> TokenClaims:
    return require_access_token("parent", authorization)


def require_parent_or_admin(authorization: str | None = Header(default=None)) -> TokenClaims:
    claims = decode_token(_bearer_token(authorization))
    if claims["token_type"] != "access":
        raise ApiError("AUTH_REQUIRED", "Access token is required.", 401)
    if claims["role"] not in {"parent", "admin"}:
        raise ApiError("FORBIDDEN", "Parent or admin access is required.", 403)
    return claims


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _encode_jwt(payload: TokenClaims) -> str:
    if settings.jwt_algorithm != "HS256":
        raise ApiError("INTERNAL_ERROR", "Only HS256 JWT signing is supported.", 500)
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_base64url_encode(signature)}"


def _decode_jwt(token: str) -> dict[str, object]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise ValueError("Invalid JWT format.") from exc

    header = json.loads(_base64url_decode(header_segment))
    if header.get("alg") != "HS256":
        raise ValueError("Unsupported JWT algorithm.")

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    provided_signature = _base64url_decode(signature_segment)
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Invalid JWT signature.")
    payload = json.loads(_base64url_decode(payload_segment))
    if not isinstance(payload, dict):
        raise ValueError("Invalid JWT payload.")
    return payload
