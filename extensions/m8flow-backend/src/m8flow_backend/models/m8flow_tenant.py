from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db


class M8flowTenantModel(SpiffworkflowBaseDBModel):
    """SQLAlchemy model for M8flowTenantModel."""
    __tablename__ = "m8flow_tenant"

    id = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
