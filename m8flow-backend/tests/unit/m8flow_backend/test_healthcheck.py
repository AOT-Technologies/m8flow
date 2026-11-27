from __future__ import annotations

from m8flow_backend import healthcheck


def test_healthcheck_reports_invalid_api_version_clearly_without_request(
    monkeypatch, capsys
):
    monkeypatch.setenv("M8FLOW_API_VERSION", "v2.0")
    monkeypatch.setattr(
        healthcheck.client,
        "HTTPConnection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid config must fail before the HTTP request")
        ),
    )

    assert healthcheck.check_backend_health() == 2
    output = capsys.readouterr()
    assert "Healthcheck configuration error" in output.err
    assert "Unsupported M8FLOW_API_VERSION 'v2.0'" in output.err
    assert "1.0, 2.0" in output.err
    assert "Traceback" not in output.err


def test_healthcheck_uses_v1_for_empty_config_and_reports_connection_failure(
    monkeypatch, capsys
):
    monkeypatch.setenv("M8FLOW_API_VERSION", "")
    calls = []

    class OfflineConnection:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def request(self, method, path):
            calls.append((method, path))
            raise OSError("offline")

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(
        healthcheck.client, "HTTPConnection", OfflineConnection
    )

    assert healthcheck.check_backend_health() == 1
    assert "127.0.0.1:6840/v1.0/healthy" in capsys.readouterr().err
    assert calls == [
        ("connect", "127.0.0.1", 6840, 5),
        ("GET", "/v1.0/healthy"),
        ("close",),
    ]


def test_healthcheck_uses_configured_v2_route(monkeypatch):
    calls = []

    class HealthyResponse:
        status = 200

    class HealthyConnection:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def request(self, method, path):
            calls.append((method, path))

        def getresponse(self):
            return HealthyResponse()

        def close(self):
            calls.append(("close",))

    monkeypatch.setenv("M8FLOW_API_VERSION", "2.0")
    monkeypatch.setenv("M8FLOW_BACKEND_PORT", "6841")
    monkeypatch.setattr(
        healthcheck.client, "HTTPConnection", HealthyConnection
    )

    assert healthcheck.check_backend_health() == 0
    assert calls == [
        ("connect", "127.0.0.1", 6841, 5),
        ("GET", "/v2.0/healthy"),
        ("close",),
    ]


def test_healthcheck_rejects_invalid_port_without_connecting(monkeypatch, capsys):
    monkeypatch.setenv("M8FLOW_BACKEND_PORT", "file:///etc/passwd")
    monkeypatch.setattr(
        healthcheck.client,
        "HTTPConnection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid port must fail before connecting")
        ),
    )

    assert healthcheck.check_backend_health() == 2
    assert "M8FLOW_BACKEND_PORT must be an integer" in capsys.readouterr().err
