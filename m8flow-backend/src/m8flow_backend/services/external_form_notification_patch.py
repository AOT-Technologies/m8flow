from __future__ import annotations

import logging
import time
import uuid

_PATCHED = False
_logger = logging.getLogger("m8flow.external_forms.notification_hook")


def _recipient_email(user) -> str | None:
    """Email for a potential owner. When the owner row has none (e.g. a backend-signed
    mirror user — duplicate row whose service is the backend's own JWT issuer), fall
    back to a same-username sibling row in the tenant that does carry an email."""
    email = (getattr(user, "email", None) or "").strip()
    if email:
        return email
    try:
        from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username

        for sibling in find_users_for_current_tenant_by_username(user.username):
            sibling_email = (getattr(sibling, "email", None) or "").strip()
            if sibling_email:
                return sibling_email
    except Exception:
        _logger.warning(
            "external-form-notify: sibling email lookup failed for user id=%s",
            getattr(user, "id", None),
            exc_info=True,
        )
    return None


def _publish_requests_created_event(tenant_id: str, process_instance_id: int, task_guid: str, created) -> None:
    """Best-effort fast-path event; the worker's periodic sweep delivers anything missed."""
    from m8flow_backend.config import nats_enabled

    if not nats_enabled():
        _logger.info(
            "external-form-notify: NATS disabled; %s request(s) for task=%s await the worker sweep",
            len(created),
            task_guid,
        )
        return

    from spiffworkflow_backend.models.db import db

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.services.nats_service import NatsService

    tenant = db.session.get(M8flowTenantModel, tenant_id)
    if tenant is None or not tenant.slug:
        _logger.warning("external-form-notify: no tenant slug for tenant=%s; skipping event publish", tenant_id)
        return

    payload = {
        "id": str(uuid.uuid4()),
        "event_type": "external_form.requests_created",
        "tenant_id": tenant_id,
        "tenant_slug": tenant.slug,
        "process_instance_id": process_instance_id,
        "task_guid": task_guid,
        "reference_ids": [row.reference_id for row in created],
        "created_at_in_seconds": int(time.time()),
    }
    NatsService.publish_notification(tenant.slug, payload)


def _find_ready_human_task(process_instance_id: int, task_guid: str):
    """The committed HumanTaskModel row for a ready task, with its potential owners."""
    from spiffworkflow_backend.models.human_task import HumanTaskModel

    return HumanTaskModel.query.filter_by(
        process_instance_id=process_instance_id, task_id=task_guid, completed=False
    ).first()


def _emit_external_form_requests(processor) -> None:
    """Create per-recipient tracking rows for ready external-form user tasks and publish
    one notification event per task. Runs after save() committed, in both the
    API process and the celery worker. create_requests_for_task is idempotent, so the
    repeated save() calls per instance only ever publish when new rows appear."""
    from m8flow_backend.services.external_form_service import ExternalFormService
    from m8flow_backend.tenancy import reset_context_tenant_id
    from m8flow_backend.tenancy import set_context_tenant_id

    external_form_tasks = []
    for spiff_task in processor.get_all_ready_or_waiting_tasks():
        task_spec = spiff_task.task_spec
        if not getattr(task_spec, "manual", False):
            continue
        properties = (getattr(task_spec, "extensions", None) or {}).get("properties", {})
        external_form_url = properties.get("externalFormUrl")
        if external_form_url:
            external_form_tasks.append((spiff_task, external_form_url))

    if not external_form_tasks:
        return

    process_instance = processor.process_instance_model
    tenant_id = getattr(process_instance, "m8f_tenant_id", None)
    if not tenant_id:
        _logger.warning(
            "external-form-notify: process instance %s has no tenant; cannot create requests",
            getattr(process_instance, "id", None),
        )
        return

    token = set_context_tenant_id(tenant_id)
    try:
        for spiff_task, external_form_url in external_form_tasks:
            task_guid = str(spiff_task.id)
            human_task = _find_ready_human_task(process_instance.id, task_guid)
            if human_task is None:
                continue

            recipients = []
            skipped_usernames = []
            for owner in human_task.potential_owners:
                owner_email = _recipient_email(owner)
                if owner_email is None:
                    skipped_usernames.append(getattr(owner, "username", "?"))
                    continue
                recipients.append(
                    {
                        "user_id": owner.id,
                        "email": owner_email,
                        "user_details": {"username": getattr(owner, "username", None)},
                    }
                )

            if skipped_usernames:
                _logger.warning(
                    "external-form-notify: task=%s instance=%s: no email for potential owner(s) %s; skipping them",
                    task_guid,
                    process_instance.id,
                    skipped_usernames,
                )
            if not recipients:
                _logger.warning(
                    "external-form-notify: task=%s instance=%s has NO recipients with an email address —"
                    " nobody will be emailed. The task stays completable from the in-app task page.",
                    task_guid,
                    process_instance.id,
                )
                continue

            created = ExternalFormService.create_requests_for_task(
                tenant_id=tenant_id,
                process_instance_id=process_instance.id,
                task_guid=task_guid,
                external_form_url=external_form_url,
                recipients=recipients,
            )
            if not created:
                continue

            try:
                _publish_requests_created_event(tenant_id, process_instance.id, task_guid, created)
            except Exception:
                _logger.warning(
                    "external-form-notify: event publish failed for task=%s instance=%s;"
                    " the worker sweep will deliver the email(s)",
                    task_guid,
                    process_instance.id,
                    exc_info=True,
                )
    finally:
        reset_context_tenant_id(token)


def apply() -> None:
    """Wrap ProcessInstanceProcessor.save() so reaching a user task that carries the
    externalFormUrl extension creates tracking rows and publishes a NATS
    notification event. The hook runs after the original save() committed,
    and never lets a notification-path error break workflow execution."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor

    original_save = ProcessInstanceProcessor.save

    def patched_save(self, *args, **kwargs):
        result = original_save(self, *args, **kwargs)
        try:
            _emit_external_form_requests(self)
        except Exception:
            _logger.warning(
                "external-form-notify: notification hook failed for process instance %s",
                getattr(getattr(self, "process_instance_model", None), "id", None),
                exc_info=True,
            )
        return result

    ProcessInstanceProcessor.save = patched_save
    _PATCHED = True
