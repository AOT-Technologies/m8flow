from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_host_%(column_0_label)s",
    "uq": "uq_host_%(table_name)s_%(column_0_name)s",
    "ck": "ck_host_%(table_name)s_%(column_0_name)s",
    "fk": "fk_host_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_host_%(table_name)s",
}


class HostBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    @classmethod
    def commit_with_rollback_on_exception(cls) -> None:
        from m8flow_backend.db import current_session

        current_session().flush()
