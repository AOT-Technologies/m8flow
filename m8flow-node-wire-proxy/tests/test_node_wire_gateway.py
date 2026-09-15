# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from m8flow_node_wire_proxy.node_wire_gateway import (
    ensure_allowed_connectors,
    get_http_generic_connector,
    get_ssrf_gate,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NW_ALLOWED_CONNECTORS", raising=False)


def test_ensure_allowed_connectors_sets_default_when_unset() -> None:
    ensure_allowed_connectors()
    assert os.environ["NW_ALLOWED_CONNECTORS"] == "http_generic"


def test_ensure_allowed_connectors_does_not_override_operator_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NW_ALLOWED_CONNECTORS", "http_generic,custom")
    ensure_allowed_connectors()
    assert os.environ["NW_ALLOWED_CONNECTORS"] == "http_generic,custom"


def test_get_http_generic_connector_returns_a_class() -> None:
    connector_cls = get_http_generic_connector()
    assert isinstance(connector_cls, type)
    assert os.environ["NW_ALLOWED_CONNECTORS"] == "http_generic"


def test_get_ssrf_gate_returns_none_when_unavailable() -> None:
    with patch.dict("sys.modules", {"node_wire_http_generic.logic": None}):
        assert get_ssrf_gate() is None


def test_get_ssrf_gate_returns_callable_and_exception_type_when_available() -> None:
    gate = get_ssrf_gate()
    assert gate is not None
    assert_safe_destination, ssrf_blocked_error = gate
    assert callable(assert_safe_destination)
    assert isinstance(ssrf_blocked_error, type) and issubclass(ssrf_blocked_error, Exception)
