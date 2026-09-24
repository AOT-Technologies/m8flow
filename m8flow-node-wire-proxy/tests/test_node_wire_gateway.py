# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from m8flow_node_wire_proxy.node_wire_gateway import (
    _DEFAULT_ALLOWED_CONNECTORS,
    ensure_allowed_connectors,
    get_http_generic_connector,
    get_m8flow_connector,
    get_ssrf_gate,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NW_ALLOWED_CONNECTORS", raising=False)


def test_ensure_allowed_connectors_sets_default_when_unset() -> None:
    ensure_allowed_connectors()
    assert os.environ["NW_ALLOWED_CONNECTORS"] == _DEFAULT_ALLOWED_CONNECTORS
    # The default must stay fail-closed: an explicit list, never a wildcard.
    assert "http_generic" in _DEFAULT_ALLOWED_CONNECTORS.split(",")


def test_ensure_allowed_connectors_does_not_override_operator_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NW_ALLOWED_CONNECTORS", "http_generic,custom")
    ensure_allowed_connectors()
    assert os.environ["NW_ALLOWED_CONNECTORS"] == "http_generic,custom"


def test_get_http_generic_connector_returns_a_class() -> None:
    connector_cls = get_http_generic_connector()
    assert isinstance(connector_cls, type)
    # The getter sets the allowlist before importing, never after.
    assert os.environ["NW_ALLOWED_CONNECTORS"] == _DEFAULT_ALLOWED_CONNECTORS


def test_get_m8flow_connector_returns_the_class_carrying_that_id() -> None:
    connector_cls = get_m8flow_connector("m8flow_github")
    assert isinstance(connector_cls, type)
    assert connector_cls.connector_id == "m8flow_github"


def test_get_m8flow_connector_raises_import_error_for_an_unknown_id() -> None:
    with pytest.raises(ImportError):
        get_m8flow_connector("m8flow_not_a_connector")


def test_get_ssrf_gate_returns_none_when_unavailable() -> None:
    with patch.dict("sys.modules", {"node_wire_http_generic.logic": None}):
        assert get_ssrf_gate() is None


def test_get_ssrf_gate_returns_callable_and_exception_type_when_available() -> None:
    gate = get_ssrf_gate()
    assert gate is not None
    assert_safe_destination, ssrf_blocked_error = gate
    assert callable(assert_safe_destination)
    assert isinstance(ssrf_blocked_error, type) and issubclass(ssrf_blocked_error, Exception)
