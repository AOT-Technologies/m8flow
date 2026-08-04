"""Unit tests for NatsMonitoringService.

The /jsz and /varz fixtures were captured from a live NATS 2.10 server, so these tests
assert against the broker's real response shape rather than against the documentation.
Three things that capture settled, each locked below:

- ``state.num_deleted`` is absent unless deletions have occurred
- ``consumer_detail[].push_bound`` is null for pull consumers
- KV buckets appear as ordinary ``KV_``-prefixed streams

Tests cover:
- normalize_jsz: stream/consumer flattening, derived lag arithmetic, internal-stream
  flagging, totals that exclude JetStream plumbing
- normalize_varz: health derived from /healthz, counter passthrough
- HTTP failures (timeout, 5xx, non-JSON, disabled) all surfacing as 503, never 500
- message serialization: truncation, base64 for binary, header stringification
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import nats_monitoring_service as module  # noqa: E402
from m8flow_backend.services.nats_monitoring_service import (  # noqa: E402
    NatsMonitoringService,
    stream_is_internal,
)
from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def jsz() -> dict:
    return _fixture("nats_jsz.json")


@pytest.fixture
def varz() -> dict:
    return _fixture("nats_varz.json")


@pytest.fixture
def enabled(monkeypatch):
    """Monitoring switched on and pointed at a stub host."""
    monkeypatch.setattr(module, "nats_monitoring_enabled", lambda: True)
    monkeypatch.setattr(module, "nats_monitoring_url", lambda: "http://nats:8222")


class TestStreamIsInternal:
    def test_flags_kv_and_object_store_streams(self):
        assert stream_is_internal("KV_m8flow-dedup") is True
        assert stream_is_internal("OBJ_uploads") is True

    def test_leaves_event_streams_alone(self):
        assert stream_is_internal("M8FLOW_EVENTS") is False
        assert stream_is_internal("M8FLOW_NOTIFICATIONS") is False

    def test_tolerates_a_missing_name(self):
        assert stream_is_internal(None) is False
        assert stream_is_internal("") is False


class TestNormalizeJsz:
    def test_flattens_streams_from_account_details(self, jsz):
        result = NatsMonitoringService.normalize_jsz(jsz)

        names = {s["name"] for s in result["streams"]}
        assert "M8FLOW_EVENTS" in names
        assert "M8FLOW_NOTIFICATIONS" in names

    def test_derives_stream_lag_from_sequence_distance(self, jsz):
        result = NatsMonitoringService.normalize_jsz(jsz)
        stream = next(s for s in result["streams"] if s["name"] == "M8FLOW_EVENTS")
        consumer = stream["consumers"][0]

        assert consumer["streamLag"] == stream["lastSeq"] - consumer["deliveredStreamSeq"]

    def test_derives_ack_lag_from_the_ack_floor(self, jsz):
        result = NatsMonitoringService.normalize_jsz(jsz)
        consumer = next(
            s for s in result["streams"] if s["name"] == "M8FLOW_EVENTS"
        )["consumers"][0]

        assert consumer["ackLag"] == (
            consumer["deliveredStreamSeq"] - consumer["ackFloorStreamSeq"]
        )

    def test_derived_lag_agrees_with_the_brokers_own_counters(self, jsz):
        """For an unfiltered consumer the broker's num_pending/num_ack_pending and our
        derived sequence arithmetic must agree; if they diverge one of them is wrong."""
        result = NatsMonitoringService.normalize_jsz(jsz)
        for stream in result["streams"]:
            for consumer in stream["consumers"]:
                if consumer["filterSubject"] in (None, "", stream["subjects"]):
                    assert consumer["streamLag"] == consumer["pending"]
                    assert consumer["ackLag"] == consumer["unacked"]

    def test_lag_never_goes_negative(self):
        """A consumer can report a delivered sequence ahead of the snapshot's last_seq,
        because the two counters are not read atomically."""
        payload = {
            "account_details": [
                {
                    "name": "$G",
                    "stream_detail": [
                        {
                            "name": "S",
                            "state": {"last_seq": 5},
                            "consumer_detail": [
                                {
                                    "name": "c",
                                    "delivered": {"stream_seq": 9},
                                    "ack_floor": {"stream_seq": 12},
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        consumer = NatsMonitoringService.normalize_jsz(payload)["streams"][0]["consumers"][0]

        assert consumer["streamLag"] == 0
        assert consumer["ackLag"] == 0

    def test_flags_kv_streams_and_excludes_them_from_totals(self, jsz):
        result = NatsMonitoringService.normalize_jsz(jsz)

        internal = [s for s in result["streams"] if s["isInternal"]]
        assert internal, "fixture should contain the KV_ dedup bucket"
        assert all(s["name"].startswith("KV_") for s in internal)

        assert result["totals"]["internalStreams"] == len(internal)
        assert result["totals"]["streams"] == len(result["streams"]) - len(internal)
        # KV messages must not pad the event-traffic total.
        assert result["totals"]["messages"] == sum(
            s["messages"] for s in result["streams"] if not s["isInternal"]
        )

    def test_internal_streams_sort_last(self, jsz):
        result = NatsMonitoringService.normalize_jsz(jsz)
        flags = [s["isInternal"] for s in result["streams"]]

        assert flags == sorted(flags), "event streams should come before plumbing"

    def test_defaults_num_deleted_when_the_broker_omits_it(self, jsz):
        """The live response has no num_deleted until something is deleted."""
        stream = next(s for s in jsz["account_details"][0]["stream_detail"])
        assert "num_deleted" not in stream["state"]

        result = NatsMonitoringService.normalize_jsz(jsz)
        assert all(s["numDeleted"] == 0 for s in result["streams"])

    def test_tolerates_a_null_push_bound(self, jsz):
        """push_bound is null for pull consumers, which is all m8flow uses."""
        NatsMonitoringService.normalize_jsz(jsz)  # must not raise

    def test_survives_an_empty_response(self):
        result = NatsMonitoringService.normalize_jsz({})

        assert result["streams"] == []
        assert result["totals"]["streams"] == 0
        assert result["totals"]["pending"] == 0

    def test_pending_totals_sum_across_consumers(self, jsz):
        result = NatsMonitoringService.normalize_jsz(jsz)

        assert result["totals"]["pending"] == sum(
            c["pending"]
            for s in result["streams"]
            if not s["isInternal"]
            for c in s["consumers"]
        )


class TestNormalizeVarz:
    def test_reports_healthy_only_when_healthz_says_ok(self, varz):
        assert NatsMonitoringService.normalize_varz(varz, {"status": "ok"})["healthy"] is True
        assert NatsMonitoringService.normalize_varz(varz, {"status": "error"})["healthy"] is False
        assert NatsMonitoringService.normalize_varz(varz, None)["healthy"] is False

    def test_passes_through_counters(self, varz):
        result = NatsMonitoringService.normalize_varz(varz, {"status": "ok"})

        assert result["version"] == varz["version"]
        assert result["inMsgs"] == varz["in_msgs"]
        assert result["outMsgs"] == varz["out_msgs"]
        assert result["slowConsumers"] == varz["slow_consumers"]
        assert result["memoryBytes"] == varz["mem"]

    def test_missing_counters_become_zero_not_none(self):
        result = NatsMonitoringService.normalize_varz({}, {"status": "ok"})

        assert result["inMsgs"] == 0
        assert result["connections"] == 0
        assert result["slowConsumers"] == 0


class TestBrokerFailuresBecome503:
    """A broker that is down must never surface as a 500."""

    def test_timeout(self, enabled, monkeypatch):
        def _timeout(*_a, **_k):
            raise httpx.ConnectTimeout("too slow")

        monkeypatch.setattr(module.httpx, "get", _timeout)

        with pytest.raises(ApiError) as exc:
            NatsMonitoringService.streams()
        assert exc.value.status_code == 503

    def test_connection_refused(self, enabled, monkeypatch):
        def _refused(*_a, **_k):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(module.httpx, "get", _refused)

        with pytest.raises(ApiError) as exc:
            NatsMonitoringService.streams()
        assert exc.value.status_code == 503

    def test_http_error_status(self, enabled, monkeypatch):
        def _server_error(url, **_k):
            request = httpx.Request("GET", url)
            return httpx.Response(500, request=request, json={})

        monkeypatch.setattr(module.httpx, "get", _server_error)

        with pytest.raises(ApiError) as exc:
            NatsMonitoringService.streams()
        assert exc.value.status_code == 503

    def test_non_json_body(self, enabled, monkeypatch):
        """Something other than NATS answering on that port."""

        def _html(url, **_k):
            request = httpx.Request("GET", url)
            return httpx.Response(200, request=request, text="<html>nope</html>")

        monkeypatch.setattr(module.httpx, "get", _html)

        with pytest.raises(ApiError) as exc:
            NatsMonitoringService.streams()
        assert exc.value.status_code == 503

    def test_disabled_monitoring(self, monkeypatch):
        monkeypatch.setattr(module, "nats_monitoring_enabled", lambda: False)

        with pytest.raises(ApiError) as exc:
            NatsMonitoringService.streams()
        assert exc.value.status_code == 503
        assert exc.value.error_code == "nats_monitoring_disabled"


class TestFetchesRealEndpoints:
    def test_streams_asks_for_consumers_and_config(self, enabled, monkeypatch, jsz):
        """Without streams=1&consumers=1 the response carries no detail at all."""
        seen: list[str] = []

        def _capture(url, **_k):
            seen.append(url)
            request = httpx.Request("GET", url)
            return httpx.Response(200, request=request, json=jsz)

        monkeypatch.setattr(module.httpx, "get", _capture)
        NatsMonitoringService.streams()

        assert len(seen) == 1
        assert "streams=1" in seen[0]
        assert "consumers=1" in seen[0]
        assert "config=1" in seen[0]

    def test_overview_still_renders_when_healthz_fails(self, enabled, monkeypatch, varz, jsz):
        """A reachable broker with an unhappy healthz should report status, not collapse."""

        def _route(url, **_k):
            request = httpx.Request("GET", url)
            if "/healthz" in url:
                return httpx.Response(503, request=request, json={})
            if "/jsz" in url:
                return httpx.Response(200, request=request, json=jsz)
            return httpx.Response(200, request=request, json=varz)

        monkeypatch.setattr(module.httpx, "get", _route)
        result = NatsMonitoringService.overview()

        assert result["healthy"] is False
        assert result["status"] == "unknown"
        assert result["version"] == varz["version"]


class _RawMessage:
    def __init__(self, data: bytes, headers: dict | None = None):
        self.data = data
        self.headers = headers or {}
        self.subject = "m8flow.events.acme.trigger"
        self.seq = 7
        self.time = "2026-08-03T10:00:00Z"


class TestSerializeMessage:
    def test_returns_utf8_payloads_as_text(self, monkeypatch):
        monkeypatch.setattr(module, "nats_message_preview_max_bytes", lambda: 4096)

        result = NatsMonitoringService._serialize_message(_RawMessage(b'{"a":1}'), 7)

        assert result["payload"] == '{"a":1}'
        assert result["encoding"] == "utf-8"
        assert result["truncated"] is False
        assert result["sizeBytes"] == 7

    def test_truncates_to_the_preview_cap_and_says_so(self, monkeypatch):
        monkeypatch.setattr(module, "nats_message_preview_max_bytes", lambda: 10)

        result = NatsMonitoringService._serialize_message(_RawMessage(b"x" * 100), 7)

        assert result["truncated"] is True
        assert len(result["payload"]) == 10
        # The reported size is the real one, not the truncated one.
        assert result["sizeBytes"] == 100

    def test_base64_encodes_binary_payloads(self, monkeypatch):
        monkeypatch.setattr(module, "nats_message_preview_max_bytes", lambda: 4096)

        result = NatsMonitoringService._serialize_message(_RawMessage(b"\xff\xfe\x00"), 7)

        assert result["encoding"] == "base64"
        # Must stay JSON-serializable.
        json.dumps(result)

    def test_stringifies_headers(self, monkeypatch):
        monkeypatch.setattr(module, "nats_message_preview_max_bytes", lambda: 4096)

        result = NatsMonitoringService._serialize_message(
            _RawMessage(b"{}", {"Nats-Msg-Id": "abc"}), 7
        )

        assert result["headers"] == {"Nats-Msg-Id": "abc"}
