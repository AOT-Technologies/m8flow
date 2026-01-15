from sqlalchemy import (
    Column, String, DateTime, Boolean, ForeignKey, Text, Integer, func, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Tenant(Base):
    __tablename__ = "m8flow_tenant"
    id = Column(String, primary_key=True)          # e.g., uuid
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


