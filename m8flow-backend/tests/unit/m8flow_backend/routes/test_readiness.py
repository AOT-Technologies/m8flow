"""DB readiness probe: /v1.0/readyz (and /v1.0/status) vs liveness /ping|/healthy."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError


def test_readyz_and_status_return_200_when_db_is_up(client):
    for path in ("/v1.0/readyz", "/v1.0/status"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_json()
        assert body["ok"] is True
        assert body["healthy"] is True
        assert body["status"] == "ok"


def test_ping_and_healthy_stay_liveness_when_db_is_down(client, monkeypatch):
    """Process-up probes must not depend on a live database."""

    def _boom():
        raise AssertionError("liveness must not open a DB connection")

    monkeypatch.setattr("m8flow_backend.db.get_engine", _boom)
    for path in ("/v1.0/ping", "/v1.0/healthy"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.get_json()["ok"] is True


def test_readyz_and_status_return_503_when_db_unreachable(client, monkeypatch):
    class _DeadEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("refused"))

    monkeypatch.setattr("m8flow_backend.db.get_engine", lambda: _DeadEngine())
    for path in ("/v1.0/readyz", "/v1.0/status"):
        response = client.get(path)
        assert response.status_code == 503
        body = response.get_json()
        assert body["ok"] is False
        assert body["healthy"] is False
