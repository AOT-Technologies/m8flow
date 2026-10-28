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

import pytest

from m8flow_backend import config

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
        "M8FLOW_BACKEND_CELERY_ENABLED",
        "M8FLOW_BACKEND_CELERY_MONITORING_ENABLED",
        "M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED",
        "M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS",
        "M8FLOW_BACKEND_CELERY_CONTROL_ENABLED",
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


class TestCeleryMonitoringFollowsCeleryEnabled:
    """Same inheritance as NATS monitoring, keyed on M8FLOW_BACKEND_CELERY_ENABLED."""

    @pytest.mark.parametrize("celery_value,expected", [("true", True), ("false", False)])
    def test_unset_inherits_from_celery_enabled(self, monkeypatch, celery_value, expected) -> None:
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_ENABLED", celery_value)
        assert config.celery_monitoring_enabled() is expected

    def test_unset_everywhere_is_off(self) -> None:
        assert config.celery_monitoring_enabled() is False

    def test_an_explicit_value_overrides_the_inheritance(self, monkeypatch) -> None:
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_ENABLED", "true")
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", "false")
        assert config.celery_monitoring_enabled() is False

    def test_empty_string_inherits_rather_than_disabling(self, monkeypatch) -> None:
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_ENABLED", "true")
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", "")
        assert config.celery_monitoring_enabled() is True

    @pytest.mark.parametrize("value", FALSEY)
    def test_a_typo_fails_closed(self, monkeypatch, value) -> None:
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", value)
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_ENABLED", "true")
        assert config.celery_monitoring_enabled() is False


class TestCeleryHistoryAndControlFollowMonitoring:
    @pytest.mark.parametrize("reader", [config.celery_task_history_enabled, config.celery_control_enabled])
    @pytest.mark.parametrize("monitoring,expected", [("true", True), ("false", False)])
    def test_unset_inherits_from_monitoring(self, monkeypatch, reader, monitoring, expected) -> None:
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", monitoring)
        assert reader() is expected

    @pytest.mark.parametrize(
        "name,reader",
        [
            ("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED", config.celery_task_history_enabled),
            ("M8FLOW_BACKEND_CELERY_CONTROL_ENABLED", config.celery_control_enabled),
        ],
    )
    def test_each_can_be_turned_off_on_its_own(self, monkeypatch, name, reader) -> None:
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", "true")
        monkeypatch.setenv(name, "false")
        assert reader() is False

    def test_worker_state_db_is_off_unless_a_path_is_set(self, monkeypatch) -> None:
        assert config.celery_worker_state_db() is None
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_WORKER_STATE_DB", " /var/lib/m8flow/celery/worker.state ")
        assert config.celery_worker_state_db() == "/var/lib/m8flow/celery/worker.state"

    def test_retention_defaults_to_seven_days(self, monkeypatch) -> None:
        assert config.celery_task_history_retention_days() == 7
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS", "30")
        assert config.celery_task_history_retention_days() == 30

    def test_retention_handles_invalid_values_defensively(self, monkeypatch, caplog) -> None:
        import logging

        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS", "invalid-number")
        with caplog.at_level(logging.WARNING):
            assert config.celery_task_history_retention_days() == 7
        assert "Invalid M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS" in caplog.text

        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS", "12.5")
        with caplog.at_level(logging.WARNING):
            assert config.celery_task_history_retention_days() == 7
