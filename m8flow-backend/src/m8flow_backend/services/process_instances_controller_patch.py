from __future__ import annotations

import flask.wrappers
from flask import jsonify
from flask import make_response

_PATCHED = False


def _should_handle_process_run_api_error(error: Exception) -> bool:
    """Return False for expected validation errors that should not fault the instance."""
    return getattr(error, "error_code", None) != "task_lane_assignment_error"


def apply() -> None:
    """Patch process instance routes for BPMN snapshots and queued-start preflight.

    The frontend renders the diagram from `bpmn_xml_file_contents` embedded on the
    process instance payload. Upstream loads that XML from the current process
    model files (or git history if configured). In m8flow we force old instances
    to display the BPMN as executed by looking up the version snapshot referenced
    by bpmn_version_id on the process instance.
    """

    global _PATCHED
    if _PATCHED:
        return

    import importlib

    process_instances_controller = importlib.import_module(
        "spiffworkflow_backend.routes.process_instances_controller"
    )
    from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer import (
        queue_process_instance_if_appropriate,
    )
    from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer import (
        should_queue_process_instance,
    )
    from spiffworkflow_backend.exceptions.api_error import ApiError
    from spiffworkflow_backend.helpers.spiff_enum import ProcessInstanceExecutionMode
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.error_handling_service import ErrorHandlingService
    from spiffworkflow_backend.services.process_instance_queue_service import ProcessInstanceIsAlreadyLockedError
    from spiffworkflow_backend.services.process_instance_queue_service import ProcessInstanceIsNotEnqueuedError
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from spiffworkflow_backend.services.process_instance_tmp_service import ProcessInstanceTmpService
    import sqlalchemy as sa

    from m8flow_backend.services.process_instance_service_patch import _validate_queued_process_start

    original_get_process_instance = process_instances_controller._get_process_instance

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

        # Only override the top-level diagram; subprocess/call-activity diagrams can be requested
        # by providing process_identifier, which we do not snapshot today.
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
            # Legacy instance without a version reference — fall through to upstream.
            return response

        # Force the snapshot XML — do not fall back to the current model files.
        payload["bpmn_xml_file_contents"] = row[0]
        payload["bpmn_xml_file_contents_retrieval_error"] = None
        return make_response(jsonify(payload), response.status_code)

    def patched_process_instance_run(
        process_instance,
        force_run: bool = False,
        execution_mode: str | None = None,
    ) -> None:
        if process_instance.status != "not_started" and not force_run:
            raise ApiError(
                error_code="process_instance_not_runnable",
                message=f"Process Instance ({process_instance.id}) is currently running or has already run.",
                status_code=400,
            )

        processor = None
        try:
            if force_run is True:
                ProcessInstanceTmpService.add_event_to_process_instance(process_instance, "process_instance_force_run")

            if should_queue_process_instance(execution_mode=execution_mode):
                if not ProcessInstanceTmpService.is_enqueued_to_run_in_the_future(process_instance):
                    _validate_queued_process_start(process_instance, handle_error=False)
                queue_process_instance_if_appropriate(process_instance, execution_mode=execution_mode)
            elif not ProcessInstanceTmpService.is_enqueued_to_run_in_the_future(process_instance):
                execution_strategy_name = None
                if execution_mode == ProcessInstanceExecutionMode.synchronous.value:
                    execution_strategy_name = "greedy"
                processor, _ = ProcessInstanceService.run_process_instance_with_processor(
                    process_instance,
                    execution_strategy_name=execution_strategy_name,
                )
        except (
            ApiError,
            ProcessInstanceIsNotEnqueuedError,
            ProcessInstanceIsAlreadyLockedError,
        ) as error:
            if _should_handle_process_run_api_error(error):
                ErrorHandlingService.handle_error(process_instance, error)
            raise error
        except Exception as error:
            ErrorHandlingService.handle_error(process_instance, error)
            if processor is not None:
                task = processor.bpmn_process_instance.last_task
                raise ApiError.from_task(
                    error_code="unknown_exception",
                    message=f"An unknown error occurred. Original error: {error}",
                    status_code=400,
                    task=task,
                ) from error
            raise error

    process_instances_controller._get_process_instance = patched_get_process_instance
    process_instances_controller._process_instance_run = patched_process_instance_run
    _PATCHED = True
