from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, null
from sqlalchemy.exc import IntegrityError

from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.services.named_value_secret_storage import get_named_value_secret_storage
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db

_VALUE_UNSET = object()


class NamedValueService:
    """CRUD for the catalog and payloads of manual configuration variables."""

    @staticmethod
    def _stored_value(value: Any, is_sensitive: bool) -> Any:
        """Return the database representation required by the storage policy."""
        return null() if is_sensitive else value

    @staticmethod
    def normalize_name(name: str) -> str:
        """Validate and normalize a catalog name for all callers, including seed jobs."""
        if not isinstance(name, str):
            raise ApiError("invalid_name", "name must be 1-255 characters.", status_code=400)
        normalized = name.strip()
        if not normalized or len(normalized) > 255:
            raise ApiError("invalid_name", "name must be 1-255 characters.", status_code=400)
        return normalized

    @staticmethod
    def _duplicate_name_error(name: str) -> ApiError:
        return ApiError(
            "duplicate_name",
            f'A configuration variable named "{name}" already exists in this tenant. '
            "Names are case-insensitive.",
            status_code=409,
        )

    @classmethod
    def _ensure_name_available(
        cls, tenant_id: str, name: str, *, exclude_id: str | None = None
    ) -> None:
        query = NamedValueModel.query.filter(
            NamedValueModel.m8f_tenant_id == tenant_id,
            func.lower(NamedValueModel.name) == name.lower(),
        )
        if exclude_id is not None:
            query = query.filter(NamedValueModel.id != exclude_id)
        if query.first() is not None:
            raise cls._duplicate_name_error(name)

    @classmethod
    def _map_name_integrity_error(cls, exc: IntegrityError, name: str) -> None:
        # The pre-check is user-friendly; the functional index remains the
        # authority for concurrent requests that pass the pre-check together.
        details = str(getattr(exc, "orig", exc)).lower()
        if "uq_m8flow_named_value_tenant_name_ci" in details or "23505" in details:
            raise cls._duplicate_name_error(name) from exc
        raise exc

    @staticmethod
    def list_values(tenant_id: str) -> list[NamedValueModel]:
        return (
            NamedValueModel.query.filter(NamedValueModel.m8f_tenant_id == tenant_id)
            .order_by(NamedValueModel.name.asc())
            .all()
        )

    @staticmethod
    def get_value(tenant_id: str, value_id: str) -> NamedValueModel | None:
        return NamedValueModel.query.filter_by(
            id=value_id, m8f_tenant_id=tenant_id
        ).one_or_none()

    @staticmethod
    def create_value(
        tenant_id: str,
        user_id: int | None,
        name: str,
        value: Any,
        description: str | None,
        is_sensitive: bool = False,
        *,
        allow_unattributed_sensitive: bool = False,
    ) -> NamedValueModel:
        name = NamedValueService.normalize_name(name)
        NamedValueService._ensure_name_available(tenant_id, name)
        if is_sensitive:
            if not isinstance(value, str) or not value:
                raise ApiError("invalid_value", "A sensitive value is required.", status_code=400)
            if user_id is None and not allow_unattributed_sensitive:
                raise ApiError("not_authenticated", "User not authenticated.", status_code=401)
        row = NamedValueModel(
            id=str(uuid4()),
            m8f_tenant_id=tenant_id,
            name=name,
            description=description,
            is_sensitive=is_sensitive,
            # Use SQL NULL explicitly. JSON's Python ``None`` serialization can
            # otherwise produce the JSON literal ``null``, which is not NULL to
            # PostgreSQL and violates the sensitive-value storage constraint.
            value=NamedValueService._stored_value(value, is_sensitive),
            is_configured=True,
            user_id=user_id,
        )
        db.session.add(row)
        try:
            # The ID exists before Vault is written and is the immutable
            # provider key. Vault receives only the sensitive payload.
            db.session.flush()
            if is_sensitive:
                get_named_value_secret_storage().write(row, value)
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            NamedValueService._map_name_integrity_error(exc, name)
        except Exception:
            db.session.rollback()
            if is_sensitive:
                try:
                    get_named_value_secret_storage().delete(row)
                except Exception:
                    pass
            raise
        return row

    @staticmethod
    def update_value(
        row: NamedValueModel,
        *,
        name: str,
        description: str | None,
        value: Any = _VALUE_UNSET,
        is_sensitive: bool = False,
    ) -> NamedValueModel:
        name = NamedValueService.normalize_name(name)
        NamedValueService._ensure_name_available(
            row.m8f_tenant_id, name, exclude_id=row.id
        )
        value_supplied = value is not _VALUE_UNSET
        if row.is_sensitive and not is_sensitive and (not value_supplied or not value):
            raise ApiError(
                "value_required",
                "A new value is required when making a variable non-sensitive.",
                status_code=400,
            )
        if row.is_sensitive != is_sensitive and is_sensitive and (
            not isinstance(value, str) or not value
        ):
            raise ApiError(
                "value_required",
                "A new value is required when making a variable sensitive.",
                status_code=400,
            )
        storage = get_named_value_secret_storage()
        was_sensitive = row.is_sensitive
        row.name = name
        row.description = description
        # Check the unique index before changing a provider-backed value. This
        # also makes a concurrent name conflict leave Vault untouched.
        try:
            db.session.flush()
        except IntegrityError as exc:
            db.session.rollback()
            NamedValueService._map_name_integrity_error(exc, name)
        if was_sensitive != is_sensitive:
            if is_sensitive:
                storage.write(row, value)
                row.value = NamedValueService._stored_value(value, True)
            else:
                row.value = value
            row.is_sensitive = is_sensitive
        elif row.is_sensitive:
            if value_supplied and value:
                storage.write(row, value)
            row.value = NamedValueService._stored_value(None, True)
        else:
            if value_supplied:
                row.value = value
        row.is_configured = True
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            NamedValueService._map_name_integrity_error(exc, name)
        if was_sensitive and not is_sensitive:
            # Removing an old sensitive payload after the catalog transition
            # leaves, at worst, an unreachable provider orphan on failure.
            try:
                storage.delete(row)
            except Exception:
                pass
        return row

    @staticmethod
    def delete_value(row: NamedValueModel) -> None:
        if row.is_sensitive:
            get_named_value_secret_storage().delete(row)
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def resolve_value(row: NamedValueModel) -> Any:
        """Resolve a value only for private runtime use, never list/detail APIs."""
        if not row.is_sensitive:
            return row.value
        value = get_named_value_secret_storage().read(row)
        if value is None:
            raise ApiError("missing_secret_error", "Sensitive configuration variable is not configured.", status_code=404)
        return value
