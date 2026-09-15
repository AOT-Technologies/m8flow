from __future__ import annotations

from flask import Flask

from m8flow_backend.startup.telemetry_setup import install_telemetry


def test_install_telemetry_is_inert_when_otel_disabled(monkeypatch):
    """Default/CI posture: OTEL_SDK_DISABLED or no endpoint set -> no export,
    and app creation must still succeed."""
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    app = Flask(__name__)
    assert install_telemetry(app) is False


def test_install_telemetry_never_raises_on_misconfiguration(monkeypatch):
    """A bad OTLP endpoint (or any bootstrap failure) must degrade to "no
    telemetry", not take the backend down."""

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated telemetry bootstrap failure")

    monkeypatch.setattr("m8flow_telemetry.bootstrap.setup", _boom)
    app = Flask(__name__)
    assert install_telemetry(app) is False
