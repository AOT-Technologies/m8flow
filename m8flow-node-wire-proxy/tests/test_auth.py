# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from m8flow_node_wire_proxy.auth import (
    ALLOW_UNAUTHENTICATED_ENV,
    API_KEY_ENV,
    API_KEY_HEADER,
    require_api_key_at_startup,
)


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv(ALLOW_UNAUTHENTICATED_ENV, raising=False)
    monkeypatch.setenv(API_KEY_ENV, "test-connector-proxy-key")
    from m8flow_node_wire_proxy.app import create_app

    with TestClient(create_app()) as client:
        yield client


def test_require_api_key_at_startup_fails_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.delenv(ALLOW_UNAUTHENTICATED_ENV, raising=False)
    with pytest.raises(RuntimeError, match=API_KEY_ENV):
        require_api_key_at_startup()


def test_liveness_remains_public(authed_client: TestClient) -> None:
    response = authed_client.get("/liveness")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_commands_rejects_missing_api_key(authed_client: TestClient) -> None:
    response = authed_client.get("/v1/commands")
    assert response.status_code == 401


def test_commands_accepts_valid_api_key(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/v1/commands",
        headers={API_KEY_HEADER: "test-connector-proxy-key"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_do_rejects_wrong_api_key(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/v1/do/http/GetRequestV2",
        headers={API_KEY_HEADER: "wrong-key"},
        json={"url": "https://example.com"},
    )
    assert response.status_code == 401
