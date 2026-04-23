from __future__ import annotations

import hashlib
import time

_PATCHED = False


def apply() -> None:
    """Persist BPMN XML version at process instance creation time.

    Computes a SHA-256 hash of the primary BPMN file contents and upserts a
    row into process_model_bpmn_version.  The process instance then gets a FK
    reference (bpmn_version_id) so it always points to the exact BPMN that was
    active when the instance was created — without duplicating XML across
    instances that share the same model version.
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
                    # We need an id + tenant id before we can store the version reference.
                    db.session.flush()
                    tenant_id = getattr(process_instance_model, "m8f_tenant_id", None)
                    if tenant_id:
                        bpmn_hash = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
                        model_id = getattr(process_model, "id", "")

                        # Upsert: insert if the (tenant, model, hash) combo doesn't exist yet.
                        db.session.execute(
                            sa.text(
                                """
                                INSERT INTO process_model_bpmn_version
                                  (m8f_tenant_id, process_model_identifier, bpmn_xml_hash, bpmn_xml_file_contents, created_at_in_seconds)
                                VALUES
                                  (:m8f_tenant_id, :process_model_identifier, :bpmn_xml_hash, :bpmn_xml_file_contents, :created_at_in_seconds)
                                ON CONFLICT(m8f_tenant_id, process_model_identifier, bpmn_xml_hash) DO NOTHING
                                """
                            ),
                            {
                                "m8f_tenant_id": tenant_id,
                                "process_model_identifier": model_id,
                                "bpmn_xml_hash": bpmn_hash,
                                "bpmn_xml_file_contents": xml_text,
                                "created_at_in_seconds": round(time.time()),
                            },
                        )

                        # Retrieve the version id (may have been inserted just now or previously).
                        version_row = db.session.execute(
                            sa.text(
                                """
                                SELECT id FROM process_model_bpmn_version
                                WHERE m8f_tenant_id = :m8f_tenant_id
                                  AND process_model_identifier = :process_model_identifier
                                  AND bpmn_xml_hash = :bpmn_xml_hash
                                LIMIT 1
                                """
                            ),
                            {
                                "m8f_tenant_id": tenant_id,
                                "process_model_identifier": model_id,
                                "bpmn_xml_hash": bpmn_hash,
                            },
                        ).first()

                        if version_row is not None:
                            process_instance_model.bpmn_version_id = version_row[0]
            except Exception:
                current_app.logger.warning(
                    "Failed to record BPMN version for process instance %s (process_model=%s)",
                    getattr(process_instance_model, "id", None),
                    getattr(process_model, "id", None),
                    exc_info=True,
                )

        return process_instance_model, start_config

    ProcessInstanceService.create_process_instance = patched_create_process_instance  # type: ignore[assignment]
    _PATCHED = True
