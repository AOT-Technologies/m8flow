"""Behaviour of the NATS environment flags in m8flow_backend.config.

These flags decide whether a monitoring surface exists and whether raw tenant payloads may
be read, so how a value is parsed is a security-relevant decision rather than a formatting
one. Two properties are locked in here:

- the accepted vocabulary is the same for every flag, so an operator who writes ``yes`` in
  one place and ``true`` in another gets the same result either way;
- anything outside that vocabulary is false. A typo must fail closed and leave a feature
  off, never fall through to enabled.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

extension_root = Path(__file__).resolve().parents[3]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend import config  # noqa: E402

TRUTHY = ["true", "True", "TRUE", "  true  ", "1", "yes", "YES", "on", "On"]
FALSEY = ["false", "False", "0", "no", "off", "  ", "tru", "true!", "enabled", "y", "t"]

NATS_FLAGS = [
    ("M8FLOW_NATS_ENABLED", config.nats_enabled),
    ("M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED", config.nats_message_inspection_enabled),
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No flag leaks in from the ambient environment."""
    for name in (
        "M8FLOW_NATS_ENABLED",
        "M8FLOW_NATS_MONITORING_ENABLED",
        "M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


class TestAcceptedSpellings:
    @pytest.mark.parametrize("name,reader", NATS_FLAGS, ids=[n for n, _ in NATS_FLAGS])
    @pytest.mark.parametrize("value", TRUTHY)
    def test_truthy_spellings_enable(self, monkeypatch, name, reader, value) -> None:
        monkeypatch.setenv(name, value)
        assert reader() is True

    @pytest.mark.parametrize("name,reader", NATS_FLAGS, ids=[n for n, _ in NATS_FLAGS])
    @pytest.mark.parametrize("value", FALSEY)
    def test_everything_else_fails_closed(self, monkeypatch, name, reader, value) -> None:
        monkeypatch.setenv(name, value)
        assert reader() is False

    @pytest.mark.parametrize("name,reader", NATS_FLAGS, ids=[n for n, _ in NATS_FLAGS])
    def test_unset_is_off(self, name, reader) -> None:
        assert reader() is False


class TestMonitoringFollowsNatsEnabled:
    """Monitoring a disabled subsystem is never useful, so the flag inherits by default."""

    @pytest.mark.parametrize("nats_value,expected", [("true", True), ("false", False)])
    def test_unset_inherits_from_nats_enabled(self, monkeypatch, nats_value, expected) -> None:
        monkeypatch.setenv("M8FLOW_NATS_ENABLED", nats_value)
        assert config.nats_monitoring_enabled() is expected

    def test_empty_string_inherits_rather_than_disabling(self, monkeypatch) -> None:
        """`FOO=` in a .env reads as "unspecified", not as "off"."""
        monkeypatch.setenv("M8FLOW_NATS_ENABLED", "true")
        monkeypatch.setenv("M8FLOW_NATS_MONITORING_ENABLED", "")
        assert config.nats_monitoring_enabled() is True

    def test_an_explicit_value_overrides_the_inheritance(self, monkeypatch) -> None:
        monkeypatch.setenv("M8FLOW_NATS_ENABLED", "true")
        monkeypatch.setenv("M8FLOW_NATS_MONITORING_ENABLED", "false")
        assert config.nats_monitoring_enabled() is False

    def test_monitoring_can_be_enabled_on_its_own(self, monkeypatch) -> None:
        """Deliberately allowed: the dashboard reads a broker this deployment does not publish to."""
        monkeypatch.setenv("M8FLOW_NATS_ENABLED", "false")
        monkeypatch.setenv("M8FLOW_NATS_MONITORING_ENABLED", "yes")
        assert config.nats_monitoring_enabled() is True
