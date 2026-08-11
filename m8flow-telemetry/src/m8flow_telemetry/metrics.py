from __future__ import annotations

from typing import Any

from m8flow_telemetry.bootstrap import get_meter, is_telemetry_enabled, tenant_metric_attributes

M8FLOW_TENANT_ID_ATTR = "m8flow_tenant_id"


class DomainMetrics:
    """Lazy domain metric instruments shared across services."""

    def __init__(self) -> None:
        self._initialized = False
        self.process_instance_created = None
        self.process_instance_active = None
        self.process_instance_completed = None
        self.process_instance_terminated = None
        self.task_completed = None
        self.workflow_duration = None
        self.connector_calls = None
        self.connector_duration = None
        self.connector_failures = None
        self.mcp_tool_calls = None
        self.mcp_tool_duration = None
        self.mcp_tool_failures = None
        self.nats_processing_duration = None
        self.nats_processing_failures = None
        self.nats_consumer_lag = None
        self.nats_consumer_redelivered = None
        # Broker-level (per stream / per consumer), fed by a periodic poll of the NATS
        # monitoring endpoints rather than pushed inline with message processing — see
        # record_nats_broker_snapshot. Deliberately no tenant label: JetStream reports
        # this per account, not per tenant, the same reasoning that keeps nats_consumer_lag
        # tenant-free above.
        self.nats_broker_stream_messages = None
        self.nats_broker_stream_bytes = None
        self.nats_broker_consumer_pending = None
        self.nats_broker_consumer_unacked = None
        self.nats_broker_consumer_stream_lag = None
        self.nats_broker_consumer_ack_lag = None
        self.nats_broker_consumer_redelivered = None

    def _ensure_backend(self) -> None:
        if self._initialized or not is_telemetry_enabled():
            return
        meter = get_meter()
        self.process_instance_created = meter.create_counter(
            "process_instance.created",
            description="Process instances created",
        )
        self.process_instance_active = meter.create_up_down_counter(
            "process_instance.active",
            description="Active process instances",
        )
        self.process_instance_completed = meter.create_counter(
            "process_instance.completed",
            description="Process instances completed",
        )
        self.process_instance_terminated = meter.create_counter(
            "process_instance.terminated",
            description="Process instances terminated",
        )
        self.task_completed = meter.create_counter(
            "task.completed",
            description="Human/service tasks completed",
        )
        self.workflow_duration = meter.create_histogram(
            "workflow.execution.duration",
            unit="ms",
            description="Workflow execution duration",
        )
        self._initialized = True

    def _ensure_connector(self) -> None:
        if self.connector_calls is not None or not is_telemetry_enabled():
            return
        meter = get_meter()
        self.connector_calls = meter.create_counter(
            "connector.calls",
            description="Connector proxy invocations",
        )
        self.connector_duration = meter.create_histogram(
            "connector.call.duration",
            unit="ms",
            description="Connector call duration",
        )
        self.connector_failures = meter.create_counter(
            "connector.call.failures",
            description="Connector call failures",
        )

    def _ensure_mcp(self) -> None:
        if self.mcp_tool_calls is not None or not is_telemetry_enabled():
            return
        meter = get_meter()
        self.mcp_tool_calls = meter.create_counter("mcp.tool.calls", description="MCP tool calls")
        self.mcp_tool_duration = meter.create_histogram(
            "mcp.tool.duration",
            unit="ms",
            description="MCP tool call duration",
        )
        self.mcp_tool_failures = meter.create_counter(
            "mcp.tool.failures",
            description="MCP tool call failures",
        )

    def _ensure_nats(self) -> None:
        if self.nats_processing_duration is not None or not is_telemetry_enabled():
            return
        meter = get_meter()
        self.nats_processing_duration = meter.create_histogram(
            "nats.consumer.processing.duration",
            unit="ms",
            description="NATS message processing duration",
        )
        self.nats_processing_failures = meter.create_counter(
            "nats.consumer.processing.failures",
            description="NATS message processing failures",
        )
        self.nats_consumer_lag = meter.create_gauge(
            "nats.consumer.lag",
            description="JetStream pending messages for consumer",
        )
        self.nats_consumer_redelivered = meter.create_gauge(
            "nats.consumer.redelivered",
            description="JetStream redelivered-message count for consumer",
        )
        self.nats_broker_stream_messages = meter.create_gauge(
            "nats.broker.stream.messages",
            description="JetStream stream message count, labeled by stream",
        )
        self.nats_broker_stream_bytes = meter.create_gauge(
            "nats.broker.stream.bytes",
            description="JetStream stream byte count, labeled by stream",
        )
        self.nats_broker_consumer_pending = meter.create_gauge(
            "nats.broker.consumer.pending",
            description="Undelivered messages owed to this consumer (num_pending)",
        )
        self.nats_broker_consumer_unacked = meter.create_gauge(
            "nats.broker.consumer.unacked",
            description="Delivered but not yet acknowledged (num_ack_pending)",
        )
        self.nats_broker_consumer_stream_lag = meter.create_gauge(
            "nats.broker.consumer.stream_lag",
            description="Sequence distance from the stream head; overstates backlog for a "
            "filtered consumer, see nats.broker.consumer.pending for the honest figure",
        )
        self.nats_broker_consumer_ack_lag = meter.create_gauge(
            "nats.broker.consumer.ack_lag",
            description="Delivered-but-unacked count, by sequence distance to the ack floor",
        )
        self.nats_broker_consumer_redelivered = meter.create_gauge(
            "nats.broker.consumer.redelivered",
            description="JetStream redelivered-message count, labeled by stream and consumer",
        )


