from __future__ import annotations

import flask.wrappers
from flask import jsonify
from flask import make_response

_PATCHED = False


def _should_handle_process_run_api_error(error: Exception) -> bool:
    """Return False for expected validation errors that should not fault the instance."""
    return getattr(error, "error_code", None) != "task_lane_assignment_error"


def apply() -> None:
    """Serve BPMN version snapshots on get; preflight queued starts before enqueue."""

    global _PATCHED
    if _PATCHED:
        return

    import importlib

    process_instances_controller = importlib.import_module(
        "spiffworkflow_backend.routes.process_instances_controller"
    )
    from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer import (
        should_queue_process_instance,
    )
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.process_instance_tmp_service import ProcessInstanceTmpService
    import sqlalchemy as sa

    from m8flow_backend.services.process_instance_service_patch import _validate_queued_process_start

    original_get_process_instance = process_instances_controller._get_process_instance
    original_process_instance_run = getattr(
        process_instances_controller, "_process_instance_run", None
    )
    original_queue_process_instance_if_appropriate = getattr(
        process_instances_controller, "queue_process_instance_if_appropriate", None
    )
    original_error_handling_service = getattr(
        process_instances_controller, "ErrorHandlingService", None
    )
    can_wrap_process_instance_run = (
        callable(original_process_instance_run)
        and callable(original_queue_process_instance_if_appropriate)
        and original_error_handling_service is not None
    )

    def patched_get_process_instance(
        modified_process_model_identifier: str,
        process_instance,
        process_identifier: str | None = None,
    ) -> flask.wrappers.Response:
        response = original_get_process_instance(
            modified_process_model_identifier,
            process_instance,
            process_identifier=process_identifier,
        )

        # Subprocess/call-activity diagrams (process_identifier set) are not snapshotted.
        if process_identifier:
            return response

        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            return response

        process_instance_id = payload.get("id")
        if not isinstance(process_instance_id, int):
            return response

        tenant_id = getattr(process_instance, "m8f_tenant_id", None)
        if not tenant_id:
            return response

        row = db.session.execute(
            sa.text(
                """
                SELECT v.bpmn_xml_file_contents
                FROM process_model_bpmn_version v
                JOIN process_instance pi ON pi.bpmn_version_id = v.id
                WHERE pi.id = :process_instance_id
                  AND v.m8f_tenant_id = :m8f_tenant_id
                LIMIT 1
                """
            ),
            {"m8f_tenant_id": tenant_id, "process_instance_id": process_instance_id},
        ).first()

        if row is None:
            return response

        payload["bpmn_xml_file_contents"] = row[0]
        payload["bpmn_xml_file_contents_retrieval_error"] = None
        return make_response(jsonify(payload), response.status_code)

    process_instances_controller._get_process_instance = patched_get_process_instance

    if can_wrap_process_instance_run:

        def queue_with_queued_start_preflight(
            process_instance,
            execution_mode: str | None = None,
            task_guid: str | None = None,
        ) -> bool:
            # Fail lane assignment before enqueue; the worker would otherwise surface it later.
            if should_queue_process_instance(execution_mode=execution_mode):
                if not ProcessInstanceTmpService.is_enqueued_to_run_in_the_future(process_instance):
                    _validate_queued_process_start(process_instance, handle_error=False)
            return original_queue_process_instance_if_appropriate(
                process_instance,
                execution_mode=execution_mode,
                task_guid=task_guid,
            )

        class _RunErrorHandlingProxy:
            """ErrorHandlingService proxy that skips faulting on lane-assignment ApiErrors."""

            def __getattr__(self, name: str):
                return getattr(original_error_handling_service, name)

            @staticmethod
            def handle_error(process_instance, error) -> None:
                if not _should_handle_process_run_api_error(error):
                    return None
                return original_error_handling_service.handle_error(process_instance, error)

        def patched_process_instance_run(
            process_instance,
            force_run: bool = False,
            execution_mode: str | None = None,
        ) -> None:
            process_instances_controller.queue_process_instance_if_appropriate = (
                queue_with_queued_start_preflight
            )
            process_instances_controller.ErrorHandlingService = _RunErrorHandlingProxy()
            try:
                return original_process_instance_run(
                    process_instance,
                    force_run=force_run,
                    execution_mode=execution_mode,
                )
            finally:
                process_instances_controller.queue_process_instance_if_appropriate = (
                    original_queue_process_instance_if_appropriate
                )
                process_instances_controller.ErrorHandlingService = original_error_handling_service

        process_instances_controller._process_instance_run = patched_process_instance_run

    _PATCHED = True
