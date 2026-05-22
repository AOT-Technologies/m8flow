# m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_scoping_writes.py
from __future__ import annotations

from flask import Flask, g

from m8flow_backend.services.tenant_scoping_patch import _locked_tenant_id_for_writes
from m8flow_backend.services.tenant_scoping_patch import _set_tenant_on_flush
from m8flow_backend.tenancy import clear_tenant_context, set_context_tenant_id


def test_locked_tenant_id_prefers_g_over_context(app: Flask) -> None:
    token = set_context_tenant_id("ctx")
    try:
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "from-g"
            assert _locked_tenant_id_for_writes() == "from-g"
    finally:
        from m8flow_backend.tenancy import reset_context_tenant_id

        reset_context_tenant_id(token)
        clear_tenant_context()


def test_locked_tenant_id_uses_context_when_no_g_tenant(app: Flask) -> None:
    token = set_context_tenant_id("ctx-only")
    try:
        with app.test_request_context("/"):
            if hasattr(g, "m8flow_tenant_id"):
                delattr(g, "m8flow_tenant_id")
            assert _locked_tenant_id_for_writes() == "ctx-only"
    finally:
        from m8flow_backend.tenancy import reset_context_tenant_id

        reset_context_tenant_id(token)
        clear_tenant_context()


def test_set_tenant_on_flush_exempt_with_locked_tenant_sets_m8f(app: Flask) -> None:
    class Ent:
        m8f_tenant_id = None

    ent = Ent()

    class FakeSession:
        new = {ent}

    with app.test_request_context("/"):
        g._m8flow_tenant_context_exempt_request = True
        g.m8flow_tenant_id = "tenant-locked"
        _set_tenant_on_flush(FakeSession(), None, None)  # type: ignore[arg-type]
        assert ent.m8f_tenant_id == "tenant-locked"


def test_set_tenant_on_flush_exempt_without_lock_skips(app: Flask) -> None:
    class Ent:
        m8f_tenant_id = None

    ent = Ent()

    class FakeSession:
        new = {ent}

    with app.test_request_context("/"):
        g._m8flow_tenant_context_exempt_request = True
        if hasattr(g, "m8flow_tenant_id"):
            delattr(g, "m8flow_tenant_id")
        clear_tenant_context()
        _set_tenant_on_flush(FakeSession(), None, None)  # type: ignore[arg-type]
        assert ent.m8f_tenant_id is None
