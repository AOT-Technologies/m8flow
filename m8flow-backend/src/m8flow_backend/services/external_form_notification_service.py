from __future__ import annotations

import html
import logging
import time
from datetime import datetime
from datetime import timezone
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from sqlalchemy import or_
from sqlalchemy import update as sa_update

from m8flow_backend.db import db

from m8flow_backend.config import notification_max_attempts
from m8flow_backend.config import notification_sweep_grace_seconds
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.models.external_form_request import truncate_last_error
from m8flow_backend.services.smtp_client import send_smtp_message

LOGGER = logging.getLogger("m8flow.external_forms.notification")

# Statuses a notification claim may transition from. Deliberately narrower than
# ACTIONABLE_STATUSES: 'notified' is excluded so a claim can never double-send.
CLAIMABLE_STATUSES = (
    ExternalFormRequestStatus.pending,
    ExternalFormRequestStatus.failed,
)

# SMTP is configured per-tenant via encrypted tenant secrets, never global
# env. These keys are read from the recipient's tenant when sending — host and
# from_email are required; the rest are optional.
#
# The NATS notification worker uses its OWN, NATS_-prefixed secrets so they stay
# independent of the plain SMTP_* secrets that the BPMN smtp/SendHTMLEmail connector
# reads. This lets the two email paths be configured separately.
SMTP_SECRET_KEYS = {
    "host": "NATS_SMTP_HOST",
    "port": "NATS_SMTP_PORT",
    "username": "NATS_SMTP_USERNAME",
    "password": "NATS_SMTP_PASSWORD",
    "from_email": "NATS_SMTP_FROM_EMAIL",
    "starttls": "NATS_SMTP_STARTTLS",
    "ssl": "NATS_SMTP_SSL",
}

# The minimum needed to send at all; resolve_smtp_settings() returns None without both.
# This must stay exactly the pair that function requires, or the status API would report
# "configured" for a tenant that still cannot send.
REQUIRED_SMTP_SECRET_KEYS = (SMTP_SECRET_KEYS["host"], SMTP_SECRET_KEYS["from_email"])
OPTIONAL_SMTP_SECRET_KEYS = tuple(key for key in SMTP_SECRET_KEYS.values() if key not in REQUIRED_SMTP_SECRET_KEYS)

_TRUTHY = {"1", "true", "yes", "on"}


def _is_truthy(value: str | None) -> bool:
    """Lenient boolean for tenant-set SMTP flags (true/1/yes/on, case-insensitive)."""
    return (value or "").strip().lower() in _TRUTHY