domain_metrics = DomainMetrics()


def record_process_instance_created(tenant_id: str | None, *, outcome: str = "created") -> None:
    domain_metrics._ensure_backend()
    if domain_metrics.process_instance_created is None:
        return
    attrs = tenant_metric_attributes(tenant_id)
    domain_metrics.process_instance_created.add(1, {**attrs, "outcome": outcome})


def record_process_instance_active_delta(tenant_id: str | None, delta: int) -> None:
    domain_metrics._ensure_backend()
    if domain_metrics.process_instance_active is None:
        return
    domain_metrics.process_instance_active.add(delta, tenant_metric_attributes(tenant_id))


def record_process_instance_terminal(tenant_id: str | None, *, outcome: str) -> None:
    domain_metrics._ensure_backend()
    attrs = tenant_metric_attributes(tenant_id)
    if outcome == "completed" and domain_metrics.process_instance_completed is not None:
        domain_metrics.process_instance_completed.add(1, attrs)
    elif outcome == "terminated" and domain_metrics.process_instance_terminated is not None:
        domain_metrics.process_instance_terminated.add(1, attrs)
    record_process_instance_active_delta(tenant_id, -1)


def record_task_completed(tenant_id: str | None, *, task_type: str) -> None:
    domain_metrics._ensure_backend()
    if domain_metrics.task_completed is None:
        return
    domain_metrics.task_completed.add(1, {**tenant_metric_attributes(tenant_id), "task_type": task_type})


def record_workflow_duration_ms(tenant_id: str | None, duration_ms: float) -> None:
    domain_metrics._ensure_backend()
    if domain_metrics.workflow_duration is None:
        return
    domain_metrics.workflow_duration.record(duration_ms, tenant_metric_attributes(tenant_id))


def record_connector_call(
    tenant_id: str | None,
    *,
    connector: str,
    duration_ms: float,
    failed: bool,
) -> None:
    domain_metrics._ensure_connector()
    attrs = {**tenant_metric_attributes(tenant_id), "connector": connector}
    if domain_metrics.connector_calls is not None:
        domain_metrics.connector_calls.add(1, attrs)
    if domain_metrics.connector_duration is not None:
        domain_metrics.connector_duration.record(duration_ms, attrs)
    if failed and domain_metrics.connector_failures is not None:
        domain_metrics.connector_failures.add(1, attrs)


