from __future__ import annotations
import asyncio
import json
import logging
import uuid
from m8flow_backend.config import nats_notifications_stream_name
from m8flow_backend.config import nats_notifications_subject
from m8flow_backend.config import nats_url
from spiffworkflow_backend.exceptions.api_error import ApiError

logger = logging.getLogger("m8flow.nats.service")

try:
    from nats.aio.client import Client as NATS
    from nats.js.errors import NotFoundError
except ModuleNotFoundError:  # pragma: no cover - environment-dependent optional dependency
    NATS = None

    class NotFoundError(Exception):
        """Fallback error type when nats-py is unavailable."""

        pass

class NatsService:
    @staticmethod
    async def _publish(
        tenant_id: str,
        tenant_slug: str,
        process_identifier: str,
        username: str,
        payload: dict,
        api_key: str,
        stream_name: str | None = None,
        reply_timeout: float = 30.0,
    ) -> dict:
        if NATS is None:
            raise ApiError(
                error_code="nats_dependency_missing",
                message="NATS support is not available because the 'nats-py' dependency is not installed.",
                status_code=503,
            )

        nc = NATS()
        try:
            await nc.connect(nats_url(), connect_timeout=5)
        except Exception as e:
            logger.error("nats_service: failed to connect to NATS at %s: %s", nats_url(), str(e))
            raise ApiError(
                error_code="nats_connection_error",
                message=f"Could not connect to NATS server: {str(e)}",
                status_code=503
            )

        js = nc.jetstream()
        subject = f"m8flow.events.{tenant_slug}.trigger"
        event_id = str(uuid.uuid4())

        # Create a unique inbox subject for the consumer to reply to
        reply_to = f"_INBOX.m8flow.{event_id}"
        reply_future: asyncio.Future = asyncio.get_event_loop().create_future()

        # Subscribe to the inbox before publishing so we don't miss the reply
        async def _on_reply(msg: any) -> None:
            if not reply_future.done():
                reply_future.set_result(msg.data)

        inbox_sub = await nc.subscribe(reply_to, cb=_on_reply)

        event_data = {
            "id": event_id,
            "subject": subject,
            "tenant_id": tenant_id,
            "tenant_slug": tenant_slug,
            "process_identifier": process_identifier,
            "username": username,
            "payload": payload,
            "api_key": api_key,
            "reply_to": reply_to,
        }

        try:
            ack = await js.publish(
                subject,
                json.dumps(event_data).encode("utf-8"),
                headers={
                    "Nats-Msg-Id": event_id,
                    "tenant_slug": tenant_slug,
                    "stream_name": stream_name,
                },
            )
            logger.info("Published to NATS: subject=%s stream=%s seq=%s", subject, ack.stream, ack.seq)

            # Wait for the consumer to reply with process instance details
            try:
                raw_reply = await asyncio.wait_for(reply_future, timeout=reply_timeout)
                instance_details = json.loads(raw_reply.decode("utf-8"))
                logger.info("Received process instance reply for event_id=%s", event_id)
            except asyncio.TimeoutError:
                logger.warning("No reply received within %ss for event_id=%s", reply_timeout, event_id)
                instance_details = None

            return {**event_data, "process_instance": instance_details}

        except NotFoundError:
            logger.error("Stream '%s' does not exist.", stream_name)
            raise
        except Exception as e:
            logger.error("NATS publish failed: %s", e)
            raise
        finally:
            await inbox_sub.unsubscribe()
            await nc.close()




    @staticmethod
    async def _publish_notification(tenant_slug: str, payload: dict) -> None:
        """Fire-and-forget publish of an internal notification event.

        Unlike trigger events there is no api_key and no reply inbox: the producer is
        the backend itself and the payload is only a pointer — the worker re-reads all
        authoritative state from the database. Nats-Msg-Id is deterministic per
        (tenant, instance, task) so JetStream's dedup window absorbs rapid repeat
        publishes from back-to-back save() calls."""
        if NATS is None:
            raise ApiError(
                error_code="nats_dependency_missing",
                message="NATS support is not available because the 'nats-py' dependency is not installed.",
                status_code=503,
            )

        nc = NATS()
        await nc.connect(nats_url(), connect_timeout=5)
        try:
            js = nc.jetstream()
            stream_name = nats_notifications_stream_name()
            try:
                await js.stream_info(stream_name)
            except NotFoundError:
                logger.info(
                    "nats_service: creating notifications stream '%s' (subject '%s')",
                    stream_name,
                    nats_notifications_subject(),
                )
                await js.add_stream(name=stream_name, subjects=[nats_notifications_subject()])

            subject = f"m8flow.notifications.{tenant_slug}.external-form"
            message_id = f"extform-{tenant_slug}-{payload.get('process_instance_id')}-{payload.get('task_guid')}"
            ack = await js.publish(
                subject,
                json.dumps(payload).encode("utf-8"),
                headers={"Nats-Msg-Id": message_id, "tenant_slug": tenant_slug},
            )
            logger.info(
                "Published notification to NATS: subject=%s stream=%s seq=%s", subject, ack.stream, ack.seq
            )
        finally:
            await nc.close()

    @classmethod
    def publish_notification(cls, tenant_slug: str, payload: dict) -> None:
        """Synchronous wrapper to publish a notification event to NATS."""
        cls._run_coroutine(cls._publish_notification(tenant_slug, payload))

    @classmethod
    def publish_event(
        cls,
        tenant_id: str,
        tenant_slug: str,
        process_identifier: str,
        username: str,
        payload: dict,
        api_key: str,
        stream_name: str | None = None
    ) -> dict:
        """Synchronous wrapper to publish event to NATS."""
        coro = NatsService._publish(
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            process_identifier=process_identifier,
            username=username,
            payload=payload,
            api_key=api_key,
            stream_name=stream_name
        )
        return cls._run_coroutine(coro)

    @staticmethod
    def _run_coroutine(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        if loop.is_running():
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor() as executor:
                return executor.submit(asyncio.run, coro).result()

        return loop.run_until_complete(coro)

