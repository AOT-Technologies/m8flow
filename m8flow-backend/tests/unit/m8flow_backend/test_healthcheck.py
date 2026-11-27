from __future__ import annotations

from urllib import error

from m8flow_backend import healthcheck


def test_healthcheck_reports_invalid_api_version_clearly_without_request(
    monkeypatch, capsys
):
    monkeypatch.setenv("M8FLOW_API_VERSION", "v2.0")
    monkeypatch.setattr(
        healthcheck.request,
        "urlopen",
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
    monkeypatch.setattr(
        healthcheck.request,
        "urlopen",
        lambda url, timeout: (_ for _ in ()).throw(error.URLError("offline")),
    )

    assert healthcheck.check_backend_health() == 1
    assert "http://127.0.0.1:6840/v1.0/healthy" in capsys.readouterr().err


def test_healthcheck_uses_configured_v2_route(monkeypatch):
    calls = []

    class HealthyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setenv("M8FLOW_API_VERSION", "2.0")
    monkeypatch.setenv("M8FLOW_BACKEND_PORT", "6841")
    monkeypatch.setattr(
        healthcheck.request,
        "urlopen",
        lambda url, timeout: (calls.append((url, timeout)) or HealthyResponse()),
    )

    assert healthcheck.check_backend_health() == 0
    assert calls == [("http://127.0.0.1:6841/v2.0/healthy", 5)]
