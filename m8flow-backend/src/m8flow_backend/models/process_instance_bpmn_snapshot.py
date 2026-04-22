from __future__ import annotations

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


class ProcessInstanceBpmnSnapshotModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel):
    __tablename__ = "process_instance_bpmn_snapshot"

    id: int = db.Column(db.Integer, primary_key=True)
    process_instance_id: int = db.Column(
        db.Integer,
        db.ForeignKey("process_instance.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    bpmn_xml_file_contents: str = db.Column(db.Text, nullable=False)
    created_at_in_seconds: int = db.Column(db.Integer, nullable=False, index=True)

