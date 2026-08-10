from __future__ import annotations

from typing import Mapping, MutableMapping

from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind

TRACER = trace.get_tracer("m8flow.nats")


def inject_trace_context(headers: MutableMapping[str, str] | None) -> dict[str, str]:
    carrier: dict[str, str] = dict(headers or {})
    inject(carrier)
    return carrier


def extract_trace_context(headers: Mapping[str, str] | None):
    if not headers:
        return None
    return extract(dict(headers))


def start_nats_publish_span(subject: str, *, tenant_id: str | None = None):
    attrs = {}
    if tenant_id:
        attrs["m8flow_tenant_id"] = tenant_id
    return TRACER.start_as_current_span(
        "nats.publish",
        kind=SpanKind.PRODUCER,
        attributes={**attrs, "messaging.system": "nats", "messaging.destination.name": subject},
    )


def start_nats_consume_span(subject: str, *, tenant_id: str | None = None, headers: Mapping[str, str] | None = None):
    parent = extract_trace_context(headers)
    attrs = {}
    if tenant_id:
        attrs["m8flow_tenant_id"] = tenant_id
    return TRACER.start_as_current_span(
        "nats.process",
        context=parent,
        kind=SpanKind.CONSUMER,
        attributes={**attrs, "messaging.system": "nats", "messaging.destination.name": subject},
    )
