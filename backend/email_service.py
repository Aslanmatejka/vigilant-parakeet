"""
Email service for DoGoods backend.

Sends password-reset and email-verification messages via SMTP.
Configure with the EMAIL_* environment variables. If they are absent,
emails are logged to stdout instead (useful for local development).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("email_service")

# SMTP config from environment — leave unset to use the console fallback.
SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
SMTP_PASS = os.getenv("EMAIL_SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "noreply@dogoods.app")


def _send(to: str, subject: str, html_body: str) -> None:
    """Send an e-mail; fall back to logging when SMTP is not configured."""
    if not SMTP_HOST or not SMTP_USER:
        logger.info("[Email fallback] To: %s | Subject: %s\n%s", to, subject, html_body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, [to], msg.as_string())
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        raise


def send_reset_email(to_email: str, reset_link: str) -> None:
    """Send a password-reset email with the given link."""
    subject = "Reset your DoGoods password"
    html_body = f"""
    <html><body>
      <h2>Password Reset</h2>
      <p>Click the link below to reset your DoGoods password. This link expires in 1 hour.</p>
      <p><a href="{reset_link}">{reset_link}</a></p>
      <p>If you did not request a password reset, you can safely ignore this email.</p>
    </body></html>
    """
    _send(to_email, subject, html_body)


def send_verification_email(to_email: str, verification_link: str) -> None:
    """Send an email-verification link to a newly registered user."""
    subject = "Verify your DoGoods email address"
    html_body = f"""
    <html><body>
      <h2>Verify your email</h2>
      <p>Thanks for joining DoGoods! Click the link below to verify your email address.</p>
      <p><a href="{verification_link}">{verification_link}</a></p>
    </body></html>
    """
    _send(to_email, subject, html_body)
