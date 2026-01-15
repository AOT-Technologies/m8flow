from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


# TODO: delete this file
class ProcessCallerCacheModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel):
    """SQLAlchemy model for ProcessCallerCacheModel."""

    __tablename__ = "process_caller_cache"
    id = db.Column(db.Integer, primary_key=True)
    process_identifier = db.Column(db.String(255), index=True)
    calling_process_identifier = db.Column(db.String(255))