"""Regression coverage for architecture review finding S2: two near-identical
"build EmailMessage -> smtplib connect -> send" implementations (email_service.py,
external_form_notification_service.py) with diverging transport support --
email_service.py couldn't do implicit-TLS/port 465 at all. Both now share
smtp_client.send_smtp_message.
"""

from __future__ import annotations

from unittest.mock import patch

from m8flow_backend.services.smtp_client import send_smtp_message


def _kwargs(**overrides):
    base = dict(
        host="smtp.example.com",
        port=587,
        from_address="from@example.com",
        to_address="to@example.com",
        subject="Subject",
        text_body="text",
        html_body="<p>html</p>",
    )
    base.update(overrides)
    return base


def test_plaintext_uses_smtp_and_skips_starttls_and_login():
    with patch("m8flow_backend.services.smtp_client.smtplib.SMTP") as smtp_cls:
        client = smtp_cls.return_value.__enter__.return_value
        send_smtp_message(**_kwargs())

        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        client.starttls.assert_not_called()
        client.login.assert_not_called()
        client.send_message.assert_called_once()


def test_use_tls_calls_starttls_on_plain_smtp():
    with patch("m8flow_backend.services.smtp_client.smtplib.SMTP") as smtp_cls:
        client = smtp_cls.return_value.__enter__.return_value
        send_smtp_message(**_kwargs(use_tls=True))

        client.starttls.assert_called_once()


def test_use_ssl_connects_via_smtp_ssl_and_never_calls_starttls():
    with patch("m8flow_backend.services.smtp_client.smtplib.SMTP_SSL") as smtp_ssl_cls, \
         patch("m8flow_backend.services.smtp_client.smtplib.SMTP") as smtp_cls:
        client = smtp_ssl_cls.return_value.__enter__.return_value
        send_smtp_message(**_kwargs(use_ssl=True, use_tls=True, port=465))

        smtp_ssl_cls.assert_called_once_with("smtp.example.com", 465, timeout=30)
        smtp_cls.assert_not_called()
        client.starttls.assert_not_called()


def test_username_and_password_trigger_login():
    with patch("m8flow_backend.services.smtp_client.smtplib.SMTP") as smtp_cls:
        client = smtp_cls.return_value.__enter__.return_value
        send_smtp_message(**_kwargs(username="user", password="pw"))

        client.login.assert_called_once_with("user", "pw")


def test_missing_credentials_skip_login():
    with patch("m8flow_backend.services.smtp_client.smtplib.SMTP") as smtp_cls:
        client = smtp_cls.return_value.__enter__.return_value
        send_smtp_message(**_kwargs(username=None, password=None))

        client.login.assert_not_called()


def test_send_failure_propagates():
    with patch("m8flow_backend.services.smtp_client.smtplib.SMTP") as smtp_cls:
        client = smtp_cls.return_value.__enter__.return_value
        client.send_message.side_effect = ConnectionRefusedError("boom")

        try:
            send_smtp_message(**_kwargs())
            raised = False
        except ConnectionRefusedError:
            raised = True
        assert raised
