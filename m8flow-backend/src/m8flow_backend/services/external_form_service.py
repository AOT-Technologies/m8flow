from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import Any

from flask import g
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend.db import db
from m8flow_bpmn_core.models.user import UserModel

from m8flow_backend.config import external_form_link_ttl_seconds
from m8flow_backend.models.external_form_request import OPEN_STATUSES
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.models.external_form_request import truncate_last_error
from m8flow_backend.auth.bind import SUPER_ADMIN_DECISION_FLAG
from m8flow_backend.auth.tenant_context import get_context_tenant_id, set_context_tenant_id

LOGGER = logging.getLogger("m8flow.external_forms.service")

# Modeler-set extension property that marks a user task as external-form driven.
# Authored under `spiffworkflow:properties`, which lands in the serialized spec at
# json_metadata["task_definition_properties"]["extensions"]["properties"].
EXTERNAL_FORM_URL_PROPERTY = "externalFormUrl"


class ExternalFormService:
    """External-form request lifecycle and submission round-trip."""

    @staticmethod
    def generate_reference_id() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def _set_tenant_context(tenant_id: str) -> None:
        g.m8flow_tenant_id = tenant_id
        if get_context_tenant_id() != tenant_id:
            g._m8flow_ctx_token = set_context_tenant_id(tenant_id)

    @classmethod
    def create_requests_for_task(
        cls,
        *,
        tenant_id: str,
        process_instance_id: int,
        task_guid: str,
        external_form_url: str,
        recipients: list[dict[str, Any]],
        expires_at_in_seconds: int | None = None,
    ) -> list[ExternalFormRequestModel]:
        """Create one PENDING row per recipient ({user_id, email, user_details?}).
        Recipients already holding an actionable link are skipped, so event
        redelivery never issues duplicate links."""
        if expires_at_in_seconds is None:
            expires_at_in_seconds = int(time.time()) + external_form_link_ttl_seconds()

        existing_user_ids = {
            row.recipient_user_id
            for row in db.session.query(ExternalFormRequestModel).filter(
                ExternalFormRequestModel.process_instance_id == process_instance_id,
                ExternalFormRequestModel.task_guid == task_guid,
                # OPEN, not ACTIONABLE: a failed send or a row parked as
                # smtp_unconfigured is not submittable but is still this recipient's
                # live request. Narrowing this to ACTIONABLE would issue a second row
                # (and a second link) every time the producer re-runs for the instance.
                ExternalFormRequestModel.status.in_(OPEN_STATUSES),
            ).all()
        }

        created: list[ExternalFormRequestModel] = []
        for recipient in recipients:
            user_id = recipient["user_id"]
            if user_id in existing_user_ids:
                LOGGER.info(
                    "external-form: skipping duplicate request for user=%s task=%s instance=%s",
                    user_id,
                    task_guid,
                    process_instance_id,
                )
                continue
            row = ExternalFormRequestModel(
                m8f_tenant_id=tenant_id,
                reference_id=cls.generate_reference_id(),
                process_instance_id=process_instance_id,
                task_guid=task_guid,
                recipient_user_id=user_id,
                email=recipient["email"],
                user_details=recipient.get("user_details"),
                external_form_url=external_form_url,
                status=ExternalFormRequestStatus.pending.value,
                expires_at_in_seconds=expires_at_in_seconds,
                attempts=0,
            )
            db.session.add(row)
            created.append(row)

        try:
            db.session.commit()
        except Exception as exception:
            db.session.rollback()
            raise ApiError(
                error_code="database_error",
                message=f"Error saving external form requests: {str(exception)}",
                status_code=500,
            ) from exception
        return created

    @classmethod
    def _find_request_or_raise(cls, reference_id: str, for_update: bool = False) -> ExternalFormRequestModel:
        query = db.session.query(ExternalFormRequestModel).filter_by(reference_id=reference_id)
        if for_update:
            query = query.with_for_update()
        row = query.first()
        if row is None:
            LOGGER.warning("external-form: unknown reference_id presented")
            raise ApiError(
                error_code="invalid_reference_id",
                message="No external form request was found for this link.",
                status_code=404,
            )
        return row

    @classmethod
    def _expire_if_needed(cls, row: ExternalFormRequestModel) -> None:
        if (
            row.status in OPEN_STATUSES
            and row.expires_at_in_seconds is not None
            and row.expires_at_in_seconds < int(time.time())
        ):
            row.status = ExternalFormRequestStatus.expired.value
            db.session.commit()

    @classmethod
    def get_form_context(cls, reference_id: str) -> dict[str, Any]:
        """Context for the external mini-app: always 200 for a known link,
        with ``actionable`` telling the app whether to render the form or a message."""
        row = cls._find_request_or_raise(reference_id)
        cls._expire_if_needed(row)
        cls._set_tenant_context(row.m8f_tenant_id)

        context = row.to_public_dict()
        context["actionable"] = row.is_actionable()
        context["expires_at_in_seconds"] = row.expires_at_in_seconds

        try:
            from m8flow_bpmn_core.models.human_task import HumanTaskModel

            human_task = db.session.query(HumanTaskModel).filter_by(
                process_instance_id=row.process_instance_id, task_id=row.task_guid
            ).first()
            if human_task is not None:
                context["task_name"] = human_task.task_name
                context["task_title"] = human_task.task_title
                context["process_model_display_name"] = human_task.process_model_display_name
        except Exception:
            LOGGER.warning(
                "external-form: could not enrich context for instance=%s", row.process_instance_id, exc_info=True
            )

        return context

    @classmethod
    def _raise_for_unusable_status(cls, row: ExternalFormRequestModel) -> None:
        if row.status in (
            ExternalFormRequestStatus.submitted.value,
            ExternalFormRequestStatus.completed.value,
        ):
            raise ApiError(
                error_code="already_submitted",
                message="This form has already been submitted.",
                status_code=409,
            )
        if row.status == ExternalFormRequestStatus.superseded.value:
            raise ApiError(
                error_code="reference_superseded",
                message="This task was already completed through another recipient's link.",
                status_code=410,
            )
        if row.status == ExternalFormRequestStatus.expired.value:
            raise ApiError(
                error_code="reference_expired",
                message="This link has expired.",
                status_code=410,
            )
        if row.status == ExternalFormRequestStatus.smtp_unconfigured.value:
            # This request was never emailed, so no recipient can legitimately hold its
            # link -- presenting one means it was read out of the database. Refuse it
            # rather than let an operator submit the form as the recipient. The message
            # stays generic: this endpoint is unauthenticated and must not disclose the
            # tenant's mail configuration.
            LOGGER.warning(
                "external-form: refused a request parked as smtp_unconfigured"
                " (id=%s instance=%s task=%s); it was never delivered to its recipient.",
                row.id,
                row.process_instance_id,
                row.task_guid,
            )
            raise ApiError(
                error_code="reference_not_active",
                message="This link is not active.",
                status_code=409,
            )

    @classmethod
    def submit(cls, reference_id: str, form_data: dict[str, Any]) -> dict[str, Any]:
        """Validate the link, store the submission, and resume the workflow.
        First valid submission wins; repeats and late submits are rejected.

        Status update and human-task completion share one DB transaction so a
        crash mid-resume cannot leave the link consumed (``submitted``) while
        the workflow task is still open.
        """
        row = cls._find_request_or_raise(reference_id, for_update=True)
        cls._raise_for_unusable_status(row)
        cls._expire_if_needed(row)
        if row.status == ExternalFormRequestStatus.expired.value:
            cls._raise_for_unusable_status(row)

        # Hold the row lock through completion; do not commit ``submitted`` alone.
        row.status = ExternalFormRequestStatus.submitted.value
        row.form_submission_data = form_data

        cls._set_tenant_context(row.m8f_tenant_id)
        recipient = db.session.query(UserModel).filter_by(id=row.recipient_user_id).first()
        if recipient is None:
            cls._record_failure(row, "Recipient user no longer exists.")
            raise ApiError(
                error_code="recipient_not_found",
                message="The recipient for this link could not be resolved.",
                status_code=410,
            )
        g.user = recipient
        # Pin the super-admin answer for this request. `apply_postgres_rls` runs inside
        # SQLAlchemy's `after_begin` -- while the session is provisioning a connection --
        # and would otherwise read `g.user.groups`, re-entering the same session and
        # failing the whole submission with "This session is provisioning a new
        # connection; concurrent operations are not permitted". (A `rollback()` earlier in
        # the request expires the user row, so even a pre-warmed relationship reloads.)
        # False is also the correct answer: a link recipient acts within one tenant, so
        # this request must never run with RLS bypassed.
        setattr(g, SUPER_ADMIN_DECISION_FLAG, False)
        # Impersonate the recipient for this call so the shared human-task completion
        # path attributes the submission to them. There is no separate guard flag
        # enforcing exclusivity here: the row-level lock acquired in
        # _find_request_or_raise(for_update=True) plus the status checks in
        # _raise_for_unusable_status() reject repeat/late submissions on this link,
        # and a completion that already happened via another route (e.g. the in-app
        # task page) is caught below when submit_external_form maps InvalidStateError.
        g._m8flow_external_form_completion = True

        try:
            # Imported at call time so house patches that rebind this name are honored.
            from m8flow_backend.human_task import submit_external_form as _task_submit_shared

            from m8flow_bpmn_core.models.human_task import HumanTaskModel

            human_task_row = (
                db.session.query(HumanTaskModel)
                .filter_by(process_instance_id=row.process_instance_id, task_id=row.task_guid)
                .first()
            )
            if human_task_row is None:
                raise ApiError("not_found", "Human task not found for this form", 404)
            _task_submit_shared(
                db.session,
                tenant_id=row.m8f_tenant_id,
                human_task_id=human_task_row.id,
                user_id=recipient.id,
                task_payload=form_data,
            )
        except ApiError as api_error:
            if api_error.error_code == "invalid_state":
                # The underlying user task was already completed by another route
                # (e.g. the in-app task page). Nothing left to resume — mark the
                # request terminal and tell the recipient cleanly.
                db.session.rollback()
                row.status = ExternalFormRequestStatus.completed.value
                row.form_submission_data = form_data
                db.session.commit()
                LOGGER.info(
                    "external-form: task already completed via another route for task=%s instance=%s",
                    row.task_guid,
                    row.process_instance_id,
                )
                raise ApiError(
                    error_code="already_submitted",
                    message="This task has already been completed.",
                    status_code=409,
                ) from None
            cls._record_failure(row, f"{api_error.error_code}: {api_error.message}")
            raise
        except Exception as exception:
            cls._record_failure(row, str(exception))
            raise ApiError(
                error_code="workflow_resume_failed",
                message=f"The form was received but the workflow could not be resumed: {str(exception)}",
                status_code=500,
            ) from exception

        row.status = ExternalFormRequestStatus.completed.value
        superseded_count = cls._supersede_siblings(row)
        db.session.commit()
        LOGGER.info(
            "external-form: completed task=%s instance=%s recipient=%s superseded=%s",
            row.task_guid,
            row.process_instance_id,
            row.recipient_user_id,
            superseded_count,
        )
        return {
            "reference_id": row.reference_id,
            "status": row.status,
            "process_instance_id": row.process_instance_id,
        }

    @classmethod
    def _supersede_siblings(cls, row: ExternalFormRequestModel) -> int:
        siblings = db.session.query(ExternalFormRequestModel).filter(
            ExternalFormRequestModel.process_instance_id == row.process_instance_id,
            ExternalFormRequestModel.task_guid == row.task_guid,
            ExternalFormRequestModel.id != row.id,
            ExternalFormRequestModel.status.in_(OPEN_STATUSES),
        ).all()
        for sibling in siblings:
            sibling.status = ExternalFormRequestStatus.superseded.value
        return len(siblings)

    @classmethod
    def _record_failure(cls, row: ExternalFormRequestModel, error_message: str) -> None:
        """Mark a failed resume attempt but keep the link actionable for retry."""
        db.session.rollback()
        row.status = ExternalFormRequestStatus.failed.value
        row.attempts = (row.attempts or 0) + 1
        row.last_error = truncate_last_error(error_message)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            LOGGER.exception("external-form: could not record failure for reference row id=%s", row.id)
        LOGGER.error(
            "external-form: submission failed for task=%s instance=%s: %s",
            row.task_guid,
            row.process_instance_id,
            error_message,
        )

    # ------------------------------------------------------------------
    # Producer: ready external-form tasks -> tracking rows + NATS event
    # ------------------------------------------------------------------

    @classmethod
    def emit_requests_for_ready_tasks(
        cls, session: Session, *, tenant_id: str, process_instance_id: int
    ) -> None:
        """Create tracking rows and publish one notification event per ready
        external-form user task of an instance.

        Called right after a workflow write commits (``workflow.start`` /
        ``workflow.complete``). Best-effort by contract: the caller swallows
        exceptions so a notification-path failure can never break workflow
        execution, and ``create_requests_for_task`` is idempotent so the repeat
        calls an instance receives only ever publish when new rows appear.

        The externalFormUrl extension is read off the committed HumanTaskModel
        row (``json_metadata["task_definition_properties"]["extensions"]``), so
        this needs no workflow engine access.

        ponytail: covers the start and human-task-completion paths only. A task
        that becomes ready from a timer/message (scheduler ``run_due``) is not
        emitted -- hook it there too if that combination ships.
        """
        from m8flow_bpmn_core.models.human_task import HumanTaskModel

        ready_tasks = (
            session.query(HumanTaskModel)
            .filter_by(
                process_instance_id=process_instance_id,
                m8f_tenant_id=tenant_id,
                completed=False,
            )
            .all()
        )
        for human_task in ready_tasks:
            external_form_url = external_form_url_for_task(human_task)
            if not external_form_url:
                continue

            recipients, skipped = _recipients_for_task(human_task)
            if skipped:
                LOGGER.warning(
                    "external-form: task=%s instance=%s: no email for potential owner(s) %s; skipping them",
                    human_task.task_guid,
                    process_instance_id,
                    skipped,
                )
            if not recipients:
                LOGGER.warning(
                    "external-form: task=%s instance=%s has NO recipients with an email address --"
                    " nobody will be emailed. The task stays completable from the in-app task page.",
                    human_task.task_guid,
                    process_instance_id,
                )
                continue

            created = cls.create_requests_for_task(
                tenant_id=tenant_id,
                process_instance_id=process_instance_id,
                task_guid=human_task.task_guid,
                external_form_url=external_form_url,
                recipients=recipients,
            )
            if not created:
                continue

            try:
                _publish_requests_created(
                    session,
                    tenant_id=tenant_id,
                    process_instance_id=process_instance_id,
                    task_guid=human_task.task_guid,
                    created=created,
                )
            except Exception:
                LOGGER.warning(
                    "external-form: event publish failed for task=%s instance=%s;"
                    " the worker sweep will deliver the email(s)",
                    human_task.task_guid,
                    process_instance_id,
                    exc_info=True,
                )


