"""Minimal outbound email sender for m8flow.

Driven entirely by env vars (see :func:`m8flow_backend.config.smtp_settings`). When no
SMTP host is configured the sender runs in *dev mode*: it logs the message instead of
sending it and reports ``sent=False`` so callers can surface the link another way
(e.g. return it in the API response for local testing).
"""
from __future__ import annotations

import logging

from m8flow_backend.config import smtp_settings
from m8flow_backend.services.smtp_client import send_smtp_message

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

    try:
        send_smtp_message(
            host=host,
            port=settings["port"],
            from_address=settings["from_address"],
            to_address=to_address,
            subject=subject,
            text_body=text_body or "Please view this message in an HTML-capable client.",
            html_body=html_body,
            use_tls=bool(settings.get("use_tls")),
            username=settings.get("username"),
            password=settings.get("password"),
        )
    except Exception:
        logger.exception("email_service: failed to send email to %s", to_address)
        raise

    logger.info("email_service: sent email to %s subject=%s", to_address, subject)
    return True
