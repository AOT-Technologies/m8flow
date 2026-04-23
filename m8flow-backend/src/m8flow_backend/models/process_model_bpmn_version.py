from __future__ import annotations

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


class ProcessModelBpmnVersionModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel):
    __tablename__ = "process_model_bpmn_version"
    __table_args__ = (
        db.UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "bpmn_xml_hash",
            name="uq_process_model_bpmn_version_tenant_model_hash",
        ),
    )

    id: int = db.Column(db.Integer, primary_key=True)
    process_model_identifier: str = db.Column(db.String(255), nullable=False, index=True)
    bpmn_xml_hash: str = db.Column(db.String(64), nullable=False, index=True)
    bpmn_xml_file_contents: str = db.Column(db.Text, nullable=False)
    created_at_in_seconds: int = db.Column(db.Integer, nullable=False, index=True)
