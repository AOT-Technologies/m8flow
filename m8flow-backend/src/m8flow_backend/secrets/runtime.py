"""Resolve ``M8FLOW_SECRET:`` sentinels on service-task execute.

List/show keep ``resolve_possibly_secret_value`` (leave missing tokens in
place). Runtime execute fails closed so a literal sentinel is never posted
to a connector.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from m8flow_bpmn_core.services.service_tasks import (
    ServiceTaskRegistry,
    ServiceTaskRequest,
    ServiceTaskResult,
)

from m8flow_backend.secrets import SECRET_SENTINEL, get_secret_value


def resolve_secret_sentinels_for_runtime(
    session: Any, *, tenant_id: str, value: str, found: list[str] | None = None
) -> str:
    """``found`` collects each substituted secret value (for error masking)."""

    def _replace(match) -> str:
        key = match.group("variable_name")
        stored = get_secret_value(session, tenant_id=tenant_id, key=key)
        if stored is None:
            raise ServiceTaskExecutionError(
                f"Secret {key!r} is not defined for this tenant."
            )
        if found is not None:
            found.append(stored)
        return stored

    return SECRET_SENTINEL.sub(_replace, value)


def masked_service_task_error(
    exc: BaseException, secret_values: Iterable[object]
) -> ServiceTaskExecutionError | None:
    """A copy of ``exc`` with every secret value in its text replaced by
    ``***``, or None when there is nothing to mask. Only a
    ``ServiceTaskExecutionError``'s text reaches users (core replaces any other
    exception's with a generic message), so nothing else is re-worded."""
    if not isinstance(exc, ServiceTaskExecutionError):
        return None
    message = masked = str(exc)
    # Longest first, so a secret that is a substring of another can't leave a tail.
    for value in sorted({v for v in secret_values if isinstance(v, str) and v}, key=len, reverse=True):
        masked = masked.replace(value, "***")
    return None if masked == message else ServiceTaskExecutionError(masked)


def _resolve_tree(value: object, *, session: Any, tenant_id: str, found: list[str]) -> object:
    if isinstance(value, str):
        return resolve_secret_sentinels_for_runtime(session, tenant_id=tenant_id, value=value, found=found)
    if isinstance(value, Mapping):
        return {
            key: _resolve_tree(item, session=session, tenant_id=tenant_id, found=found)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_tree(item, session=session, tenant_id=tenant_id, found=found) for item in value]
    if isinstance(value, tuple):
        return tuple(_resolve_tree(item, session=session, tenant_id=tenant_id, found=found) for item in value)
    return value


def _with_resolved_parameters(request: ServiceTaskRequest, found: list[str]) -> ServiceTaskRequest:
    context = request.context
    if context is None:
        raise ServiceTaskExecutionError("Service task is missing tenant context for secret resolution.")
    from m8flow_backend.db import current_session

    session = current_session()
    parameters = _resolve_tree(request.parameters, session=session, tenant_id=context.tenant_id, found=found)
    return replace(request, parameters=parameters)


class SecretResolvingServiceTaskRegistry(ServiceTaskRegistry):
    def execute(self, request: ServiceTaskRequest) -> ServiceTaskResult:
        found: list[str] = []
        resolved = _with_resolved_parameters(request, found)
        try:
            return super().execute(resolved)
        except Exception as exc:
            masked = masked_service_task_error(exc, found)
            if masked is None:
                raise
            raise masked from exc


def wrap_registry_for_secret_sentinels(registry: ServiceTaskRegistry) -> ServiceTaskRegistry:
    if isinstance(registry, SecretResolvingServiceTaskRegistry):
        return registry
    wrapped = SecretResolvingServiceTaskRegistry()
    for connector_key in registry.list_connectors():
        wrapped.register_connector(registry.get_connector(connector_key), replace=True)
    return wrapped
