from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class CheckoutPayload(BaseModel):
    plan_code: str = "family_plus"
    billing_cycle: str = "monthly"


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.get("/plans")
def plans() -> dict[str, object]:
    return envelope(
        [
            {
                "code": "starter",
                "name": "Starter",
                "monthly_price_inr": 299,
                "allowed_child_count": 1,
                "features": ["safe chat", "dashboard"],
            },
            {
                "code": "family_plus",
                "name": "Family Plus",
                "monthly_price_inr": 599,
                "allowed_child_count": 3,
                "features": ["alerts", "2FA", "summaries"],
            },
            {
                "code": "family_max",
                "name": "Family Max",
                "monthly_price_inr": 999,
                "allowed_child_count": 5,
                "features": ["advanced controls", "voice later"],
            },
        ]
    )


def _latest_subscription(parent_id: str) -> dict[str, object] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT parent_user_id::text, plan_code, billing_cycle, status,
                       auto_renew, starts_at::text, ends_at::text, updated_at::text
                FROM subscriptions
                WHERE parent_user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (parent_id,),
            )
            subscription = cursor.fetchone()
    return dict(subscription) if subscription else None


@router.get("/subscription")
def subscription(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    current = _latest_subscription(parent_id)
    if current is not None:
        return envelope(current)
    return envelope(
        {
            "parent_user_id": parent_id,
            "plan_code": "starter",
            "billing_cycle": "monthly",
            "status": "active",
            "auto_renew": False,
        }
    )


@router.post("/checkout-session", status_code=201)
def checkout_session(payload: CheckoutPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
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
                VALUES (%s, %s, %s, 'active', true, 'demo')
                """,
                (parent_id, payload.plan_code, payload.billing_cycle),
            )
        connection.commit()
    return envelope(
        {
            "checkout_session_id": "checkout_demo",
            "status": "created",
            "plan_code": payload.plan_code,
            "billing_cycle": payload.billing_cycle,
            "redirect_url": "https://billing.example/pikuai/demo",
        },
        "Checkout created.",
    )


@router.patch("/subscription")
def update_subscription(payload: CheckoutPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
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
                VALUES (%s, %s, %s, 'active', true, 'demo')
                RETURNING parent_user_id::text, plan_code, billing_cycle, status,
                          auto_renew, starts_at::text, ends_at::text, updated_at::text
                """,
                (parent_id, payload.plan_code, payload.billing_cycle),
            )
            subscription_record = cursor.fetchone()
        connection.commit()
    return envelope(dict(subscription_record), "Subscription updated.")


@router.post("/subscription/cancel")
def cancel_subscription(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE subscriptions
                SET status = 'canceled',
                    auto_renew = false,
                    updated_at = now()
                WHERE id = (
                  SELECT id
                  FROM subscriptions
                  WHERE parent_user_id = %s
                  ORDER BY created_at DESC
                  LIMIT 1
                )
                RETURNING parent_user_id::text, plan_code, billing_cycle, status,
                          auto_renew, starts_at::text, ends_at::text, updated_at::text
                """,
                (parent_id,),
            )
            subscription_record = cursor.fetchone()
        connection.commit()
    return envelope(dict(subscription_record) if subscription_record else None, "Subscription canceled.")