class ExternalFormNotificationService:
    """Email delivery for external-form secure links.

    The tracking row is the source of truth: a request is emailed exactly when an
    atomic claim flips it to 'notified' and stamps notified_at_in_seconds. A failed
    SMTP attempt reverts to 'failed' with notified_at cleared, so the periodic sweep
    retries it; a failed *resume* keeps notified_at set and is never
    re-emailed. Callers must hold a Flask app context with the row's tenant set."""

    @classmethod
    def claim(cls, request_id: int) -> bool:
        """Atomically claim a request for email delivery; True when this caller owns it."""
        now = int(time.time())
        result = db.session.execute(
            sa_update(ExternalFormRequestModel)
            .where(
                ExternalFormRequestModel.id == request_id,
                ExternalFormRequestModel.notified_at_in_seconds.is_(None),
                ExternalFormRequestModel.status.in_(CLAIMABLE_STATUSES),
            )
            .values(
                status=ExternalFormRequestStatus.notified,
                notified_at_in_seconds=now,
                attempts=ExternalFormRequestModel.attempts + 1,
                updated_at_in_seconds=now,
                # Clear any prior diagnosis; it describes an attempt that is now superseded.
                last_error=None,
            )
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
        return result.rowcount == 1

    @classmethod
    def release_failed(cls, request_id: int, error_message: str) -> None:
        """Revert a claim after a send failure so the sweep can retry. The status guard
        avoids clobbering a row the recipient managed to submit in the meantime."""
        now = int(time.time())
        db.session.execute(
            sa_update(ExternalFormRequestModel)
            .where(
                ExternalFormRequestModel.id == request_id,
                ExternalFormRequestModel.status == ExternalFormRequestStatus.notified,
            )
            .values(
                status=ExternalFormRequestStatus.failed,
                notified_at_in_seconds=None,
                updated_at_in_seconds=now,
                last_error=truncate_last_error(error_message),
            )
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
        LOGGER.warning(
            "external-form-notify: send failed for reference row id=%s (left retryable): %s",
            request_id,
            error_message,
        )

    @staticmethod
    def build_secure_link(row: ExternalFormRequestModel) -> str:
        """The recipient's secure link: the task's own externalFormUrl (set per-task in
        the modeler) with ref=<reference_id> appended, preserving any query
        params it already carries."""
        scheme, netloc, path, query, fragment = urlsplit(row.external_form_url)
        query_params = parse_qsl(query, keep_blank_values=True)
        query_params.append(("ref", row.reference_id))
        return urlunsplit((scheme, netloc, path, urlencode(query_params), fragment))

    @classmethod
    def render_email(cls, row: ExternalFormRequestModel, human_task: Any | None) -> tuple[str, str, str]:
        """Return (subject, text_body, html_body) for one recipient."""
        task_label = None
        process_label = None
        if human_task is not None:
            task_label = getattr(human_task, "task_title", None) or getattr(human_task, "task_name", None)
            process_label = getattr(human_task, "process_model_display_name", None)

        subject = "Action required: " + (task_label or "a task needs your input")
        if process_label:
            subject += f" — {process_label}"

        user_details = row.user_details or {}
        recipient_name = user_details.get("display_name") or user_details.get("username") or row.email
        link = cls.build_secure_link(row)

        context_sentence = "A workflow task is waiting for your input"
        if task_label and process_label:
            context_sentence = f'The task "{task_label}" in "{process_label}" is waiting for your input'
        elif task_label:
            context_sentence = f'The task "{task_label}" is waiting for your input'

        expiry_sentence = ""
        if row.expires_at_in_seconds:
            expires_on = datetime.fromtimestamp(row.expires_at_in_seconds, tz=timezone.utc)
            expiry_sentence = f"This link expires on {expires_on.strftime('%B %d, %Y at %H:%M UTC')}. "

        text_body = (
            f"Hello {recipient_name},\n\n"
            f"{context_sentence}.\n\n"
            f"Open the form: {link}\n\n"
            f"{expiry_sentence}This link is unique to you — please don't forward it.\n"
        )
        # Name, task/process labels, and URL are modeler- or identity-controlled —
        # escape them so they can't inject markup into the HTML part.
        safe_name = html.escape(str(recipient_name), quote=True)
        safe_context = html.escape(context_sentence, quote=True)
        safe_link = html.escape(link, quote=True)
        html_body = (
            '<div style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; margin: 0 auto;">'
            f"<p>Hello {safe_name},</p>"
            f"<p>{safe_context}.</p>"
            f'<p><a href="{safe_link}" style="display: inline-block; padding: 10px 24px;'
            ' background-color: #1a73e8; color: #ffffff; text-decoration: none;'
            ' border-radius: 4px;">Open the form</a></p>'
            f'<p style="font-size: 12px; color: #5f6368;">Or copy this link: {safe_link}</p>'
            f'<p style="font-size: 12px; color: #5f6368;">{expiry_sentence}'
            "This link is unique to you — please don&#39;t forward it.</p>"
            "</div>"
        )
        return subject, text_body, html_body

    @staticmethod
    def _effective_tenant_id(tenant_id: str | None = None) -> str | None:
        """The tenant a secret lookup should scope to, or None when there is none.

        An explicit `tenant_id` wins -- the admin endpoints inspect a tenant they are
        not "in", and a super-admin request carries no single ambient tenant. Otherwise
        the active tenant context, resolved through `get_tenant_id()` rather than `g`
        alone: the notification worker sets the tenant in the ContextVar with no request
        context, where a `g`-only read finds nothing and every send looks like
        `smtp_unconfigured`."""
        if tenant_id is not None:
            return tenant_id
        from m8flow_backend.auth.tenant_context import get_tenant_id

        try:
            return get_tenant_id(warn_on_default=False)
        except RuntimeError:
            # No active tenant at all -- treat as "not configured" so a misconfigured
            # caller leaves the request retryable rather than crashing the worker.
            return None

    @classmethod
    def _read_tenant_secret(cls, key: str, tenant_id: str | None = None) -> str | None:
        """Decrypted value of a tenant secret, or None if absent/unreadable."""
        from m8flow_backend.errors import ApiError
        from m8flow_backend import secrets as SecretService
        from m8flow_backend.db import current_session

        effective_tenant_id = cls._effective_tenant_id(tenant_id)
        if effective_tenant_id is None:
            return None
        try:
            secret = SecretService.get_secret_value(
                current_session(),
                tenant_id=effective_tenant_id,
                key=key,
            )
        except ApiError:
            return None
        if secret is None:
            return None
        value = secret.strip()
        return value or None

    @classmethod
    def resolve_smtp_settings(cls, tenant_id: str | None = None) -> dict[str, Any] | None:
        """Per-tenant SMTP config from the recipient tenant's encrypted secrets.

        Uses the active tenant context unless `tenant_id` names one. Returns None when
        the tenant has not configured SMTP (host and from_email are the minimum needed
        to send) -- REQUIRED_SMTP_SECRET_KEYS must stay exactly that pair."""
        host = cls._read_tenant_secret(SMTP_SECRET_KEYS["host"], tenant_id)
        from_email = cls._read_tenant_secret(SMTP_SECRET_KEYS["from_email"], tenant_id)
        if not host or not from_email:
            return None

        port_raw = cls._read_tenant_secret(SMTP_SECRET_KEYS["port"], tenant_id)
        try:
            port = int(port_raw) if port_raw else 587
        except ValueError:
            port = 587

        return {
            "host": host,
            "port": port,
            "username": cls._read_tenant_secret(SMTP_SECRET_KEYS["username"], tenant_id),
            "password": cls._read_tenant_secret(SMTP_SECRET_KEYS["password"], tenant_id),
            "from_email": from_email,
            "starttls": _is_truthy(cls._read_tenant_secret(SMTP_SECRET_KEYS["starttls"], tenant_id)),
            "ssl": _is_truthy(cls._read_tenant_secret(SMTP_SECRET_KEYS["ssl"], tenant_id)),
        }

    @classmethod
    def _present_smtp_secret_keys(cls, tenant_id: str | None = None) -> set[str]:
        """Which NATS_SMTP_* keys the tenant has rows for. Presence only, no decryption,
        so it stays a single query."""
        from m8flow_backend.db import current_session
        from m8flow_backend.secrets import list_secret_keys

        effective_tenant_id = cls._effective_tenant_id(tenant_id)
        if effective_tenant_id is None:
            # `list_secret_keys(tenant_id=None)` spans every tenant; reporting another
            # tenant's keys as this one's is worse than reporting none.
            return set()
        keys = set(list_secret_keys(current_session(), tenant_id=effective_tenant_id))
        return keys & set(SMTP_SECRET_KEYS.values())

    @classmethod
    def smtp_readiness(cls, tenant_id: str | None = None) -> dict[str, Any]:
        """Whether the tenant can send, and why not when it cannot.

        Separates a key that was never set from one whose row exists but does not resolve
        to a usable value (blank, or undecryptable because the backend encryption key
        changed). Both block sending but need completely different fixes, so the reason an
        admin reads must not collapse them into "missing"."""
        missing: list[str] = []
        unreadable: list[str] = []
        present = cls._present_smtp_secret_keys(tenant_id)
        for key in REQUIRED_SMTP_SECRET_KEYS:
            if cls._read_tenant_secret(key, tenant_id):
                continue
            (unreadable if key in present else missing).append(key)

        if unreadable:
            reason = (
                "SMTP secrets exist but could not be read (blank value, or the backend"
                " encryption key changed): " + ", ".join(unreadable)
            )
        elif missing:
            reason = "SMTP is not configured for this tenant. Missing required secrets: " + ", ".join(missing)
        else:
            reason = None
        return {
            "missing": missing,
            "unreadable": unreadable,
            "unusable": missing + unreadable,
            "reason": reason,
            "ok": reason is None,
        }

    @classmethod
    def smtp_configuration_status(cls, tenant_id: str | None = None) -> dict[str, Any]:
        """Whether the tenant can send external-form emails, and which secret keys it
        still needs. Returns key *names* only -- never a secret value.

        ``configured_keys`` lists keys that resolve to a usable (decryptable, non-blank)
        value, including optional ones. Presence of a row alone is not enough."""
        readiness = cls.smtp_readiness(tenant_id)
        present_keys = cls._present_smtp_secret_keys(tenant_id)
        configured_keys = sorted(key for key in present_keys if cls._read_tenant_secret(key, tenant_id))
        return {
            "configured": readiness["ok"],
            "required_keys": list(REQUIRED_SMTP_SECRET_KEYS),
            "optional_keys": list(OPTIONAL_SMTP_SECRET_KEYS),
            "missing_required_keys": readiness["unusable"],
            "unreadable_keys": readiness["unreadable"],
            "reason": readiness["reason"],
            "configured_keys": configured_keys,
        }

    @classmethod
    def mark_smtp_unconfigured(cls, request_ids: list[int], reason: str) -> int:
        """Park requests that cannot be emailed because the tenant has no usable SMTP config.

        'smtp_unconfigured' is outside CLAIMABLE_STATUSES, so the sweep stops considering
        these rows entirely -- this is what ends the indefinite retry loop. The status
        guard mirrors release_failed(): a row the recipient just submitted, or one another
        worker already claimed, is left alone."""
        if not request_ids:
            return 0
        now = int(time.time())
        result = db.session.execute(
            sa_update(ExternalFormRequestModel)
            .where(
                ExternalFormRequestModel.id.in_(request_ids),
                ExternalFormRequestModel.notified_at_in_seconds.is_(None),
                ExternalFormRequestModel.status.in_(CLAIMABLE_STATUSES),
            )
            .values(
                status=ExternalFormRequestStatus.smtp_unconfigured.value,
                updated_at_in_seconds=now,
                last_error=truncate_last_error(reason),
            )
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
        return result.rowcount

    @classmethod
    def revive_smtp_unconfigured(cls, tenant_id: str) -> int:
        """Return every parked request of one tenant to the retry queue.

        Called by the worker's sweep once the tenant's SMTP secrets appear. attempts is
        reset because the parked attempts were never real delivery attempts -- they
        burned no SMTP connection. `tenant_id` is mandatory: unscoped, this statement
        would revive parked rows across every tenant. Reviving one specific row is
        `requeue`."""
        now = int(time.time())
        result = db.session.execute(
            sa_update(ExternalFormRequestModel)
            .where(
                ExternalFormRequestModel.status == ExternalFormRequestStatus.smtp_unconfigured.value,
                ExternalFormRequestModel.m8f_tenant_id == tenant_id,
            )
            .values(
                status=ExternalFormRequestStatus.pending.value,
                notified_at_in_seconds=None,
                attempts=0,
                updated_at_in_seconds=now,
                last_error=None,
            )
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
        return result.rowcount

    # Statuses an admin may resend from: parked for missing SMTP, awaiting delivery, or
    # failed with the claim released (notified_at cleared). A 'failed' row that still has
    # notified_at set is a failed workflow *resume*, not a failed send -- re-emailing it is
    # wrong, which the notified_at guard in requeue() enforces.
    RESENDABLE_STATUSES = (
        ExternalFormRequestStatus.smtp_unconfigured.value,
        ExternalFormRequestStatus.failed.value,
        ExternalFormRequestStatus.pending.value,
    )

    @classmethod
    def requeue(cls, request_id: int, tenant_id: str | None = None) -> bool:
        """Admin resend: put one request back at the front of the retry queue.

        True when the row moved. False when it is not in a resendable state (already
        submitted/completed/superseded/expired, or a failed resume rather than a failed
        send), which the caller reports as a conflict.

        ``tenant_id`` pins the update to one tenant: a bare numeric id would otherwise
        reach any tenant's row."""
        now = int(time.time())
        statement = (
            sa_update(ExternalFormRequestModel)
            .where(
                ExternalFormRequestModel.id == request_id,
                ExternalFormRequestModel.status.in_(cls.RESENDABLE_STATUSES),
                ExternalFormRequestModel.notified_at_in_seconds.is_(None),
            )
            .values(
                status=ExternalFormRequestStatus.pending.value,
                attempts=0,
                updated_at_in_seconds=now,
                last_error=None,
            )
            .execution_options(synchronize_session=False)
        )
        if tenant_id is not None:
            statement = statement.where(ExternalFormRequestModel.m8f_tenant_id == tenant_id)
        result = db.session.execute(statement)
        db.session.commit()
        return result.rowcount == 1

    @classmethod
    def tenants_with_parked_requests(cls) -> list[str]:
        """Tenant ids holding requests parked as smtp_unconfigured. Runs cross-tenant --
        call without tenant context, like sweep_candidates()."""
        rows = (
            db.session.query(ExternalFormRequestModel.m8f_tenant_id)
            .filter(ExternalFormRequestModel.status == ExternalFormRequestStatus.smtp_unconfigured.value)
            .distinct()
            .all()
        )
        return [row.m8f_tenant_id for row in rows]

    @staticmethod
    def send_email(settings: dict[str, Any], to_email: str, subject: str, text_body: str, html_body: str) -> None:
        # Surfaces the negotiated transport so a "Connection unexpectedly closed" (plaintext
        # hitting an implicit-TLS port) vs auth issue is obvious from the logs. No secrets logged.
        LOGGER.info(
            "external-form-notify: connecting host=%s port=%s ssl=%s starttls=%s auth=%s",
            settings["host"],
            settings["port"],
            settings["ssl"],
            settings["starttls"],
            bool(settings["username"] and settings["password"]),
        )
        send_smtp_message(
            host=settings["host"],
            port=settings["port"],
            from_address=settings["from_email"],
            to_address=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            use_ssl=settings["ssl"],
            use_tls=settings["starttls"],
            username=settings["username"],
            password=settings["password"],
        )

    @classmethod
    def notify(cls, reference_id: str) -> str:
        """Claim and email one request; returns a status string for logging.
        Safe to call repeatedly and concurrently — the claim makes it idempotent."""
        row = db.session.query(ExternalFormRequestModel).filter_by(reference_id=reference_id).first()
        if row is None:
            LOGGER.warning("external-form-notify: unknown reference_id presented")
            return "skipped:unknown_reference"
        smtp_settings = cls.resolve_smtp_settings()
        if smtp_settings is None:
            # Retrying cannot help until an admin fixes the configuration, so park the row
            # in a terminal status rather than leaving it pending for the sweep to re-pick
            # forever. revive_smtp_unconfigured() brings it back once SMTP is usable.
            readiness = cls.smtp_readiness()
            reason = readiness["reason"] or "SMTP configuration could not be resolved for this tenant."
            cls.mark_smtp_unconfigured([row.id], reason)
            LOGGER.error(
                "external-form-notify: cannot send for tenant=%s; parking request id=%s"
                " instance=%s task=%s recipient_user_id=%s as smtp_unconfigured. %s",
                row.m8f_tenant_id,
                row.id,
                row.process_instance_id,
                row.task_guid,
                row.recipient_user_id,
                reason,
            )
            return "skipped:smtp_unconfigured"
        now = int(time.time())
        if row.expires_at_in_seconds is not None and row.expires_at_in_seconds < now:
            return "skipped:expired"
        # The externalFormUrl extension is modeler-controlled; refuse to email anything
        # but a web link (blocks javascript:/data: schemes in the href).
        link_scheme = urlsplit(cls.build_secure_link(row)).scheme.lower()
        if link_scheme not in ("http", "https"):
            LOGGER.error(
                "external-form-notify: refusing to email link with scheme '%s' for task=%s instance=%s",
                link_scheme or "(none)",
                row.task_guid,
                row.process_instance_id,
            )
            if cls.claim(row.id):
                cls.release_failed(row.id, f"external form link scheme '{link_scheme}' is not http/https")
            return "skipped:unsafe_url"
        if not cls.claim(row.id):
            return "skipped:not_claimable"
        db.session.refresh(row)

        human_task = None
        try:
            from m8flow_bpmn_core.models.human_task import HumanTaskModel

            human_task = db.session.query(HumanTaskModel).filter_by(
                process_instance_id=row.process_instance_id, task_id=row.task_guid
            ).first()
        except Exception:
            LOGGER.warning(
                "external-form-notify: could not enrich email for instance=%s", row.process_instance_id, exc_info=True
            )

        subject, text_body, html_body = cls.render_email(row, human_task)
        try:
            cls.send_email(smtp_settings, row.email, subject, text_body, html_body)
        except Exception as exception:
            db.session.rollback()
            cls.release_failed(row.id, str(exception))
            LOGGER.error(
                "external-form-notify: send failed for task=%s instance=%s attempt=%s: %s",
                row.task_guid,
                row.process_instance_id,
                row.attempts,
                exception,
            )
            return f"failed:{exception}"

        LOGGER.info(
            "external-form-notify: sent task=%s instance=%s recipient=%s",
            row.task_guid,
            row.process_instance_id,
            row.recipient_user_id,
        )
        return "sent"

    @classmethod
    def sweep_candidates(cls, now: int | None = None) -> list[tuple[int, str, str]]:
        """(id, reference_id, m8f_tenant_id) of requests still owed an email: never
        claimed, not exhausted, not expired, and old enough that the event fast-path
        had its chance. Runs cross-tenant — call without tenant context."""
        if now is None:
            now = int(time.time())
        cutoff = now - notification_sweep_grace_seconds()
        rows = (
            db.session.query(
                ExternalFormRequestModel.id,
                ExternalFormRequestModel.reference_id,
                ExternalFormRequestModel.m8f_tenant_id,
            )
            .filter(
                ExternalFormRequestModel.notified_at_in_seconds.is_(None),
                ExternalFormRequestModel.status.in_(CLAIMABLE_STATUSES),
                ExternalFormRequestModel.attempts < notification_max_attempts(),
                ExternalFormRequestModel.created_at_in_seconds < cutoff,
                or_(
                    ExternalFormRequestModel.expires_at_in_seconds.is_(None),
                    ExternalFormRequestModel.expires_at_in_seconds > now,
                ),
            )
            .order_by(ExternalFormRequestModel.created_at_in_seconds)
            .all()
        )
        return [(row.id, row.reference_id, row.m8f_tenant_id) for row in rows]
