from spiffworkflow_backend.models.db import db


class TenantScoped:
    __abstract__ = True


class M8fTenantScopedMixin:
    m8f_tenant_id = db.Column(db.String(255), db.ForeignKey("m8flow_tenant.id"), nullable=False, index=True)