def external_form_url_for_task(human_task: Any) -> str | None:
    """The task's modeler-set ``externalFormUrl`` extension property, if any."""
    metadata = human_task.json_metadata if isinstance(human_task.json_metadata, dict) else {}
    definition = metadata.get("task_definition_properties")
    extensions = (definition or {}).get("extensions") if isinstance(definition, dict) else None
    properties = (extensions or {}).get("properties") if isinstance(extensions, dict) else None
    url = (properties or {}).get(EXTERNAL_FORM_URL_PROPERTY) if isinstance(properties, dict) else None
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _recipients_for_task(human_task: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """(recipients, usernames skipped for want of an email) for a task's potential owners."""
    recipients: list[dict[str, Any]] = []
    skipped: list[str] = []
    for owner in human_task.potential_owners:
        email = (getattr(owner, "email", None) or "").strip()
        if not email:
            skipped.append(getattr(owner, "username", "?"))
            continue
        recipients.append(
            {
                "user_id": owner.id,
                "email": email,
                "user_details": {"username": getattr(owner, "username", None)},
            }
        )
    return recipients, skipped


def _publish_requests_created(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    task_guid: str,
    created: list[ExternalFormRequestModel],
) -> None:
    """Fast-path event so the worker emails immediately; the worker's periodic
    sweep is what delivers anything this publish misses."""
    from m8flow_backend.config import nats_enabled

    if not nats_enabled():
        LOGGER.info(
            "external-form: NATS disabled; %s request(s) for task=%s await the worker sweep",
            len(created),
            task_guid,
        )
        return

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.services.nats_service import NatsService

    tenant = session.get(M8flowTenantModel, tenant_id)
    if tenant is None or not tenant.slug:
        LOGGER.warning("external-form: no tenant slug for tenant=%s; skipping event publish", tenant_id)
        return

    NatsService.publish_notification(
        tenant.slug,
        {
            "id": str(uuid.uuid4()),
            "event_type": "external_form.requests_created",
            "tenant_id": tenant_id,
            "tenant_slug": tenant.slug,
            "process_instance_id": process_instance_id,
            "task_guid": task_guid,
            "reference_ids": [row.reference_id for row in created],
            "created_at_in_seconds": int(time.time()),
        },
    )
