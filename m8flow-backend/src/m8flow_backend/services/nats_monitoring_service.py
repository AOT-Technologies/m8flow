"""Reads live NATS broker state for the monitoring dashboard.

Everything here is read-only and comes from the NATS server's own monitoring endpoints
(``/varz``, ``/healthz``, ``/jsz``) plus JetStream message fetches. The backend reaches
those over the internal docker network, so the monitoring port never needs publishing to a
browser — which is the main security improvement over the third-party UI this replaces.

The parsing in ``normalize_jsz`` was written against a real 2.10 response captured from a
running server (see ``tests/unit/m8flow_backend/fixtures/nats_jsz.json``), not from the
documentation. Three things that response settled:

- ``state.num_deleted`` is absent unless messages have actually been deleted.
- ``consumer_detail[].push_bound`` is null for pull consumers, which is all m8flow uses.
- KV buckets surface as ordinary streams named ``KV_<bucket>``, so the dedup bucket would
  otherwise appear in the dashboard as a mysterious extra stream.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.config import (
    nats_message_preview_max_bytes,
    nats_monitoring_enabled,
    nats_monitoring_url,
    nats_url,
)

logger = logging.getLogger("m8flow.nats.monitoring")

# Short: this is a request-path call and a dashboard that hangs is worse than one that
# reports the broker as unreachable.
HTTP_TIMEOUT_SECONDS = 3.0

# JetStream backs KV buckets and object stores with regular streams under these prefixes.
# They are real streams, but they are m8flow plumbing rather than event traffic, so they
# are flagged and can be filtered in the UI instead of silently padding the stream list.
INTERNAL_STREAM_PREFIXES = ("KV_", "OBJ_")

# Hard ceiling on a message fetch, enforced server-side so a crafted query cannot ask the
# broker for an unbounded range.
MAX_MESSAGE_FETCH = 25

try:
    from nats.aio.client import Client as NATS
except ModuleNotFoundError:  # pragma: no cover - environment-dependent optional dependency
    NATS = None


def _unavailable(detail: str) -> ApiError:
    return ApiError(
        error_code="nats_monitoring_unavailable",
        message=f"Could not read NATS monitoring state: {detail}",
        status_code=503,
    )


def _require_enabled() -> str:
    if not nats_monitoring_enabled():
        raise ApiError(
            error_code="nats_monitoring_disabled",
            message="NATS monitoring is not enabled on this deployment.",
            status_code=503,
        )
    return nats_monitoring_url().rstrip("/")


def stream_is_internal(name: str | None) -> bool:
    return bool(name) and name.startswith(INTERNAL_STREAM_PREFIXES)


def _int(value: object, default: int = 0) -> int:
    """Coerce a monitoring field to int. Missing keys are normal, not errors."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class NatsMonitoringService:
    # ------------------------------------------------------------------ HTTP

    @classmethod
    def _get(cls, path: str) -> dict:
        base = _require_enabled()
        url = f"{base}{path}"
        try:
            response = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.warning("nats monitoring: timed out reading %s", url)
            raise _unavailable(f"timed out after {HTTP_TIMEOUT_SECONDS}s")
        except httpx.HTTPStatusError as e:
            logger.warning("nats monitoring: %s returned %s", url, e.response.status_code)
            raise _unavailable(f"monitoring endpoint returned HTTP {e.response.status_code}")
        except httpx.HTTPError as e:
            logger.warning("nats monitoring: could not reach %s: %s", url, e)
            raise _unavailable(str(e))
        except ValueError as e:
            # A 200 whose body is not JSON usually means something else is on that port.
            raise _unavailable(f"monitoring endpoint returned a non-JSON body: {e}")

    # ------------------------------------------------------- normalization

    @staticmethod
    def normalize_varz(varz: dict, healthz: dict | None = None) -> dict:
        status = (healthz or {}).get("status")
        return {
            "healthy": status == "ok",
            "status": status or "unknown",
            "serverName": varz.get("server_name"),
            "serverId": varz.get("server_id"),
            "version": varz.get("version"),
            "uptime": varz.get("uptime"),
            "startedAt": varz.get("start"),
            "connections": _int(varz.get("connections")),
            "totalConnections": _int(varz.get("total_connections")),
            "subscriptions": _int(varz.get("subscriptions")),
            "inMsgs": _int(varz.get("in_msgs")),
            "outMsgs": _int(varz.get("out_msgs")),
            "inBytes": _int(varz.get("in_bytes")),
            "outBytes": _int(varz.get("out_bytes")),
            "slowConsumers": _int(varz.get("slow_consumers")),
            "memoryBytes": _int(varz.get("mem")),
            "cpuPercent": _int(varz.get("cpu")),
        }

    @classmethod
    def normalize_jsz(cls, jsz: dict) -> dict:
        """Flatten /jsz into stream + consumer records carrying the derived numbers.

        Pure function over the response body so the lag arithmetic is testable against a
        recorded fixture with no broker involved.
        """
        streams: list[dict] = []

        for account in jsz.get("account_details") or []:
            for stream in account.get("stream_detail") or []:
                state = stream.get("state") or {}
                config = stream.get("config") or {}
                last_seq = _int(state.get("last_seq"))

                consumers = [
                    cls._normalize_consumer(consumer, stream_last_seq=last_seq)
                    for consumer in (stream.get("consumer_detail") or [])
                ]

                streams.append(
                    {
                        "name": stream.get("name"),
                        "account": account.get("name"),
                        "subjects": config.get("subjects") or [],
                        "isInternal": stream_is_internal(stream.get("name")),
                        "messages": _int(state.get("messages")),
                        "bytes": _int(state.get("bytes")),
                        "firstSeq": _int(state.get("first_seq")),
                        "lastSeq": last_seq,
                        "numSubjects": _int(state.get("num_subjects")),
                        # Absent from the response unless deletions have happened.
                        "numDeleted": _int(state.get("num_deleted")),
                        "consumerCount": _int(state.get("consumer_count"), len(consumers)),
                        "createdAt": stream.get("created"),
                        "consumers": consumers,
                    }
                )

        streams.sort(key=lambda s: (s["isInternal"], (s["name"] or "")))

        event_streams = [s for s in streams if not s["isInternal"]]
        return {
            "streams": streams,
            "totals": {
                # Totals cover event traffic only; KV/object plumbing would otherwise
                # inflate every number on the dashboard.
                "streams": len(event_streams),
                "consumers": sum(len(s["consumers"]) for s in event_streams),
                "messages": sum(s["messages"] for s in event_streams),
                "bytes": sum(s["bytes"] for s in event_streams),
                "pending": sum(c["pending"] for s in event_streams for c in s["consumers"]),
                "unacked": sum(c["unacked"] for s in event_streams for c in s["consumers"]),
                "redelivered": sum(
                    c["redelivered"] for s in event_streams for c in s["consumers"]
                ),
                "internalStreams": len(streams) - len(event_streams),
            },
            "jetstream": {
                "memoryBytes": _int(jsz.get("memory")),
                "storageBytes": _int(jsz.get("storage")),
                "totalStreams": _int(jsz.get("streams")),
                "totalConsumers": _int(jsz.get("consumers")),
                "totalMessages": _int(jsz.get("messages")),
                "totalBytes": _int(jsz.get("bytes")),
            },
        }

    @staticmethod
    def _normalize_consumer(consumer: dict, *, stream_last_seq: int) -> dict:
        delivered = consumer.get("delivered") or {}
        ack_floor = consumer.get("ack_floor") or {}
        delivered_stream_seq = _int(delivered.get("stream_seq"))
        ack_floor_stream_seq = _int(ack_floor.get("stream_seq"))
        config = consumer.get("config") or {}

        return {
            "name": consumer.get("name"),
            "streamName": consumer.get("stream_name"),
            "filterSubject": config.get("filter_subject") or config.get("filter_subjects"),
            # Authoritative backlog: how many messages this consumer still owes work on.
            "pending": _int(consumer.get("num_pending")),
            # Delivered but not yet acknowledged.
            "unacked": _int(consumer.get("num_ack_pending")),
            # Raw sequence distance from the head of the stream. For a consumer with a
            # filter subject this OVERSTATES the backlog, because it counts messages on
            # subjects this consumer will never receive — "pending" is the honest number.
            # Kept because it is the only signal that shows a consumer parked far behind
            # the head even while its own filtered backlog is empty.
            "streamLag": max(0, stream_last_seq - delivered_stream_seq),
            # Messages delivered but still unacknowledged, by sequence.
            "ackLag": max(0, delivered_stream_seq - ack_floor_stream_seq),
            "redelivered": _int(consumer.get("num_redelivered")),
            "waiting": _int(consumer.get("num_waiting")),
            "deliveredStreamSeq": delivered_stream_seq,
            "deliveredConsumerSeq": _int(delivered.get("consumer_seq")),
            "ackFloorStreamSeq": ack_floor_stream_seq,
            "lastActive": delivered.get("last_active"),
            "createdAt": consumer.get("created"),
        }

    # ------------------------------------------------------------ public API

    @classmethod
    def overview(cls) -> dict:
        varz = cls._get("/varz")
        try:
            healthz = cls._get("/healthz")
        except ApiError:
            # A reachable server whose healthz is unhappy should still render an overview
            # that says so, rather than collapsing the whole page into an error.
            healthz = {"status": "unknown"}

        normalized = cls.normalize_varz(varz, healthz)
        normalized["jetstream"] = cls.normalize_jsz(cls._get("/jsz"))["jetstream"]
        return normalized

    @classmethod
    def streams(cls) -> dict:
        return cls.normalize_jsz(
            cls._get("/jsz?streams=1&consumers=1&accounts=1&config=1")
        )

    # ------------------------------------------------------------- messages

    @classmethod
    def get_messages(cls, stream_name: str, *, start_seq: int = 1, limit: int = 10) -> list[dict]:
        """Read up to ``limit`` messages from ``stream_name``, starting at ``start_seq``.

        Read-only: messages are fetched by sequence via the JetStream direct-get API and
        never acknowledged, so inspecting a stream cannot consume it.
        """
        _require_enabled()
        if NATS is None:
            raise _unavailable("the 'nats-py' dependency is not installed")

        limit = max(1, min(int(limit or 1), MAX_MESSAGE_FETCH))
        start_seq = max(1, int(start_seq or 1))

        async def _read() -> list[dict]:
            nc = NATS()
            try:
                await nc.connect(nats_url(), connect_timeout=5)
            except Exception as e:
                raise _unavailable(f"could not connect to NATS: {e}")
            try:
                js = nc.jetstream()
                out: list[dict] = []
                seq = start_seq
                # Sequences are not contiguous once messages expire or are removed, so walk
                # forward past gaps rather than stopping at the first miss.
                misses = 0
                while len(out) < limit and misses < limit:
                    try:
                        raw = await js.get_msg(stream_name, seq)
                    except Exception:
                        misses += 1
                        seq += 1
                        continue
                    out.append(cls._serialize_message(raw, seq))
                    seq += 1
                return out
            finally:
                await nc.close()

        return _run(_read())

    @classmethod
    def _serialize_message(cls, raw: object, seq: int) -> dict:
        data = getattr(raw, "data", b"") or b""
        cap = nats_message_preview_max_bytes()
        truncated = len(data) > cap
        clipped = data[:cap]

        try:
            payload = clipped.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            # Binary payload: base64 so the response stays valid JSON, with the encoding
            # stated rather than left for the client to guess.
            payload = base64.b64encode(clipped).decode("ascii")
            encoding = "base64"

        headers = getattr(raw, "headers", None) or {}
        return {
            "seq": getattr(raw, "seq", seq) or seq,
            "subject": getattr(raw, "subject", None),
            "time": str(getattr(raw, "time", "") or "") or None,
            "sizeBytes": len(data),
            "payload": payload,
            "encoding": encoding,
            "truncated": truncated,
            "headers": {str(k): str(v) for k, v in dict(headers).items()},
        }


def _run(coro):
    """Run a coroutine from sync request-handling code.

    Mirrors NatsService._run_coroutine: under an already-running loop the work is handed to
    a worker thread, because asyncio.run would raise.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if loop.is_running():
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor() as executor:
            return executor.submit(asyncio.run, coro).result()

    return loop.run_until_complete(coro)
