from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from flask import g

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel

from m8flow_backend.config import external_form_link_ttl_seconds
from m8flow_backend.models.external_form_request import ACTIONABLE_STATUSES
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.tenancy import get_context_tenant_id, set_context_tenant_id

LOGGER = logging.getLogger("m8flow.external_forms.service")


class ExternalFormService:
    """External-form request lifecycle and submission round-trip (M8F-338)."""

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
        redelivery (M8F-339) never issues duplicate links."""
        if expires_at_in_seconds is None:
            expires_at_in_seconds = int(time.time()) + external_form_link_ttl_seconds()

        existing_user_ids = {
            row.recipient_user_id
            for row in ExternalFormRequestModel.query.filter(
                ExternalFormRequestModel.process_instance_id == process_instance_id,
                ExternalFormRequestModel.task_guid == task_guid,
                ExternalFormRequestModel.status.in_(ACTIONABLE_STATUSES),
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
        query = ExternalFormRequestModel.query.filter_by(reference_id=reference_id)
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
            row.status in ACTIONABLE_STATUSES
            and row.expires_at_in_seconds is not None
            and row.expires_at_in_seconds < int(time.time())
        ):
            row.status = ExternalFormRequestStatus.expired.value
            db.session.commit()

    @classmethod
    def get_form_context(cls, reference_id: str) -> dict[str, Any]:
        """Context for the external mini-app (M8F-340): always 200 for a known link,
        with ``actionable`` telling the app whether to render the form or a message."""
        row = cls._find_request_or_raise(reference_id)
        cls._expire_if_needed(row)
        cls._set_tenant_context(row.m8f_tenant_id)

        context = row.to_public_dict()
        context["actionable"] = row.is_actionable()
        context["expires_at_in_seconds"] = row.expires_at_in_seconds

        try:
            from spiffworkflow_backend.models.human_task import HumanTaskModel

            human_task = HumanTaskModel.query.filter_by(
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

    @classmethod
    def submit(cls, reference_id: str, form_data: dict[str, Any]) -> dict[str, Any]:
        """Validate the link, store the submission, and resume the workflow.
        First valid submission wins; repeats and late submits are rejected."""
        row = cls._find_request_or_raise(reference_id, for_update=True)
        cls._raise_for_unusable_status(row)
        cls._expire_if_needed(row)
        if row.status == ExternalFormRequestStatus.expired.value:
            cls._raise_for_unusable_status(row)

        row.status = ExternalFormRequestStatus.submitted.value
        row.form_submission_data = form_data
        db.session.commit()

        cls._set_tenant_context(row.m8f_tenant_id)
        recipient = UserModel.query.filter_by(id=row.recipient_user_id).first()
        if recipient is None:
            cls._record_failure(row, "Recipient user no longer exists.")
            raise ApiError(
                error_code="recipient_not_found",
                message="The recipient for this link could not be resolved.",
                status_code=410,
            )
        g.user = recipient

        try:
            # Imported at call time so house patches that rebind this name are honored.
            from spiffworkflow_backend.routes.process_api_blueprint import _task_submit_shared

            _task_submit_shared(row.process_instance_id, row.task_guid, form_data)
        except ApiError as api_error:
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
        siblings = ExternalFormRequestModel.query.filter(
            ExternalFormRequestModel.process_instance_id == row.process_instance_id,
            ExternalFormRequestModel.task_guid == row.task_guid,
            ExternalFormRequestModel.id != row.id,
            ExternalFormRequestModel.status.in_(ACTIONABLE_STATUSES),
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
        row.last_error = error_message[:4000]
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
