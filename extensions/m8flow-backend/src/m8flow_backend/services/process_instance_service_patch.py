from __future__ import annotations

import time

_PATCHED = False


def apply() -> None:
    """Persist BPMN XML snapshot at process instance creation time.

    This ensures old process instances can show the diagram that was executed,
    even when the underlying process model files change later.
    """

    global _PATCHED
    if _PATCHED:
        return

    from flask import current_app

    from spiffworkflow_backend.models.db import db
    import sqlalchemy as sa
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from spiffworkflow_backend.services.spec_file_service import SpecFileService

    original_create_process_instance = ProcessInstanceService.create_process_instance

    @classmethod  # type: ignore[misc]
    def patched_create_process_instance(cls, process_model, user, start_configuration=None, load_bpmn_process_model: bool = True):
        process_instance_model, start_config = original_create_process_instance(
            process_model,
            user,
            start_configuration=start_configuration,
            load_bpmn_process_model=load_bpmn_process_model,
        )

        primary_file_name = getattr(process_model, "primary_file_name", None)
        if primary_file_name:
            try:
                raw_bytes = SpecFileService.get_data(process_model, primary_file_name)
                xml_text = raw_bytes.decode("utf-8")
                if xml_text:
                    # Upstream only adds the ProcessInstanceModel to the session; it doesn't flush/commit.
                    # We need an id + tenant id before we can store a snapshot row.
                    db.session.flush()
                    tenant_id = getattr(process_instance_model, "m8f_tenant_id", None)
                    if tenant_id:
                        db.session.execute(
                            sa.text(
                                """
                                INSERT INTO process_instance_bpmn_snapshot
                                  (m8f_tenant_id, process_instance_id, bpmn_xml_file_contents, created_at_in_seconds)
                                VALUES
                                  (:m8f_tenant_id, :process_instance_id, :bpmn_xml_file_contents, :created_at_in_seconds)
                                ON CONFLICT(process_instance_id) DO NOTHING
                                """
                            ),
                            {
                                "m8f_tenant_id": tenant_id,
                                "process_instance_id": process_instance_model.id,
                                "bpmn_xml_file_contents": xml_text,
                                "created_at_in_seconds": round(time.time()),
                            },
                        )
            except Exception:
                current_app.logger.warning(
                    "Failed to snapshot BPMN XML for process instance %s (process_model=%s)",
                    getattr(process_instance_model, "id", None),
                    getattr(process_model, "id", None),
                    exc_info=True,
                )

        return process_instance_model, start_config

    ProcessInstanceService.create_process_instance = patched_create_process_instance  # type: ignore[assignment]
    _PATCHED = True
