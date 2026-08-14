from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


@dataclass
class ConnectorConfigurationModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """One named connector profile for one tenant.

    A profile is a reusable credential/configuration set - "smtp-staging",
    "smtp-production" - that a BPMN service task selects by name instead of
    spelling out host, user and password on every task.

    Storage split follows the platform rule that ciphertext lives only in the
    secret store: ``config_json`` holds the non-sensitive values, and
    ``secret_refs`` maps each sensitive field to its key in the secret store.
    No secret value is ever stored on this row.
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

    id: int = db.Column(db.Integer, primary_key=True)

    m8f_tenant_id: str = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        nullable=False,
        index=True,
    )

    # Validated against the connector registry in the application layer, so a
    # new connector is a code change with no migration.
    connector_type: str = db.Column(db.String(50), nullable=False)

    # Stable identifier used in BPMN (the m8flow_profile parameter value).
    profile_name: str = db.Column(db.String(255), nullable=False)
    display_name: str = db.Column(db.String(255), nullable=False)
    description: str | None = db.Column(db.Text, nullable=True)

    # config_param values only. Never sensitive.
    config_json: dict[str, Any] = db.Column(db.JSON, nullable=False, default=dict)
    # secret_param field -> key in the secret store. References, never values.
    secret_refs: dict[str, str] = db.Column(db.JSON, nullable=False, default=dict)

    is_active: bool = db.Column(db.Boolean, nullable=False, default=True)
    is_default: bool = db.Column(db.Boolean, nullable=False, default=False)

    user_id: int | None = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """API shape. Carries secret field *names*, never values."""
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
            f"<ConnectorConfigurationModel(id={self.id}, tenant_id={self.m8f_tenant_id},"
            f" connector_type={self.connector_type}, profile_name={self.profile_name})>"
        )
