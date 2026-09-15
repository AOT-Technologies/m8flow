"""Low-level SMTP send. The one place "connect and send an email" logic
lives -- config resolution (env-based global settings vs. per-tenant
encrypted secrets) stays with each caller, since those are deliberately
independent (see external_form_notification_service.py's SMTP_SECRET_KEYS
docstring); only the send mechanics were duplicated. See architecture
review finding S2.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_smtp_message(
    *,
    host: str,
    port: int,
    from_address: str,
    to_address: str,
    subject: str,
    text_body: str,
    html_body: str,
    use_ssl: bool = False,
    use_tls: bool = False,
    username: str | None = None,
    password: str | None = None,
    timeout: int = 30,
) -> None:
    """Build and send one HTML+text email over SMTP: implicit TLS (use_ssl,
    e.g. port 465), STARTTLS (use_tls), or plaintext, with optional auth.
    Raises on any failure (bad connection, auth, etc.) -- callers decide how
    to log/map/surface it; nothing here swallows an error.

    email_service.py's inline copy of this logic couldn't do implicit-TLS at
    all before this -- only external_form_notification_service.py's could.
    """
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(host, port, timeout=timeout) as client:
        if use_tls and not use_ssl:
            client.starttls()
        if username and password:
            client.login(username, password)
        client.send_message(message)
