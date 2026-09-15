"""Postgres ``secret`` table provider — the default SecretProvider."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend.models.native import SecretModel
from m8flow_backend.secrets.crypto import decrypt_secret_value, encrypt_secret_value
from m8flow_backend.secrets.provider import SecretListPage, SecretRecord


def _not_found(key: str) -> ApiError:
    return ApiError(
        "missing_secret_error",
        f"Unable to locate a secret with the name: {key}. ",
        404,
    )


def _record(row: SecretModel) -> SecretRecord:
    return SecretRecord(
        id=row.id,
        key=row.key,
        user_id=row.created_by_user_id,
        tenant_id=row.m8f_tenant_id,
        created_at_in_seconds=row.created_at_in_seconds,
        updated_at_in_seconds=row.updated_at_in_seconds,
    )


def _row(session: Session, *, tenant_id: str, key: str) -> SecretModel | None:
    return session.scalars(
        select(SecretModel).where(SecretModel.m8f_tenant_id == tenant_id, SecretModel.key == key)
    ).first()


class DatabaseSecretProvider:
    def add(
        self,
        session: Session,
        *,
        tenant_id: str,
        key: str,
        value: str,
        user_id: int,
    ) -> SecretRecord:
        if _row(session, tenant_id=tenant_id, key=key) is not None:
            raise ApiError(
                "create_secret_error",
                f"There was an error creating a secret with key: {key}.",
                409,
            )
        row = SecretModel(
            key=key,
            value=encrypt_secret_value(value),
            m8f_tenant_id=tenant_id,
            created_by_user_id=user_id,
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise ApiError(
                "create_secret_error",
                f"There was an error creating a secret with key: {key}.",
                409,
            ) from exc
        return _record(row)

    def get(self, session: Session, *, tenant_id: str, key: str) -> SecretRecord:
        row = _row(session, tenant_id=tenant_id, key=key)
        if row is None:
            raise _not_found(key)
        return _record(row)

    def get_value(self, session: Session, *, tenant_id: str, key: str) -> str | None:
        row = _row(session, tenant_id=tenant_id, key=key)
        if row is None:
            return None
        return decrypt_secret_value(row.value)

    def update(self, session: Session, *, tenant_id: str, key: str, value: str) -> None:
        row = _row(session, tenant_id=tenant_id, key=key)
        if row is None:
            raise ApiError(
                "update_secret_error",
                f"Cannot update secret with key: {key}. Resource does not exist.",
                404,
            )
        row.value = encrypt_secret_value(value)

    def delete(self, session: Session, *, tenant_id: str, key: str) -> None:
        row = _row(session, tenant_id=tenant_id, key=key)
        if row is None:
            raise ApiError(
                "delete_secret_error",
                f"Cannot delete secret with key: {key}. Resource does not exist.",
                404,
            )
        session.delete(row)

    def list(
        self,
        session: Session,
        *,
        tenant_id: str,
        page: int = 1,
        per_page: int = 100,
    ) -> SecretListPage:
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        total = session.scalar(
            select(func.count()).select_from(SecretModel).where(SecretModel.m8f_tenant_id == tenant_id)
        ) or 0
        rows = session.scalars(
            select(SecretModel)
            .where(SecretModel.m8f_tenant_id == tenant_id)
            .order_by(SecretModel.key.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return SecretListPage(
            records=tuple(_record(row) for row in rows),
            total=int(total),
            page=page,
            per_page=per_page,
        )

    def list_keys(self, session: Session, *, tenant_id: str) -> list[str]:
        return list(
            session.scalars(
                select(SecretModel.key)
                .where(SecretModel.m8f_tenant_id == tenant_id)
                .order_by(SecretModel.key.asc())
            ).all()
        )
