"""Unit tests for m8flow_telemetry.metrics.

Tests cover:
- record_nats_broker_snapshot: skips isInternal (KV_/OBJ_) streams; stream and consumer
  attrs land on the right gauges with the right labels; missing numeric fields default to 0
  rather than raising.
- record_nats_processing: the new `outcome` label is additive -- absent when not passed
  (existing call sites stay valid), present and correct when passed.
- Both are no-ops when telemetry is disabled, matching every other recorder in this module.

Each test gets a fresh DomainMetrics() via monkeypatch rather than sharing the module-level
singleton, so instrument creation in one test cannot leak into another and make results
order-dependent.
"""

from __future__ import annotations

import pytest

import m8flow_telemetry.metrics as metrics_module
from m8flow_telemetry.metrics import (
    DomainMetrics,
    record_nats_broker_snapshot,
    record_nats_processing,
    set_nats_consumer_redelivered,
)


class FakeInstrument:
    """Records every .set()/.add()/.record() call as (value, attrs) for assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, dict]] = []

    def set(self, value, attrs=None):
        self.calls.append((value, dict(attrs or {})))

    def add(self, value, attrs=None):
        self.calls.append((value, dict(attrs or {})))

    def record(self, value, attrs=None):
        self.calls.append((value, dict(attrs or {})))


class FakeMeter:
    def __init__(self) -> None:
        self.instruments: dict[str, FakeInstrument] = {}

    def _make(self, name: str, **_kwargs) -> FakeInstrument:
        instrument = FakeInstrument()
        self.instruments[name] = instrument
        return instrument

    def create_gauge(self, name, **kwargs):
        return self._make(name, **kwargs)

    def create_counter(self, name, **kwargs):
        return self._make(name, **kwargs)

    def create_up_down_counter(self, name, **kwargs):
        return self._make(name, **kwargs)

    def create_histogram(self, name, **kwargs):
        return self._make(name, **kwargs)


@pytest.fixture
def fresh_metrics(monkeypatch):
    """Telemetry enabled, a fresh DomainMetrics(), and a fake meter to inspect."""
    fake_meter = FakeMeter()
    monkeypatch.setattr(metrics_module, "domain_metrics", DomainMetrics())
    monkeypatch.setattr(metrics_module, "is_telemetry_enabled", lambda: True)
    monkeypatch.setattr(metrics_module, "get_meter", lambda: fake_meter)
    return fake_meter


@pytest.fixture
def disabled_metrics(monkeypatch):
    """Telemetry disabled -- every recorder must be a safe no-op."""
    monkeypatch.setattr(metrics_module, "domain_metrics", DomainMetrics())
    monkeypatch.setattr(metrics_module, "is_telemetry_enabled", lambda: False)

    def _fail_if_called():
        raise AssertionError("get_meter() must not be called while telemetry is disabled")

    monkeypatch.setattr(metrics_module, "get_meter", _fail_if_called)
    return None


STREAMS = [
    {
        "name": "M8FLOW_EVENTS",
        "isInternal": False,
        "messages": 33,
        "bytes": 17902,
        "consumers": [
            {
                "name": "m8flow-engine-consumer",
                "pending": 3,
                "unacked": 2,
                "streamLag": 3,
                "ackLag": 2,
                "redelivered": 0,
            }
        ],
    },
    {
        "name": "KV_m8flow-dedup",
        "isInternal": True,
        "messages": 0,
        "bytes": 0,
        "consumers": [],
    },
]


class TestRecordNatsBrokerSnapshot:
    def test_skips_internal_streams(self, fresh_metrics):
        record_nats_broker_snapshot(STREAMS)

        stream_calls = fresh_metrics.instruments["nats.broker.stream.messages"].calls
        assert len(stream_calls) == 1
        assert stream_calls[0] == (33, {"stream": "M8FLOW_EVENTS"})

    def test_stream_attrs_land_on_the_right_gauges(self, fresh_metrics):
        record_nats_broker_snapshot(STREAMS)

        assert fresh_metrics.instruments["nats.broker.stream.bytes"].calls == [
            (17902, {"stream": "M8FLOW_EVENTS"})
        ]

    def test_consumer_attrs_carry_both_stream_and_consumer_labels(self, fresh_metrics):
        record_nats_broker_snapshot(STREAMS)

        expected_attrs = {"stream": "M8FLOW_EVENTS", "consumer": "m8flow-engine-consumer"}
        assert fresh_metrics.instruments["nats.broker.consumer.pending"].calls == [
            (3, expected_attrs)
        ]
        assert fresh_metrics.instruments["nats.broker.consumer.unacked"].calls == [
            (2, expected_attrs)
        ]
        assert fresh_metrics.instruments["nats.broker.consumer.stream_lag"].calls == [
            (3, expected_attrs)
        ]
        assert fresh_metrics.instruments["nats.broker.consumer.ack_lag"].calls == [
            (2, expected_attrs)
        ]
        assert fresh_metrics.instruments["nats.broker.consumer.redelivered"].calls == [
            (0, expected_attrs)
        ]

    def test_a_stream_with_no_consumers_emits_no_consumer_series(self, fresh_metrics):
        record_nats_broker_snapshot([{"name": "EMPTY", "isInternal": False, "consumers": []}])

        assert fresh_metrics.instruments["nats.broker.consumer.pending"].calls == []

    def test_missing_numeric_fields_default_to_zero_rather_than_raising(self, fresh_metrics):
        record_nats_broker_snapshot(
            [{"name": "SPARSE", "isInternal": False, "consumers": [{"name": "c"}]}]
        )

        assert fresh_metrics.instruments["nats.broker.stream.messages"].calls == [
            (0, {"stream": "SPARSE"})
        ]
        assert fresh_metrics.instruments["nats.broker.consumer.pending"].calls == [
            (0, {"stream": "SPARSE", "consumer": "c"})
        ]

    def test_an_empty_list_is_a_safe_no_op(self, fresh_metrics):
        record_nats_broker_snapshot([])  # must not raise

    def test_is_a_no_op_when_telemetry_is_disabled(self, disabled_metrics):
        record_nats_broker_snapshot(STREAMS)  # must not call get_meter() -- see fixture


class TestRecordNatsProcessingOutcomeLabel:
    def test_outcome_is_absent_when_not_passed(self, fresh_metrics):
        """Existing call sites (no outcome kwarg) must keep working unchanged."""
        record_nats_processing("tenant-1", duration_ms=12.5, failed=False)

        value, attrs = fresh_metrics.instruments["nats.consumer.processing.duration"].calls[0]
        assert value == 12.5
        assert "outcome" not in attrs

    def test_outcome_label_reaches_the_duration_histogram(self, fresh_metrics):
        record_nats_processing("tenant-1", duration_ms=5.0, failed=True, outcome="rejected_auth")

        _, attrs = fresh_metrics.instruments["nats.consumer.processing.duration"].calls[0]
        assert attrs["outcome"] == "rejected_auth"

    def test_outcome_label_also_reaches_the_failure_counter(self, fresh_metrics):
        record_nats_processing("tenant-1", duration_ms=5.0, failed=True, outcome="rejected_auth")

        _, attrs = fresh_metrics.instruments["nats.consumer.processing.failures"].calls[0]
        assert attrs["outcome"] == "rejected_auth"

    def test_a_successful_outcome_is_still_labeled_without_incrementing_failures(
        self, fresh_metrics
    ):
        record_nats_processing("tenant-1", duration_ms=5.0, failed=False, outcome="instantiated")

        assert fresh_metrics.instruments["nats.consumer.processing.failures"].calls == []
        _, attrs = fresh_metrics.instruments["nats.consumer.processing.duration"].calls[0]
        assert attrs["outcome"] == "instantiated"

    def test_tenant_attribute_survives_alongside_the_new_label(self, fresh_metrics):
        record_nats_processing("tenant-1", duration_ms=5.0, failed=False, outcome="instantiated")

        _, attrs = fresh_metrics.instruments["nats.consumer.processing.duration"].calls[0]
        assert attrs["m8flow_tenant_id"] == "tenant-1"
        assert attrs["outcome"] == "instantiated"


class TestSetNatsConsumerRedelivered:
    def test_sets_the_gauge_with_no_labels(self, fresh_metrics):
        set_nats_consumer_redelivered(4)

        assert fresh_metrics.instruments["nats.consumer.redelivered"].calls == [(4, {})]

    def test_is_a_no_op_when_telemetry_is_disabled(self, disabled_metrics):
        set_nats_consumer_redelivered(4)  # must not call get_meter() -- see fixture
