from dataclasses import dataclass
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped
from spiffworkflow_backend.models.user import UserModel


@dataclass
class SecretModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel):
    """SQLAlchemy model for SecretModel."""
    __tablename__ = "secret"
    __table_args__ = (UniqueConstraint("m8f_tenant_id", "key", name="secret_key_tenant_unique"),)

    id: int = db.Column(db.Integer, primary_key=True)
    key: str = db.Column(db.String(50), nullable=False)
    value: str = db.Column(db.Text(), nullable=False)
    user_id: int = db.Column(ForeignKey(UserModel.id), nullable=False, index=True)  # type: ignore
    updated_at_in_seconds: int = db.Column(db.Integer)
    created_at_in_seconds: int = db.Column(db.Integer)

    def to_dict(self) -> dict[str, Any]:
        """Create a JSON serializable representation of the model."""
        return {
            "id": self.id,
            "key": self.key,
            "user_id": self.user_id,
            "updated_at_in_seconds": self.updated_at_in_seconds,
            "created_at_in_seconds": self.created_at_in_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SecretModel":
        """Create a SecretModel instance from a dictionary."""
        return cls(**data)
