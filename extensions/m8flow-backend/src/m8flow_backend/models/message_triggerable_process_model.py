from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


class MessageTriggerableProcessModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel):
    __tablename__ = "message_triggerable_process_model"
    __table_args__ = (
        db.UniqueConstraint(
            "m8f_tenant_id",
            "message_name",
            name="message_triggerable_process_model_message_name_tenant_unique",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    message_name: str = db.Column(db.String(255), index=True)
    process_model_identifier: str = db.Column(db.String(255), nullable=False, index=True)
    file_name: str = db.Column(db.String(255), index=True)

    updated_at_in_seconds: int = db.Column(db.Integer)
    created_at_in_seconds: int = db.Column(db.Integer)
