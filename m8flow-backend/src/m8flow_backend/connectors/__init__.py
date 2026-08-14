"""Code-defined connector schemas.

One module per connector under ``definitions/``, registered in ``registry.py``
and serialized for the UI by ``descriptor.py``.
"""

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    ConnectorField,
    config_param,
    secret_param,
    task_param,
)
from m8flow_backend.connectors.descriptor import all_descriptors, to_descriptor
from m8flow_backend.connectors.registry import all_connectors, get_connector, register

__all__ = [
    "ConnectorDefinition",
    "ConnectorField",
    "all_connectors",
    "all_descriptors",
    "config_param",
    "get_connector",
    "register",
    "secret_param",
    "task_param",
    "to_descriptor",
]
