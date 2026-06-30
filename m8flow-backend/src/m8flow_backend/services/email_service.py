"""Minimal outbound email sender for m8flow.

Driven entirely by env vars (see :func:`m8flow_backend.config.smtp_settings`). When no
SMTP host is configured the sender runs in *dev mode*: it logs the message instead of
sending it and reports ``sent=False`` so callers can surface the link another way
(e.g. return it in the API response for local testing).
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from m8flow_backend.config import smtp_settings

logger = logging.getLogger(__name__)


def smtp_is_configured() -> bool:
    """True when an SMTP host is configured (i.e. email can actually be sent)."""
    return bool(smtp_settings().get("host"))


def send_email(to_address: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """Send an email. Returns True if dispatched via SMTP, False in dev mode.

    Never raises on a missing SMTP configuration; a genuine SMTP failure is logged and
    re-raised so the caller can decide how to surface it.
    """
    settings = smtp_settings()
    host = settings.get("host")

    if not host:
        logger.warning(
            "email_service: SMTP not configured; dev mode. to=%s subject=%s\n%s",
            to_address,
            subject,
            text_body or html_body,
        )
        return False

    message = EmailMessage()
    message["From"] = settings["from_address"]
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(text_body or "Please view this message in an HTML-capable client.")
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, settings["port"], timeout=30) as server:
            if settings.get("use_tls"):
                server.starttls()
            if settings.get("username"):
                server.login(settings["username"], settings.get("password") or "")
            server.send_message(message)
    except Exception:
        logger.exception("email_service: failed to send email to %s", to_address)
        raise

    logger.info("email_service: sent email to %s subject=%s", to_address, subject)
    return True
