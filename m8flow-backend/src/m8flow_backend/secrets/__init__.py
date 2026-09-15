from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from m8flow_bpmn_core import api
from m8flow_bpmn_core.models.tenant import M8flowTenantModel
from m8flow_bpmn_core.models.user import UserModel
from m8flow_bpmn_core.services.connector_proxy_service_tasks import (
    build_connector_proxy_service_task_registry,
)
from m8flow_bpmn_core.services.service_tasks import ServiceTaskRegistry

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets.database import DatabaseSecretProvider
from m8flow_backend.secrets.provider import (
    DEFAULT_SECRET_BACKEND_KIND,
    SecretListPage,
    SecretRecord,
    get_secret_provider,
    register_secret_provider,
    registered_secret_backend_kinds,
    resolved_secret_backend_kind,
)
from m8flow_backend.secrets.vault import VaultSecretProvider

SECRET_SENTINEL = re.compile(r"M8FLOW_SECRET:(?P<variable_name>\w+)")
SECRET_KEY_PATTERN = re.compile(r"^\w+$")
EMPTY_SECRET_LIST = {"results": [], "pagination": {"count": 0, "total": 0, "pages": 0}}

register_secret_provider(DEFAULT_SECRET_BACKEND_KIND, DatabaseSecretProvider)
register_secret_provider("vault", VaultSecretProvider)


def require_secret_key(key: str) -> str:
    cleaned = (key or "").strip()
    if not SECRET_KEY_PATTERN.fullmatch(cleaned):
        raise ApiError("validation_error", "Secret key must be a word (letters, digits, underscore).", 400)
    return cleaned


def add_secret(
    session: Session,
    *,
    tenant_id: str,
    key: str,
    value: str,
    user_id: int,
) -> SecretRecord:
    return get_secret_provider().add(
        session,
        tenant_id=tenant_id,
        key=require_secret_key(key),
        value=value,
        user_id=user_id,
    )


def get_secret(session: Session, *, tenant_id: str, key: str) -> SecretRecord:
    return get_secret_provider().get(session, tenant_id=tenant_id, key=require_secret_key(key))


def get_secret_value(session: Session, *, tenant_id: str, key: str) -> str | None:
    if not SECRET_KEY_PATTERN.fullmatch(key or ""):
        return None
    return get_secret_provider().get_value(session, tenant_id=tenant_id, key=key)


def update_secret(session: Session, *, tenant_id: str, key: str, value: str) -> None:
    get_secret_provider().update(session, tenant_id=tenant_id, key=require_secret_key(key), value=value)


def delete_secret(session: Session, *, tenant_id: str, key: str) -> None:
    get_secret_provider().delete(session, tenant_id=tenant_id, key=require_secret_key(key))


def list_secrets(
    session: Session,
    *,
    tenant_id: str,
    page: int = 1,
    per_page: int = 100,
) -> SecretListPage:
    return get_secret_provider().list(session, tenant_id=tenant_id, page=page, per_page=per_page)


def list_secret_keys(session: Session, *, tenant_id: str) -> list[str]:
    return get_secret_provider().list_keys(session, tenant_id=tenant_id)


def serialize_secret_list(session: Session, page: SecretListPage) -> dict[str, Any]:
    user_ids = {record.user_id for record in page.records if record.user_id}
    usernames: dict[int, str] = {}
    if user_ids:
        users = session.scalars(select(UserModel).where(UserModel.id.in_(user_ids))).all()
        usernames = {user.id: user.username for user in users}
    tenant_ids = {record.tenant_id for record in page.records if record.tenant_id}
    tenant_names: dict[str, str] = {}
    if tenant_ids:
        tenants = session.scalars(select(M8flowTenantModel).where(M8flowTenantModel.id.in_(tenant_ids))).all()
        tenant_names = {tenant.id: tenant.name for tenant in tenants}
    results = []
    for record in page.records:
        row = record.to_dict()
        row["username"] = usernames.get(record.user_id)
        row["tenantId"] = record.tenant_id
        row["tenantName"] = tenant_names.get(record.tenant_id)
        results.append(row)
    return {"results": results, "pagination": page.pagination()}


def resolve_possibly_secret_value(session: Session, *, tenant_id: str, value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        stored = get_secret_value(session, tenant_id=tenant_id, key=match.group("variable_name"))
        return stored if stored is not None else match.group(0)

    return SECRET_SENTINEL.sub(_replace, value)


def list_connectors(registry: ServiceTaskRegistry | None = None) -> list[dict[str, Any]]:
    active = registry or _default_registry()
    grouped: dict[str, list[str]] = {}
    for command in active.list_commands():
        grouped.setdefault(command.connector_key, []).append(command.command_name)
    return [{"name": key, "commands": commands} for key, commands in grouped.items()]


def connector_proxy_url() -> str | None:
    """Active connector-proxy base URL, or None when connectors are not configured.

    Prefers ``M8FLOW_BACKEND_CONNECTOR_PROXY_URL``; falls back to the Spiff-mapped
    name after ``apply_m8flow_env_mapping()``.
    """
    raw = (
        os.environ.get("M8FLOW_BACKEND_CONNECTOR_PROXY_URL")
        or os.environ.get("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL")
        or ""
    ).strip()
    return raw or None


def build_host_service_task_registry() -> ServiceTaskRegistry:
    """Build the host ServiceTaskRegistry from the configured connector proxy.

    When ``M8FLOW_BACKEND_CONNECTOR_PROXY_URL`` is unset, returns an empty registry
    (unit tests / hosts without connectors). When set, fetches ``GET /v1/commands``
    via core's connector-proxy client — failures raise rather than silently emptying
    the catalog. The returned registry injects ``m8flow_profile`` then resolves
    ``M8FLOW_SECRET:`` sentinels on ``execute`` (missing keys fail closed).
    """
    from m8flow_backend.connectors.runtime import wrap_registry_for_connector_profiles
    from m8flow_backend.secrets.runtime import wrap_registry_for_secret_sentinels

    base_url = connector_proxy_url()
    if base_url is None:
        inner: ServiceTaskRegistry = ServiceTaskRegistry()
    else:
        inner = build_connector_proxy_service_task_registry(base_url)
    return wrap_registry_for_connector_profiles(wrap_registry_for_secret_sentinels(inner))


def install_registry_at_boot() -> None:
    api.set_default_service_task_registry_factory(build_host_service_task_registry)


def _default_registry() -> ServiceTaskRegistry:
    return build_host_service_task_registry()


__all__ = [
    "EMPTY_SECRET_LIST",
    "SECRET_KEY_PATTERN",
    "SECRET_SENTINEL",
    "SecretListPage",
    "SecretRecord",
    "add_secret",
    "build_host_service_task_registry",
    "connector_proxy_url",
    "delete_secret",
    "get_secret",
    "get_secret_provider",
    "get_secret_value",
    "install_registry_at_boot",
    "list_connectors",
    "list_secret_keys",
    "list_secrets",
    "register_secret_provider",
    "registered_secret_backend_kinds",
    "require_secret_key",
    "resolved_secret_backend_kind",
    "resolve_possibly_secret_value",
    "serialize_secret_list",
    "update_secret",
]
