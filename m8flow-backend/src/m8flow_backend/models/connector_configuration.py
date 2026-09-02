from __future__ import annotations

from typing import Any

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


class ConnectorConfigurationModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """One named connector profile for one tenant.

    A profile is a reusable credential and configuration set -- "smtp-staging",
    "smtp-production" -- that a BPMN service task selects by name instead of
    spelling out host, user and password on every task.

    ``config_json`` and ``secret_refs`` are retained temporarily for the
    compatibility migration from the original profile implementation. New code
    will use ``ConnectorVariableModel`` for field-level metadata and a single
    provider document referenced by ``provider_key`` for sensitive values.
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
    variables = db.relationship(
        "ConnectorVariableModel",
        back_populates="configuration",
        cascade="all, delete-orphan",
    )

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

    # Nullable during the additive migration. They become required after every
    # legacy profile has been backfilled to the provider-document format.
    provider_key = db.Column(db.String(255), nullable=True)
    schema_version = db.Column(db.String(64), nullable=True)

    # config_param values only. Never sensitive.
    config_json = db.Column(db.JSON, nullable=False, default=dict)
    # secret_param field name -> key in the secret store. References, not values.
    secret_refs = db.Column(db.JSON, nullable=False, default=dict)

    # Soft delete. An inactive profile leaves the modeler dropdown, and a run
    # still naming it fails loudly rather than silently sending no credentials.
    is_active = db.Column(db.Boolean, nullable=False, default=True)

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
            "configured_secrets": sorted(
                set((self.secret_refs or {}).keys())
                | {
                    variable.field_name
                    for variable in self.variables
                    if variable.is_sensitive and variable.is_configured
                }
            ),
            "is_active": self.is_active,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
        }

    def __repr__(self) -> str:
        return (
            f"<ConnectorConfigurationModel(id={self.id},"
            f" tenant={self.m8f_tenant_id},"
            f" type={self.connector_type}, profile={self.profile_name})>"
        )


class ConnectorVariableModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """One schema-defined field belonging to a connector configuration.

    Sensitive fields keep ``value`` NULL at all times. ``is_configured`` tells
    the control plane whether the provider document contains that field without
    allowing it to read the value.
    """

    __tablename__ = "m8flow_connector_variable"
    __table_args__ = (
        db.UniqueConstraint(
            "connector_configuration_id",
            "field_name",
            name="uq_m8flow_connector_variable_field",
        ),
        db.CheckConstraint(
            "(is_sensitive = false) OR (value IS NULL)",
            name="ck_m8flow_connector_variable_sensitive_value",
        ),
        db.Index(
            "ix_m8flow_connector_variable_tenant_configuration",
            "m8f_tenant_id",
            "connector_configuration_id",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    m8f_tenant_id = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        nullable=False,
        index=True,
    )
    connector_configuration_id = db.Column(
        db.Integer,
        db.ForeignKey("m8flow_connector_configuration.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    configuration = db.relationship(
        "ConnectorConfigurationModel", back_populates="variables"
    )
    field_name = db.Column(db.String(255), nullable=False)
    is_sensitive = db.Column(db.Boolean, nullable=False)
    # JSON normally serializes Python None as JSON null. The check constraint
    # intentionally requires SQL NULL for sensitive fields, so make the
    # distinction explicit at the SQLAlchemy boundary.
    value = db.Column(db.JSON(none_as_null=True), nullable=True)
    is_configured = db.Column(db.Boolean, nullable=False, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ConnectorVariableModel(id={self.id}, tenant={self.m8f_tenant_id}, "
            f"configuration_id={self.connector_configuration_id}, field={self.field_name})>"
        )
