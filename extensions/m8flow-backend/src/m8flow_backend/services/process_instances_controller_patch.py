from __future__ import annotations

import flask.wrappers
from flask import jsonify
from flask import make_response

_PATCHED = False


def apply() -> None:
    """Patch process instance show to prefer stored BPMN snapshots.

    The frontend renders the diagram from `bpmn_xml_file_contents` embedded on the
    process instance payload. Upstream loads that XML from the current process
    model files (or git history if configured). In m8flow we want old instances
    to display the BPMN as executed, so we use a per-instance snapshot when available.
    """

    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.routes import process_instances_controller
    from spiffworkflow_backend.models.db import db
    import sqlalchemy as sa

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
                SELECT bpmn_xml_file_contents
                FROM process_instance_bpmn_snapshot
                WHERE m8f_tenant_id = :m8f_tenant_id
                  AND process_instance_id = :process_instance_id
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
    _PATCHED = True

