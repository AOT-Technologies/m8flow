"""Inject connector profile values into service task calls.

A profile-capable service task must carry an ``m8flow_profile`` parameter,
which the modeler writes when an author picks a profile. At execution the
profile's config and secrets are resolved and merged into the call, so the BPMN
never holds a host name or a password. Tasks for connectors without profile
support are passed through untouched.

``ServiceTaskDelegate.call_connector`` is the hook because it is the single
chokepoint every service task passes through, including the ``http/*`` operators
that upstream runs in-process instead of via the proxy.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from m8flow_backend.connectors.registry import get_connector

logger = logging.getLogger(__name__)

_PATCHED = False

# The proxy's catalogue changes only when the proxy is redeployed.
_CATALOGUE_TTL_SECONDS = 60.0
_catalogue_cache: dict[str, frozenset[str]] | None = None
_catalogue_fetched_at = 0.0


def declared_parameter_names(operator_identifier: str) -> frozenset[str] | None:
    """Parameter names an operator accepts, or None when unknown.

    The proxy builds each command with ``command(**params)``, so passing a
    parameter it does not declare is a hard failure. Profile values are
    therefore injected only into parameters the operator actually takes -- n8n's
    TriggerWorkflow, for one, takes neither base_url nor api_key.
    """
    catalogue = _catalogue()
    if catalogue is None:
        return None
    return catalogue.get(operator_identifier)


def _catalogue() -> dict[str, frozenset[str]] | None:
    global _catalogue_cache, _catalogue_fetched_at

    now = time.monotonic()
    if (
        _catalogue_cache is not None
        and (now - _catalogue_fetched_at) < _CATALOGUE_TTL_SECONDS
    ):
        return _catalogue_cache

    from spiffworkflow_backend.services.service_task_service import ServiceTaskService

    try:
        operators = ServiceTaskService.available_connectors() or []
    except Exception:
        logger.warning("Could not read the connector catalogue", exc_info=True)
        return _catalogue_cache

    if not operators:
        # An empty list means the proxy is unreachable, not that there are no
        # connectors. Keep the last good catalogue rather than believing it.
        return _catalogue_cache

    parsed: dict[str, frozenset[str]] = {}
    for operator in operators:
        operator_id = operator.get("id")
        if not operator_id:
            continue
        parsed[operator_id] = frozenset(
            parameter.get("id")
            for parameter in operator.get("parameters", [])
            if parameter.get("id")
        )

    _catalogue_cache = parsed
    _catalogue_fetched_at = now
    return _catalogue_cache


def reset_catalogue_cache() -> None:
    """Drop the cached catalogue. For tests, and for proxy redeployments."""
    global _catalogue_cache, _catalogue_fetched_at
    _catalogue_cache = None
    _catalogue_fetched_at = 0.0


def _profile_name(entry: Any) -> str | None:
    """Read the profile name out of a bpmn parameter entry.

    Values reaching the delegate have already been evaluated by the script
    engine, so the quoted expression written into the XML arrives as a plain
    string.
    """
    if isinstance(entry, dict):
        entry = entry.get("value")
    if isinstance(entry, str):
        return entry.strip() or None
    return None


def _is_unset(entry: Any) -> bool:
    """True when the author left this parameter empty."""
    if entry is None:
        return True
    value = entry.get("value") if isinstance(entry, dict) else entry
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def apply() -> None:
    """Wrap ServiceTaskDelegate.call_connector with profile resolution."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.service_task_service import ServiceTaskDelegate

    from m8flow_backend.services.connector_profile_service import (
        PROFILE_PARAMETER_NAME,
        ConnectorProfileError,
        ConnectorProfileService,
    )

    original_call_connector = ServiceTaskDelegate.call_connector.__func__

    @classmethod  # type: ignore[misc]
    def patched_call_connector(
        cls, operator_identifier: str, bpmn_params: Any, spiff_task: Any
    ) -> str:
        params = dict(bpmn_params or {})
        profile_name = _profile_name(params.pop(PROFILE_PARAMETER_NAME, None))

        if not profile_name:
            connector_type = operator_identifier.split("/", 1)[0]
            definition = get_connector(connector_type)
            if definition is not None and definition.has_profile_support():
                raise ConnectorProfileError(
                    f"A connector profile must be selected for connector "
                    f"'{connector_type}'.",
                    status_code=400,
                )
            return original_call_connector(
                cls, operator_identifier, bpmn_params, spiff_task
            )

        connector_type = operator_identifier.split("/", 1)[0]
        resolved = ConnectorProfileService.resolve_for_runtime(
            connector_type, profile_name
        )
        accepted = declared_parameter_names(operator_identifier)

        injected: list[str] = []
        for name, value in resolved.items():
            if accepted is not None and name not in accepted:
                continue
            if not _is_unset(params.get(name)):
                # The author typed something for this parameter; their value
                # wins over the profile's.
                continue
            params[name] = {"value": value, "type": "any"}
            injected.append(name)

        # Names only. The values are credentials.
        logger.info(
            "Connector %s using profile '%s' for parameters: %s",
            operator_identifier,
            profile_name,
            ", ".join(sorted(injected)) or "(none)",
        )
        return original_call_connector(cls, operator_identifier, params, spiff_task)

    ServiceTaskDelegate.call_connector = patched_call_connector  # type: ignore[assignment]
    _PATCHED = True
