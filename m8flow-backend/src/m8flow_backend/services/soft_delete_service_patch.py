"""Patch registration entry point for soft-delete service.

This module ensures the soft-delete models are imported and registered with SQLAlchemy
when the patch registry loads. No actual monkey-patching is performed here;
the delete/listing patches live in process_model_service_patch.py.
"""
from __future__ import annotations

import m8flow_backend.models.process_model_deletion  # noqa: F401
import m8flow_backend.models.process_group_deletion  # noqa: F401


def apply(**_kwargs) -> None:
    pass