def record_mcp_tool_call(
    tenant_id: str | None,
    *,
    tool_name: str,
    transport: str,
    duration_ms: float,
    failed: bool,
) -> None:
    domain_metrics._ensure_mcp()
    attrs = {
        **tenant_metric_attributes(tenant_id),
        "tool_name": tool_name,
        "transport": transport,
    }
    if domain_metrics.mcp_tool_calls is not None:
        domain_metrics.mcp_tool_calls.add(1, attrs)
    if domain_metrics.mcp_tool_duration is not None:
        domain_metrics.mcp_tool_duration.record(duration_ms, attrs)
    if failed and domain_metrics.mcp_tool_failures is not None:
        domain_metrics.mcp_tool_failures.add(1, attrs)


def record_nats_processing(
    tenant_id: str | None, *, duration_ms: float, failed: bool, outcome: str | None = None
) -> None:
    """Record one message's processing duration and, on failure, count it.

    ``outcome`` is additive and optional so existing call sites stay valid without it; when
    given (e.g. "instantiated", "rejected_auth" — the same values recorded in the
    m8flow_nats_event_audit table) it lands as a Prometheus label, which is what makes
    "failures by reason" chartable/alertable directly from Grafana without querying that
    table. Mirrors the existing ``outcome: str = "created"`` parameter on
    record_process_instance_created above — not a new idiom.
    """
    domain_metrics._ensure_nats()
    attrs = tenant_metric_attributes(tenant_id)
    if outcome is not None:
        attrs = {**attrs, "outcome": outcome}
    if domain_metrics.nats_processing_duration is not None:
        domain_metrics.nats_processing_duration.record(duration_ms, attrs)
    if failed and domain_metrics.nats_processing_failures is not None:
        domain_metrics.nats_processing_failures.add(1, attrs)


def set_nats_consumer_lag(pending: int) -> None:
    domain_metrics._ensure_nats()
    if domain_metrics.nats_consumer_lag is None:
        return
    domain_metrics.nats_consumer_lag.set(pending, {})


def set_nats_consumer_redelivered(count: int) -> None:
    domain_metrics._ensure_nats()
    if domain_metrics.nats_consumer_redelivered is None:
        return
    domain_metrics.nats_consumer_redelivered.set(count, {})


def record_nats_broker_snapshot(streams: list[dict[str, Any]]) -> None:
    """Emit broker-level stream/consumer gauges from a NatsMonitoringService.streams()
    ``["streams"]`` list.

    Takes plain dicts rather than importing m8flow_backend's service directly, so this
    package gains no dependency on m8flow_backend/httpx — the caller (m8flow-nats-consumer)
    already depends on both and does the fetching.

    Internal JetStream plumbing (KV buckets / object stores, surfaced by the broker as
    ordinary ``KV_``/``OBJ_``-prefixed streams) is skipped, matching the same policy the live
    NATS monitoring dashboard already applies via ``stream_is_internal()`` — one decision,
    not two independently-drifting ones.
    """
    domain_metrics._ensure_nats()
    if domain_metrics.nats_broker_stream_messages is None:
        return

    for stream in streams:
        if stream.get("isInternal"):
            continue

        stream_name = stream.get("name") or "unknown"
        stream_attrs = {"stream": stream_name}
        domain_metrics.nats_broker_stream_messages.set(stream.get("messages") or 0, stream_attrs)
        domain_metrics.nats_broker_stream_bytes.set(stream.get("bytes") or 0, stream_attrs)

        for consumer in stream.get("consumers") or []:
            consumer_attrs = {"stream": stream_name, "consumer": consumer.get("name") or "unknown"}
            domain_metrics.nats_broker_consumer_pending.set(consumer.get("pending") or 0, consumer_attrs)
            domain_metrics.nats_broker_consumer_unacked.set(consumer.get("unacked") or 0, consumer_attrs)
            domain_metrics.nats_broker_consumer_stream_lag.set(
                consumer.get("streamLag") or 0, consumer_attrs
            )
            domain_metrics.nats_broker_consumer_ack_lag.set(consumer.get("ackLag") or 0, consumer_attrs)
            domain_metrics.nats_broker_consumer_redelivered.set(
                consumer.get("redelivered") or 0, consumer_attrs
            )
