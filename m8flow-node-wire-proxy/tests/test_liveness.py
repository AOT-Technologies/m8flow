# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from m8flow_node_wire_proxy.app import app


def test_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/liveness")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
