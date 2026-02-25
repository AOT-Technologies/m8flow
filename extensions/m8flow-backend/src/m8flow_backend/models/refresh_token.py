from dataclasses import dataclass

from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint

from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db


@dataclass()
class RefreshTokenModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel):
    __tablename__ = "refresh_token"
    __table_args__ = (
        UniqueConstraint(
            "m8f_tenant_id",
            "user_id",
            name="refresh_token_user_id_tenant_unique",
        ),
    )

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(ForeignKey("user.id"), nullable=False)
    token: str = db.Column(db.String(4096), nullable=False)
