from spiffworkflow_backend.models.db import db


class TenantScoped:
    """Helper class for TenantScoped."""
    __abstract__ = True


class M8fTenantScopedMixin:
    """Mixin for M8fTenantScopedMixin behavior."""
    m8f_tenant_id = db.Column(db.String(255), db.ForeignKey("m8flow_tenant.id"), nullable=False, index=True)
