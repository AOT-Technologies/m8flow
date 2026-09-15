"""Structured logging, request correlation, and OTel trace/span correlation.

This package is the host's logging/observability seam: everything that turns
a plain ``logging.getLogger(__name__)`` call into a Grafana-ready record
(tenant id, request id, OTel trace/span id, JSON shape) lives here, so
individual routes and services never need to know about the wire format.
"""
