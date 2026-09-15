"""Inject connector-profile values on service-task execute.

A Service Task opts in with ``m8flow_profile``. The host pops that parameter,
fills empty operator params from the active tenant profile, then the existing
secret-sentinel wrap still runs. Tasks without the parameter are unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from m8flow_bpmn_core.services.service_tasks import (
    ServiceTaskRegistry,
    ServiceTaskRequest,
    ServiceTaskResult,
)

from m8flow_backend.connectors.service import PROFILE_PARAMETER_NAME, resolve_for_runtime

logger = logging.getLogger(__name__)


def _profile_name(entry: Any) -> str | None:
    if isinstance(entry, dict):
        entry = entry.get("value")
    if isinstance(entry, str):
        return entry.strip() or None
    return None


def _is_unset(entry: Any) -> bool:
    if entry is None:
        return True
    value = entry.get("value") if isinstance(entry, dict) else entry
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _accepted_parameter_names(
    registry: ServiceTaskRegistry, operation_id: str
) -> frozenset[str] | None:
    try:
        command = registry.get_command(operation_id)
    except Exception:
        return None
    names = frozenset(parameter.name for parameter in command.parameters)
    return names or None


def apply_profile_to_request(
    request: ServiceTaskRequest, *, registry: ServiceTaskRegistry
) -> ServiceTaskRequest:
    params = request.parameters
    if not params or PROFILE_PARAMETER_NAME not in params:
        return request

    params = dict(params)
    profile_name = _profile_name(params.pop(PROFILE_PARAMETER_NAME, None))
    if not profile_name:
        return replace(request, parameters=params)

    context = request.context
    if context is None:
        raise ServiceTaskExecutionError(
            "Service task is missing tenant context for connector profile resolution."
        )

    from m8flow_backend.db import current_session

    connector_type = request.operation_id.split("/", 1)[0]
    resolved = resolve_for_runtime(
        current_session(),
        tenant_id=context.tenant_id,
        connector_type=connector_type,
        profile_name=profile_name,
    )
    accepted = _accepted_parameter_names(registry, request.operation_id)

    injected: list[str] = []
    for name, value in resolved.items():
        if accepted is not None and name not in accepted:
            continue
        if not _is_unset(params.get(name)):
            continue
        params[name] = value
        injected.append(name)

    logger.info(
        "Connector %s using profile '%s' for parameters: %s",
        request.operation_id,
        profile_name,
        ", ".join(sorted(injected)) or "(none)",
    )
    return replace(request, parameters=params)


class ProfileInjectingServiceTaskRegistry(ServiceTaskRegistry):
    """Delegates to an inner registry after injecting profile values."""

    def __init__(self, inner: ServiceTaskRegistry) -> None:
        super().__init__()
        self._inner = inner

    def execute(self, request: ServiceTaskRequest) -> ServiceTaskResult:
        return self._inner.execute(apply_profile_to_request(request, registry=self._inner))

    def list_connectors(self) -> tuple[str, ...]:
        return self._inner.list_connectors()

    def list_commands(self, *, connector_key: str | None = None):
        return self._inner.list_commands(connector_key=connector_key)

    def get_connector(self, connector_key: str):
        return self._inner.get_connector(connector_key)

    def get_command(self, operation_id: str):
        return self._inner.get_command(operation_id)

    def register_connector(self, connector, *, replace: bool = False) -> None:
        self._inner.register_connector(connector, replace=replace)

    def unregister_connector(self, connector_key: str) -> None:
        self._inner.unregister_connector(connector_key)


def wrap_registry_for_connector_profiles(registry: ServiceTaskRegistry) -> ServiceTaskRegistry:
    if isinstance(registry, ProfileInjectingServiceTaskRegistry):
        return registry
    return ProfileInjectingServiceTaskRegistry(registry)
