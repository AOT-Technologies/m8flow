"""Postgres ``secret`` table provider — the default SecretProvider."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend.models.native import SecretModel
from m8flow_backend.secrets.crypto import decrypt_secret_value, encrypt_secret_value
from m8flow_backend.secrets.provider import SecretListPage, SecretRecord

_CONFIGURATION_VALUE_KEY_PREFIX = "m8flow_named_value_"
_CONNECTOR_CONFIGURATION_KEY_PREFIX = "m8flow_connector_configuration_"


def _configuration_value_key(variable_id: str) -> str:
    return _CONFIGURATION_VALUE_KEY_PREFIX + variable_id.replace("-", "")


def _connector_configuration_key(configuration_id: int) -> str:
    return f"{_CONNECTOR_CONFIGURATION_KEY_PREFIX}{configuration_id}"


def _is_internal_key(key_column):
    return ~key_column.like(f"{_CONFIGURATION_VALUE_KEY_PREFIX}%") & ~key_column.like(
        f"{_CONNECTOR_CONFIGURATION_KEY_PREFIX}%"
    )


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
        created_at=row.created_at,
        updated_at=row.updated_at,
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
        tenant_id: str | None,
        page: int = 1,
        per_page: int = 100,
    ) -> SecretListPage:
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        # tenant_id None == "all tenants": caller-verified super-admin only
        # (auth.resolve_read_tenant_id). Records carry no secret value, so this
        # lists keys/metadata across tenants, never plaintext.
        count_stmt = select(func.count()).select_from(SecretModel)
        rows_stmt = select(SecretModel)
        if tenant_id is not None:
            count_stmt = count_stmt.where(SecretModel.m8f_tenant_id == tenant_id)
            rows_stmt = rows_stmt.where(SecretModel.m8f_tenant_id == tenant_id)
        count_stmt = count_stmt.where(_is_internal_key(SecretModel.key))
        rows_stmt = rows_stmt.where(_is_internal_key(SecretModel.key))
        total = session.scalar(count_stmt) or 0
        rows = session.scalars(
            rows_stmt
            .order_by(SecretModel.m8f_tenant_id.asc(), SecretModel.key.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return SecretListPage(
            records=tuple(_record(row) for row in rows),
            total=int(total),
            page=page,
            per_page=per_page,
        )

    def list_keys(self, session: Session, *, tenant_id: str | None) -> list[str]:
        stmt = select(SecretModel.key).where(_is_internal_key(SecretModel.key))
        if tenant_id is not None:
            stmt = stmt.where(SecretModel.m8f_tenant_id == tenant_id)
        return list(session.scalars(stmt.order_by(SecretModel.key.asc())).all())

    def set_configuration_value(
        self,
        session: Session,
        *,
        tenant_id: str,
        variable_id: str,
        value: str,
        user_id: int,
    ) -> None:
        key = _configuration_value_key(variable_id)
        if _row(session, tenant_id=tenant_id, key=key) is None:
            self.add(session, tenant_id=tenant_id, key=key, value=value, user_id=user_id)
        else:
            self.update(session, tenant_id=tenant_id, key=key, value=value)

    def get_configuration_value(
        self, session: Session, *, tenant_id: str, variable_id: str
    ) -> str | None:
        return self.get_value(
            session,
            tenant_id=tenant_id,
            key=_configuration_value_key(variable_id),
        )

    def delete_configuration_value(
        self, session: Session, *, tenant_id: str, variable_id: str
    ) -> None:
        key = _configuration_value_key(variable_id)
        if _row(session, tenant_id=tenant_id, key=key) is not None:
            self.delete(session, tenant_id=tenant_id, key=key)

    def set_connector_configuration(
        self,
        session: Session,
        *,
        tenant_id: str,
        configuration_id: int,
        values: dict[str, str],
        user_id: int,
        replace_existing: bool,
    ) -> None:
        key = _connector_configuration_key(configuration_id)
        serialized = json.dumps(values, separators=(",", ":"), sort_keys=True)
        current = self.get_value(session, tenant_id=tenant_id, key=key)
        if current is not None:
            try:
                current_values = json.loads(current)
            except json.JSONDecodeError as exc:
                raise ApiError(
                    "secret_storage_conflict",
                    "The connector secret document is invalid; resolve it before updating the profile.",
                    409,
                ) from exc
            if current_values != values and not replace_existing:
                raise ApiError(
                    "secret_storage_conflict",
                    "A different connector secret document already exists at the profile path.",
                    409,
                )
            self.update(session, tenant_id=tenant_id, key=key, value=serialized)
        else:
            self.add(session, tenant_id=tenant_id, key=key, value=serialized, user_id=user_id)

    def get_connector_configuration(
        self, session: Session, *, tenant_id: str, configuration_id: int
    ) -> dict[str, str] | None:
        serialized = self.get_value(
            session,
            tenant_id=tenant_id,
            key=_connector_configuration_key(configuration_id),
        )
        if serialized is None:
            return None
        try:
            values = json.loads(serialized)
        except json.JSONDecodeError as exc:
            raise ApiError(
                "secret_storage_error",
                "The connector secret document could not be read.",
                500,
            ) from exc
        if not isinstance(values, dict) or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in values.items()
        ):
            raise ApiError(
                "secret_storage_error",
                "The connector secret document has an invalid shape.",
                500,
            )
        return values

    def delete_connector_configuration(
        self, session: Session, *, tenant_id: str, configuration_id: int
    ) -> None:
        key = _connector_configuration_key(configuration_id)
        if _row(session, tenant_id=tenant_id, key=key) is not None:
            self.delete(session, tenant_id=tenant_id, key=key)
