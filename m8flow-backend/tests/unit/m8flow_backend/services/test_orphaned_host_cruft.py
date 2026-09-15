"""Ticket 08: overlay host-layer modules with zero callers must stay gone."""

from __future__ import annotations

import importlib

import pytest

_REMOVED = (
    "m8flow_backend.services.asgi_tenant_context_middleware",
    "m8flow_backend.services.cors_fallback_middleware",
    "m8flow_backend.services.celery_worker_runtime",
)


@pytest.mark.parametrize("module", _REMOVED)
def test_orphaned_overlay_host_modules_are_removed(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)
