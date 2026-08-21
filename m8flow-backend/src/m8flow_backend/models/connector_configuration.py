from __future__ import annotations

from typing import Any

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


class ConnectorConfigurationModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """One named connector profile for one tenant.

    A profile is a reusable credential and configuration set -- "smtp-staging",
    "smtp-production" -- that a BPMN service task selects by name instead of
    spelling out host, user and password on every task.

    The storage split follows the platform rule that ciphertext lives only in
    the secret store: ``config_json`` holds non-sensitive values, ``secret_refs``
    maps each sensitive field to its key in the secret store. No secret value is
    ever stored on this row.
    """

    __tablename__ = "m8flow_connector_configuration"
    __table_args__ = (
        db.UniqueConstraint(
            "m8f_tenant_id",
            "connector_type",
            "profile_name",
            name="uq_m8flow_connector_configuration_profile",
        ),
        db.Index(
            "ix_m8flow_connector_configuration_tenant_type",
            "m8f_tenant_id",
            "connector_type",
        ),
        db.Index(
            "ix_m8flow_connector_configuration_tenant_active",
            "m8f_tenant_id",
            "is_active",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    m8f_tenant_id = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        nullable=False,
        index=True,
    )

    # Validated against CONNECTOR_REGISTRY in the application layer, so adding a
    # connector stays a code change with no migration.
    connector_type = db.Column(db.String(50), nullable=False)

    # The stable identifier BPMN stores as the m8flow_profile parameter value.
    profile_name = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # config_param values only. Never sensitive.
    config_json = db.Column(db.JSON, nullable=False, default=dict)
    # secret_param field name -> key in the secret store. References, not values.
    secret_refs = db.Column(db.JSON, nullable=False, default=dict)

    # Soft delete. An inactive profile leaves the modeler dropdown, and a run
    # still naming it fails loudly rather than silently sending no credentials.
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """API shape. Carries secret field *names* only, never their values."""
        return {
            "id": self.id,
            "connector_type": self.connector_type,
            "profile_name": self.profile_name,
            "display_name": self.display_name,
            "description": self.description,
            "config": dict(self.config_json or {}),
            "configured_secrets": sorted((self.secret_refs or {}).keys()),
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
        }

    def __repr__(self) -> str:
        return (
            f"<ConnectorConfigurationModel(id={self.id},"
            f" tenant={self.m8f_tenant_id},"
            f" type={self.connector_type}, profile={self.profile_name})>"
        )
