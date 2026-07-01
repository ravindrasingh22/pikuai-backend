from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from html import escape
import re
import smtplib
from typing import Any

from app.db.session import get_connection
from app.shared.exceptions import ApiError

SUPPORT_EMAIL = "support@pratvim.ai"
LOGO_URL = "https://yellow-fly-539164.hostingersite.com/wp-content/themes/pratvim-theme/assets/img/pratvim-wordmark.svg"


DEFAULT_EMAIL_TEMPLATES: list[dict[str, object]] = [
    {"template_key": "auth_email_confirmation_code_parent", "template_ref": "PRTV-AUTH-001", "category": "Auth", "name": "Email confirmation code", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Parent registers with email", "subject": "Your Pratvim confirmation code", "preview_text": "Use this code to complete your parent registration.", "cta_label": "Confirm Email", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim confirmation code is:\n\n{{ confirmation_code }}\n\nThis code expires in {{ expiry_minutes }} minutes.\n\nIf you did not create a Pratvim parent account, you can ignore this email."},
    {"template_key": "auth_login_otp_parent", "template_ref": "PRTV-AUTH-002", "category": "Auth", "name": "Parent login OTP", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Parent logs in with OTP or secure verification", "subject": "Your Pratvim login code", "preview_text": "Use this code to sign in to your parent account.", "cta_label": "Open Pratvim", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim login code is:\n\n{{ otp_code }}\n\nThis code expires in {{ expiry_minutes }} minutes.\n\nIf this was not you, please change your password or contact {{ support_email }}."},
    {"template_key": "auth_password_reset_parent", "template_ref": "PRTV-AUTH-003", "category": "Auth", "name": "Password reset", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Parent requests password reset", "subject": "Reset your Pratvim password", "preview_text": "Use this secure link to reset your parent account password.", "cta_label": "Reset Password", "body_text": "Hi {{ parent_first_name }},\n\nWe received a request to reset your Pratvim password.\n\nUse the secure link below to reset it. This link expires in {{ expiry_minutes }} minutes.\n\n{{ reset_link }}\n\nIf you did not request this, you can ignore this email."},
    {"template_key": "auth_password_changed_parent", "template_ref": "PRTV-AUTH-004", "category": "Auth", "name": "Password changed confirmation", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent password changed successfully", "subject": "Your Pratvim password was changed", "preview_text": "This is a confirmation that your parent account password was updated.", "cta_label": "Review Account", "body_text": "Hi {{ parent_first_name }},\n\nThis confirms your Pratvim parent account password was changed at {{ event_time }}.\n\nIf this was not you, contact {{ support_email }}."},
    {"template_key": "security_new_device_login_parent", "template_ref": "PRTV-AUTH-005", "category": "Security", "name": "New device login alert", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent account login from a new device", "subject": "New login to your Pratvim parent account", "preview_text": "We noticed a login from a new device.", "cta_label": "Review Account", "body_text": "Hi {{ parent_first_name }},\n\nWe noticed a login to your Pratvim parent account at {{ event_time }}.\n\nDevice: {{ device_name }}\nIP address: {{ ip_address }}\n\nIf this was not you, contact {{ support_email }}."},
    {"template_key": "account_parent_profile_updated", "template_ref": "PRTV-AUTH-006", "category": "Account", "name": "Parent profile updated", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent updates profile details", "subject": "Your Pratvim parent profile was updated", "preview_text": "Your account details were changed successfully.", "cta_label": "Review Profile", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim parent profile was updated at {{ event_time }}.\n\nUpdated fields: {{ updated_fields }}"},
    {"template_key": "auth_email_change_confirmation_code_parent", "template_ref": "PRTV-AUTH-007", "category": "Auth", "name": "Parent email change confirmation code", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent requests email address change", "subject": "Confirm your new Pratvim email address", "preview_text": "Use this code to confirm your new parent account email.", "cta_label": "Confirm Email", "body_text": "Hi {{ parent_first_name }},\n\nUse this code to confirm {{ new_email }} for your Pratvim parent account:\n\n{{ confirmation_code }}\n\nThis code expires in {{ expiry_minutes }} minutes."},
    {"template_key": "security_parent_pin_changed", "template_ref": "PRTV-AUTH-008", "category": "Security", "name": "Parent PIN changed", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent PIN changed successfully", "subject": "Your Pratvim parent PIN was changed", "preview_text": "This confirms a change to your parent-only access PIN.", "cta_label": "Open Pratvim", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim parent PIN was changed at {{ event_time }}.\n\nIf this was not you, contact {{ support_email }}."},
    {"template_key": "onboarding_parent_welcome", "template_ref": "PRTV-ONB-001", "category": "Onboarding", "name": "Parent welcome", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Parent account setup completed", "subject": "Welcome to Pratvim", "preview_text": "Create a protected AI learning space for your family.", "cta_label": "Open Parent Home", "body_text": "Hi {{ parent_first_name }},\n\nWelcome to Pratvim - a protected AI learning space where children can ask, understand, and explore with parent-managed boundaries.\n\nYou can now create child profiles, set private PINs, manage screen-time habits, and review safety activity from Parent Home."},
    {"template_key": "onboarding_parent_setup_reminder", "template_ref": "PRTV-ONB-002", "category": "Onboarding", "name": "Parent onboarding reminder", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent registered but has not completed setup", "subject": "Finish setting up your Pratvim family space", "preview_text": "Complete setup to start protected learning.", "cta_label": "Continue Setup", "body_text": "Hi {{ parent_first_name }},\n\nFinish setting up your Pratvim family space to start protected learning.\n\nContinue here: {{ setup_link }}"},
    {"template_key": "profile_child_created_parent", "template_ref": "PRTV-PROFILE-001", "category": "Profile", "name": "Child profile created", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Parent creates a child profile", "subject": "A child profile was created in Pratvim", "preview_text": "The new learning profile is ready for protected access.", "cta_label": "View Profile", "body_text": "Hi {{ parent_first_name }},\n\nThe child profile \"{{ child_profile_name }}\" is now ready in Pratvim.\n\nYou can manage the profile, private PIN, screen-time habits, and activity from Parent Home."},
    {"template_key": "profile_child_updated_parent", "template_ref": "PRTV-PROFILE-002", "category": "Profile", "name": "Child profile updated", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Child profile display name, avatar, age band, or settings updated", "subject": "A child profile was updated in Pratvim", "preview_text": "A child profile setting was changed.", "cta_label": "View Profile", "body_text": "Hi {{ parent_first_name }},\n\nThe child profile \"{{ child_profile_name }}\" was updated at {{ event_time }}."},
    {"template_key": "profile_child_deleted_parent", "template_ref": "PRTV-PROFILE-003", "category": "Profile", "name": "Child profile deleted", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent deletes a child profile", "subject": "A child profile was deleted from Pratvim", "preview_text": "A child profile was removed from your family space.", "cta_label": "Open Parent Home", "body_text": "Hi {{ parent_first_name }},\n\nThe child profile \"{{ child_profile_name }}\" was removed from Pratvim at {{ event_time }}."},
    {"template_key": "profile_child_limit_reached_parent", "template_ref": "PRTV-PROFILE-004", "category": "Profile", "name": "Child profile limit reached", "priority": "P3", "audience": "Parent / Guardian", "trigger": "Parent tries to add more child profiles than plan allows", "subject": "You have reached your Pratvim child profile limit", "preview_text": "Your current plan has reached its child profile limit.", "cta_label": "Manage Plan", "body_text": "Hi {{ parent_first_name }},\n\nYour current plan allows {{ child_limit }} child profile(s). Manage your plan to add more profiles."},
    {"template_key": "account_guardian_invite", "template_ref": "PRTV-ACCOUNT-001", "category": "Account", "name": "Guardian invite", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent invites another guardian", "subject": "You have been invited to join a Pratvim family space", "preview_text": "A guardian invited you to help manage a Pratvim family space.", "cta_label": "Accept Invite", "body_text": "Hi,\n\nYou have been invited to join a Pratvim family space.\n\nAccept invite: {{ invite_link }}"},
    {"template_key": "safety_alert_needs_review_parent", "template_ref": "PRTV-SAFETY-001", "category": "Safety", "name": "Safety alert needs review", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Guardrail creates a parent-review safety alert", "subject": "A Pratvim safety alert needs your review", "preview_text": "Open Pratvim to review a child-safety alert.", "cta_label": "Review Alert", "body_text": "Hi {{ parent_first_name }},\n\nA safety alert needs parent review for {{ child_profile_name }}.\n\nOpen Pratvim to review the alert. Sensitive child conversation text is not included in this email."},
    {"template_key": "safety_urgent_concern_parent", "template_ref": "PRTV-SAFETY-002", "category": "Safety", "name": "Urgent safety concern", "priority": "P1", "audience": "Parent / Guardian", "trigger": "High-severity guardrail category requiring immediate parent attention", "subject": "Please review an urgent Pratvim safety alert", "preview_text": "Open Pratvim to review an urgent child-safety alert.", "cta_label": "Review Now", "body_text": "Hi {{ parent_first_name }},\n\nAn urgent safety concern needs your review for {{ child_profile_name }}.\n\nOpen Pratvim to review. Sensitive child conversation text is not included in this email."},
    {"template_key": "safety_alert_reviewed_parent", "template_ref": "PRTV-SAFETY-003", "category": "Safety", "name": "Safety alert reviewed", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent marks a safety alert as reviewed or closed", "subject": "A Pratvim safety alert was marked as reviewed", "preview_text": "This confirms the alert status was updated.", "cta_label": "Open Pratvim", "body_text": "Hi {{ parent_first_name }},\n\nA Pratvim safety alert was marked as reviewed at {{ event_time }}."},
    {"template_key": "safety_blocked_response_parent_notice", "template_ref": "PRTV-SAFETY-004", "category": "Safety", "name": "Child blocked-response notice", "priority": "P2", "audience": "Parent / Guardian", "trigger": "The app blocks a high-risk answer and redirects the child safely", "subject": "Pratvim redirected a sensitive question", "preview_text": "Pratvim redirected a child away from unsafe content.", "cta_label": "Review Activity", "body_text": "Hi {{ parent_first_name }},\n\nPratvim redirected a sensitive question for {{ child_profile_name }}. Open Pratvim to review details."},
    {"template_key": "report_weekly_learning_summary_parent", "template_ref": "PRTV-REPORT-001", "category": "Reports", "name": "Weekly learning summary", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Weekly scheduled digest", "subject": "Your Pratvim weekly learning summary", "preview_text": "Review this week's learning activity.", "cta_label": "View Summary", "body_text": "Hi {{ parent_first_name }},\n\nYour weekly Pratvim learning summary is ready.\n\nSessions: {{ weekly_sessions }}\nAlerts to review: {{ pending_alerts }}"},
    {"template_key": "report_child_learning_summary_parent", "template_ref": "PRTV-REPORT-002", "category": "Reports", "name": "Individual child learning report", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent requests or scheduled child-specific report", "subject": "Learning summary for {{ child_profile_name }}", "preview_text": "Review a child-specific learning summary.", "cta_label": "View Report", "body_text": "Hi {{ parent_first_name }},\n\nThe learning summary for {{ child_profile_name }} is ready in Pratvim."},
    {"template_key": "screen_time_complete_parent", "template_ref": "PRTV-SCREEN-001", "category": "Screen Time", "name": "Screen time complete", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Child reaches configured screen-time limit", "subject": "Screen time completed in Pratvim", "preview_text": "A child reached their configured Pratvim time limit.", "cta_label": "Review Screen Time", "body_text": "Hi {{ parent_first_name }},\n\n{{ child_profile_name }} reached the configured Pratvim screen-time limit today."},
    {"template_key": "screen_time_setting_changed_parent", "template_ref": "PRTV-SCREEN-002", "category": "Screen Time", "name": "Screen-time setting changed", "priority": "P3", "audience": "Parent / Guardian", "trigger": "Parent changes screen-time limit for a child profile", "subject": "A Pratvim screen-time setting was changed", "preview_text": "This confirms a screen-time setting change.", "cta_label": "Open Settings", "body_text": "Hi {{ parent_first_name }},\n\nA screen-time setting for {{ child_profile_name }} was changed at {{ event_time }}."},
    {"template_key": "billing_family_plan_active_parent", "template_ref": "PRTV-BILLING-001", "category": "Billing", "name": "Family plan active", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Payment successful and family plan activated", "subject": "Your Pratvim family plan is active", "preview_text": "Your family plan is now active.", "cta_label": "Manage Plan", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim {{ plan_code }} plan is active."},
    {"template_key": "billing_payment_receipt_parent", "template_ref": "PRTV-BILLING-002", "category": "Billing", "name": "Payment receipt", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Payment captured successfully", "subject": "Your Pratvim payment receipt", "preview_text": "Your payment receipt is ready.", "cta_label": "View Billing", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim payment was received.\n\nAmount: {{ amount }}\nRequest ID: {{ request_id }}"},
    {"template_key": "billing_payment_failed_parent", "template_ref": "PRTV-BILLING-003", "category": "Billing", "name": "Payment failed", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Subscription renewal or checkout payment fails", "subject": "Your Pratvim payment could not be completed", "preview_text": "Please update payment details to keep access active.", "cta_label": "Update Payment", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim payment could not be completed. Please update payment details to keep access active."},
    {"template_key": "billing_subscription_renewal_reminder_parent", "template_ref": "PRTV-BILLING-004", "category": "Billing", "name": "Subscription renewal reminder", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Upcoming plan renewal", "subject": "Your Pratvim family plan renews soon", "preview_text": "Your plan renewal is coming up.", "cta_label": "Manage Plan", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim family plan renews on {{ renewal_date }}."},
    {"template_key": "billing_subscription_cancelled_parent", "template_ref": "PRTV-BILLING-005", "category": "Billing", "name": "Subscription cancelled", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent cancels subscription", "subject": "Your Pratvim family plan was cancelled", "preview_text": "This confirms your plan cancellation.", "cta_label": "Manage Plan", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim family plan was cancelled at {{ event_time }}."},
    {"template_key": "billing_plan_expired_access_paused_parent", "template_ref": "PRTV-BILLING-006", "category": "Billing", "name": "Plan expired / access paused", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Paid plan expires and access is paused or downgraded", "subject": "Your Pratvim family plan has expired", "preview_text": "Your paid plan expired and access may be paused.", "cta_label": "Renew Plan", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim family plan has expired. Renew your plan to continue paid access."},
    {"template_key": "billing_low_token_balance_parent", "template_ref": "PRTV-BILLING-007", "category": "Billing", "name": "Low token balance", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Family token/credit balance drops below threshold", "subject": "Your Pratvim protected chat balance is running low", "preview_text": "Your protected chat balance is low.", "cta_label": "Add Balance", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim protected chat balance is running low. Remaining balance: {{ balance }}."},
    {"template_key": "support_request_received_parent", "template_ref": "PRTV-SUPPORT-001", "category": "Support", "name": "Support request received", "priority": "P0", "audience": "Parent / Guardian", "trigger": "Parent submits support request", "subject": "We received your Pratvim support request", "preview_text": "Pratvim Support received your request.", "cta_label": "View Request", "body_text": "Hi {{ parent_first_name }},\n\nWe received your Pratvim support request.\n\nRequest ID: {{ request_id }}"},
    {"template_key": "support_reply_available_parent", "template_ref": "PRTV-SUPPORT-002", "category": "Support", "name": "Support reply notification", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Support team replies to a request", "subject": "Pratvim Support replied to your request", "preview_text": "A support reply is available.", "cta_label": "View Reply", "body_text": "Hi {{ parent_first_name }},\n\nPratvim Support replied to your request {{ request_id }}."},
    {"template_key": "privacy_data_request_received_parent", "template_ref": "PRTV-PRIVACY-001", "category": "Privacy", "name": "Privacy or data request received", "priority": "P1", "audience": "Parent / Guardian", "trigger": "Parent submits data export, correction, deletion, or privacy request", "subject": "We received your Pratvim privacy request", "preview_text": "Your privacy request was received.", "cta_label": "Review Privacy", "body_text": "Hi {{ parent_first_name }},\n\nWe received your Pratvim privacy request.\n\nRequest ID: {{ request_id }}"},
    {"template_key": "privacy_data_export_ready_parent", "template_ref": "PRTV-PRIVACY-002", "category": "Privacy", "name": "Data export ready", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent-requested data export is ready", "subject": "Your Pratvim data export is ready", "preview_text": "Your requested data export is ready.", "cta_label": "Download Export", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim data export is ready.\n\nDownload link: {{ export_link }}"},
    {"template_key": "privacy_account_deletion_request_received_parent", "template_ref": "PRTV-PRIVACY-003", "category": "Privacy", "name": "Account deletion request received", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Parent requests account deletion", "subject": "We received your Pratvim account deletion request", "preview_text": "Your account deletion request was received.", "cta_label": "Review Request", "body_text": "Hi {{ parent_first_name }},\n\nWe received your Pratvim account deletion request at {{ event_time }}.\n\nRequest ID: {{ request_id }}"},
    {"template_key": "privacy_account_deletion_completed_parent", "template_ref": "PRTV-PRIVACY-004", "category": "Privacy", "name": "Account deletion completed", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Account deletion completed", "subject": "Your Pratvim account deletion is complete", "preview_text": "This confirms account deletion is complete.", "cta_label": "Contact Support", "body_text": "Hi {{ parent_first_name }},\n\nYour Pratvim account deletion is complete."},
    {"template_key": "legal_terms_privacy_update_parent", "template_ref": "PRTV-LEGAL-001", "category": "Legal", "name": "Terms or privacy update", "priority": "P2", "audience": "Parent / Guardian", "trigger": "Terms, Privacy Policy, or child-safety policy is materially updated", "subject": "We updated Pratvim's terms or privacy information", "preview_text": "Review updates to Pratvim legal or privacy information.", "cta_label": "Review Updates", "body_text": "Hi {{ parent_first_name }},\n\nWe updated Pratvim's terms, privacy, or child-safety information.\n\nReview details: {{ privacy_policy_link }}"},
]


def seed_email_templates() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for template in DEFAULT_EMAIL_TEMPLATES:
                cursor.execute(
                    """
                    INSERT INTO email_templates (
                      template_key, template_ref, category, name, priority, audience,
                      trigger_description, subject, preview_text, cta_label, body_text
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (template_key) DO NOTHING
                    """,
                    (
                        template["template_key"],
                        template["template_ref"],
                        template["category"],
                        template["name"],
                        template["priority"],
                        template["audience"],
                        template["trigger"],
                        template["subject"],
                        template["preview_text"],
                        template["cta_label"],
                        template["body_text"],
                    ),
                )
        connection.commit()


def list_email_templates() -> list[dict[str, object]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT template_key, template_ref, category, name, priority, audience,
                       trigger_description, subject, preview_text, cta_label, body_text,
                       enabled, updated_at::text
                FROM email_templates
                ORDER BY category ASC, template_ref ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]


def get_email_template(template_key: str) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT template_key, template_ref, category, name, priority, audience,
                       trigger_description, subject, preview_text, cta_label, body_text,
                       enabled, updated_at::text
                FROM email_templates
                WHERE template_key = %s
                """,
                (template_key,),
            )
            template = cursor.fetchone()
    if template is None:
        raise ApiError("EMAIL_TEMPLATE_NOT_FOUND", "Email template was not found.", 404)
    return dict(template)


def update_email_template(template_key: str, updates: dict[str, object]) -> dict[str, object]:
    current = get_email_template(template_key)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE email_templates
                SET subject = %s,
                    preview_text = %s,
                    cta_label = %s,
                    body_text = %s,
                    enabled = %s,
                    updated_at = now()
                WHERE template_key = %s
                """,
                (
                    updates.get("subject", current["subject"]),
                    updates.get("preview_text", current["preview_text"]),
                    updates.get("cta_label", current["cta_label"]),
                    updates.get("body_text", current["body_text"]),
                    updates.get("enabled", current["enabled"]),
                    template_key,
                ),
            )
        connection.commit()
    return get_email_template(template_key)


def send_template_email(
    template_key: str,
    to_email: str,
    params: dict[str, Any] | None = None,
    *,
    to_name: str | None = None,
    raise_on_error: bool = False,
) -> bool:
    try:
        template = get_email_template(template_key)
        if not template["enabled"]:
            return False
        merged_params = _default_params(params or {})
        subject = _render(str(template["subject"]), merged_params)
        body = _render(str(template["body_text"]), merged_params)
        html = _email_html(body, template, merged_params)
        _send_email(to_email=to_email, subject=subject, body=body, html=html, to_name=to_name)
        return True
    except Exception:
        if raise_on_error:
            raise
        return False


def send_raw_email(to_email: str, subject: str, body: str, *, html: str | None = None) -> None:
    _send_email(to_email=to_email, subject=subject, body=body, html=html)


def smtp_public_config() -> dict[str, object]:
    config = smtp_config_row(include_secret=True)
    return {
        "host": config["host"],
        "port": config["port"],
        "secure": config["secure"],
        "username": config["username"],
        "mail_from": config["mail_from"],
        "password_set": bool(config["password_optional"]),
        "updated_at": config["updated_at"],
    }


def smtp_config_row(include_secret: bool = False) -> dict[str, object]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT host, port, secure, username, password_optional, mail_from, updated_at::text
                FROM smtp_runtime_config
                WHERE id = true
                """
            )
            config = cursor.fetchone()

    if config is None:
        raise ApiError("SMTP_CONFIG_MISSING", "SMTP configuration is not initialized.", 500)

    row = dict(config)
    if not include_secret:
        row.pop("password_optional", None)
    return row


def _default_params(params: dict[str, Any]) -> dict[str, Any]:
    current_year = datetime.now().year
    defaults = {
        "app_name": "Pratvim",
        "parent_first_name": "there",
        "support_email": SUPPORT_EMAIL,
        "current_year": current_year,
        "logo_url": LOGO_URL,
        "event_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cta_link": "",
    }
    return {**defaults, **params}


def _render(template: str, params: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).replace("params.", "").strip()
        value = params.get(key, "")
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)

    return re.sub(r"{{\s*([^}]+)\s*}}", replace, template)


def _email_html(body: str, template: dict[str, object], params: dict[str, Any]) -> str:
    paragraphs = "".join(
        f'<p style="margin:0 0 16px 0;font-size:16px;line-height:26px;color:#4D5658;">{escape(part).replace(chr(10), "<br />")}</p>'
        for part in body.split("\n\n")
        if part.strip()
    )
    cta_link = str(params.get("cta_link") or "")
    cta_label = str(template.get("cta_label") or "")
    cta = (
        f'<a href="{escape(cta_link)}" style="display:inline-block;background:#668F96;color:#FFFFFF;text-decoration:none;font-weight:700;font-size:15px;line-height:20px;padding:14px 22px;border-radius:999px;">{escape(cta_label)}</a>'
        if cta_link and cta_label
        else ""
    )
    return f"""<div style="margin:0;padding:0;background:#FBFAF5;font-family:Inter,Arial,sans-serif;color:#20292C;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FBFAF5;margin:0;padding:0;width:100%;">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFEFA;border:1px solid #E7E2D9;border-radius:16px;box-shadow:0 4px 12px rgba(52,58,55,0.08);overflow:hidden;">
        <tr><td style="padding:28px 28px 12px 28px;text-align:left;"><img src="{escape(str(params["logo_url"]))}" width="132" alt="Pratvim" style="display:block;border:0;outline:none;text-decoration:none;max-width:132px;height:auto;" /></td></tr>
        <tr><td style="padding:0 28px 8px 28px;"><div style="height:1px;background:#E7E2D9;line-height:1px;font-size:1px;">&nbsp;</div></td></tr>
        <tr><td style="padding:20px 28px 28px 28px;">{paragraphs}{cta}</td></tr>
        <tr><td style="padding:20px 28px 28px 28px;background:#EEF3F2;border-top:1px solid #E7E2D9;">
          <p style="margin:0 0 8px 0;font-size:13px;line-height:20px;color:#4D5658;">Pratvim is a protected AI learning space for children under parent or guardian supervision.</p>
          <p style="margin:0;font-size:12px;line-height:18px;color:#858B8C;">Need help? Contact <a href="mailto:{escape(str(params["support_email"]))}" style="color:#527B83;text-decoration:underline;">{escape(str(params["support_email"]))}</a>.<br />&copy; {escape(str(params["current_year"]))} Pratvim. All rights reserved.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>"""


def _smtp_login_if_configured(smtp: smtplib.SMTP, config: dict[str, object]) -> None:
    username = str(config["username"])
    password = str(config["password_optional"])
    if username or password:
        smtp.login(username, password)


def _send_email(to_email: str, subject: str, body: str, *, html: str | None = None, to_name: str | None = None) -> None:
    config = smtp_config_row(include_secret=True)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = str(config["mail_from"])
    message["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")

    if config["secure"]:
        with smtplib.SMTP_SSL(str(config["host"]), int(config["port"]), timeout=15) as smtp:
            _smtp_login_if_configured(smtp, config)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            _smtp_login_if_configured(smtp, config)
            smtp.send_message(message)
