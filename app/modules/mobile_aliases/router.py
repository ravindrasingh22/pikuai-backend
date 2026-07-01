from fastapi import APIRouter, Depends

from app.core.security import TokenClaims, require_parent_or_admin
from app.db.session import get_connection
from app.modules.alerts.router import get_alert, list_alerts
from app.modules.billing.router import CheckoutPayload, checkout_session, plans, subscription
from app.modules.dashboard.router import overview
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


def _parent_id(claims: TokenClaims) -> str:
    if claims["role"] != "parent":
        raise ApiError("FORBIDDEN", "Parent access is required.", 403)
    return claims["sub"]


@router.get("/session/current")
def session_current(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
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
        raise ApiError("NOT_FOUND", "Parent session was not found.", 404)
    return envelope({"profile_type": "parent", "profile": dict(parent)})


@router.get("/dashboard/parent")
def parent_dashboard(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    return overview(claims)


@router.get("/plans/family")
def family_plans() -> dict[str, object]:
    return plans()


@router.get("/subscriptions/current")
def current_subscription(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    return subscription(claims)


@router.post("/checkout/session", status_code=201)
def create_checkout_session(payload: CheckoutPayload, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    return checkout_session(payload, claims)


@router.post("/checkout/confirm")
def confirm_checkout(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    current = subscription(claims)
    return envelope({"confirmed": True, "subscription": current.get("data")}, "Checkout confirmed.")


@router.get("/safety-alerts")
def safety_alerts(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    return list_alerts(claims)


@router.get("/safety-alerts/summary")
def safety_alert_summary(claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = 'unread') AS pending,
                  COUNT(*) FILTER (WHERE status <> 'unread') AS reviewed
                FROM admin_notifications
                WHERE parent_user_id = %s
                """,
                (parent_id,),
            )
            row = cursor.fetchone()
    return envelope({"total": int(row["total"]), "pending": int(row["pending"]), "reviewed": int(row["reviewed"])})


@router.get("/safety-alerts/{alert_id}")
def safety_alert(alert_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    return get_alert(alert_id, claims)


@router.patch("/safety-alerts/{alert_id}/review")
def review_safety_alert(alert_id: str, claims: TokenClaims = Depends(require_parent_or_admin)) -> dict[str, object]:
    parent_id = _parent_id(claims)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE admin_notifications
                SET status = 'reviewed',
                    updated_at = now()
                WHERE id = %s
                  AND parent_user_id = %s
                RETURNING id::text, status, updated_at::text
                """,
                (alert_id, parent_id),
            )
            alert = cursor.fetchone()
        connection.commit()
    if alert is None:
        raise ApiError("NOT_FOUND", "Safety alert was not found.", 404)
    return envelope(dict(alert), "Safety alert reviewed.")
