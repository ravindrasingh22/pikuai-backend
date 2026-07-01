from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.modules.mail.service import send_template_email
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class SupportRequestPayload(BaseModel):
    subject: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10, max_length=1200)


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.post("/request", status_code=201)
def create_support_request(
    payload: SupportRequestPayload,
    claims: TokenClaims = Depends(require_parent_or_admin),
) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT full_name, email FROM parent_users WHERE id = %s", (parent_id,))
            parent = cursor.fetchone()

    if parent is None:
        raise ApiError("NOT_FOUND", "Parent profile was not found.", 404)

    request_id = f"PRTV-SUP-{parent_id[:8]}"
    send_template_email(
        "support_request_received_parent",
        parent["email"],
        {
            "parent_first_name": str(parent["full_name"]).split(" ", 1)[0],
            "parent_email": parent["email"],
            "request_id": request_id,
            "cta_link": "pratvim://parent/support",
        },
        to_name=parent["full_name"],
    )

    return envelope(
        {
            "request_id": request_id,
            "request_status": "submitted",
            "subject": payload.subject,
        },
        "Support request submitted.",
    )
