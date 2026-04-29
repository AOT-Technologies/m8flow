import importlib


def _reload_sequence_module():
    # Keep tests isolated from other tests that import sequence.
    import extensions.startup.sequence as sequence

    return importlib.reload(sequence)


def test_wrap_asgi_skips_proxy_fix_in_testing_env(monkeypatch):
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "testing")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_PROXY_COUNT_FOR_PROXY_FIX", "2")

    sequence = _reload_sequence_module()

    cnx_app = object()
    wrapped = sequence._wrap_asgi_if_needed(cnx_app)
    assert wrapped is cnx_app


def test_wrap_asgi_no_proxy_fix_when_count_zero(monkeypatch):
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_PROXY_COUNT_FOR_PROXY_FIX", "0")

    sequence = _reload_sequence_module()

    cnx_app = object()
    wrapped = sequence._wrap_asgi_if_needed(cnx_app)

    # Outer wrapper always sets tenant context in non-test envs.
    assert wrapped.__class__.__name__ == "AsgiTenantContextMiddleware"
    assert wrapped.app is cnx_app


def test_wrap_asgi_adds_proxy_fix_when_count_set(monkeypatch):
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_PROXY_COUNT_FOR_PROXY_FIX", "2")

    sequence = _reload_sequence_module()

    cnx_app = object()
    wrapped = sequence._wrap_asgi_if_needed(cnx_app)

    assert wrapped.__class__.__name__ == "AsgiTenantContextMiddleware"
    proxy_fix = wrapped.app
    assert proxy_fix.__class__.__name__ == "ASGIProxyFix"
    assert proxy_fix.app is cnx_app

    assert proxy_fix.x_for == 2
    assert proxy_fix.x_proto == 2
    assert proxy_fix.x_host == 2
    assert proxy_fix.x_port == 2
    assert proxy_fix.x_prefix == 2
