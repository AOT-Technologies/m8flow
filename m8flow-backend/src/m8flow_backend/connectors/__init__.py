"""Connector definitions: the schema for each connector, in code."""

from m8flow_backend.connectors.base import (
    CONFIG_PARAM,
    PROFILE_BINDINGS,
    SECRET_PARAM,
    TASK_PARAM,
    ConnectorDefinition,
    config_param,
    secret_param,
    secret_ref,
    task_param,
)
from m8flow_backend.connectors.registry import (
    CONNECTOR_REGISTRY,
    all_connectors,
    get_connector,
    register,
)

__all__ = [
    "CONFIG_PARAM",
    "CONNECTOR_REGISTRY",
    "PROFILE_BINDINGS",
    "SECRET_PARAM",
    "TASK_PARAM",
    "ConnectorDefinition",
    "all_connectors",
    "config_param",
    "get_connector",
    "register",
    "secret_param",
    "secret_ref",
    "task_param",
]
