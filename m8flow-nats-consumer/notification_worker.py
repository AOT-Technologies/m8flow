"""External-form notification worker (M8F-339).

Consumes external_form.requests_created events from the M8FLOW_NOTIFICATIONS
JetStream stream and emails each recipient their secure link. A periodic sweep
re-checks the tracking table for pending requests whose event was missed, so
delivery is reliable even when a publish failed or this worker was down.

All authoritative state lives in the m8flow_external_form_requests table; events
are only pointers. The atomic claim inside ExternalFormNotificationService.notify
guarantees the same request never produces duplicate emails, so messages are
always ACKed — failures are recorded on the row and retried by the sweep instead
of through NATS redelivery.
"""
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

from dotenv import load_dotenv
from nats.aio.client import Client as NATS
from nats.errors import ConnectionClosedError, NoServersError
from nats.js.errors import NotFoundError

load_dotenv()

logging.basicConfig(
    level=os.getenv("M8FLOW_BACKEND_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("m8flow.nats.notification_worker")

NATS_URL      = os.environ["M8FLOW_NATS_URL"]
STREAM_NAME   = os.getenv("M8FLOW_NATS_NOTIFICATIONS_STREAM_NAME", "M8FLOW_NOTIFICATIONS")
SUBJECT       = os.getenv("M8FLOW_NATS_NOTIFICATIONS_SUBJECT", "m8flow.notifications.>")
DURABLE_NAME  = os.getenv("M8FLOW_NATS_NOTIFICATIONS_DURABLE_NAME", "m8flow-notification-worker")
FETCH_BATCH   = int(os.getenv("M8FLOW_NATS_FETCH_BATCH", "10"))
FETCH_TIMEOUT = float(os.getenv("M8FLOW_NATS_FETCH_TIMEOUT", "2.0"))
MAX_RECONNECTS = int(os.getenv("M8FLOW_NATS_MAX_RECONNECTS", "-1"))

running = True

flask_app = None


def _notify_one(tenant_id: str, reference_id: str) -> str:
    """Claim and email one request inside an app context with the row's tenant set.

    Runs synchronously (called via asyncio.to_thread). The per-thread app context
    gives this call its own SQLAlchemy session, torn down on exit."""
    from spiffworkflow_backend.models.db import db
    from m8flow_backend.services.external_form_notification_service import ExternalFormNotificationService
    from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id

    with flask_app.app_context():
        token = set_context_tenant_id(tenant_id)
        try:
            return ExternalFormNotificationService.notify(reference_id)
        except Exception:
            db.session.rollback()
            raise
        finally:
            reset_context_tenant_id(token)


def _run_sweep() -> None:
    """One sweep pass: find requests still owed an email and send them.

    sweep_candidates runs cross-tenant (the tracking table is not tenant-row-locked);
    each send then runs under the owning row's tenant context. The atomic claim makes
    racing the event fast-path harmless."""
    from m8flow_backend.services.external_form_notification_service import ExternalFormNotificationService

    with flask_app.app_context():
        candidates = ExternalFormNotificationService.sweep_candidates()

    if not candidates:
        return

    logger.info("Sweep found %s request(s) owed an email.", len(candidates))
    for _request_id, reference_id, tenant_id in candidates:
        try:
            result = _notify_one(tenant_id, reference_id)
            logger.info("Sweep notify reference=%s…: %s", reference_id[:8], result)
        except Exception:
            logger.exception("Sweep notify failed for reference=%s… (tenant=%s)", reference_id[:8], tenant_id)


async def sweep_loop() -> None:
    from m8flow_backend.config import notification_sweep_interval_seconds

    interval = notification_sweep_interval_seconds()
    logger.info("Sweep loop started (every %ss).", interval)
    while running:
        try:
            await asyncio.to_thread(_run_sweep)
        except Exception:
            logger.exception("Sweep pass failed; retrying on next interval.")
        await asyncio.sleep(interval)


def _extract_tenant_slug_from_subject(subject: str) -> str | None:
    """Expected format: m8flow.notifications.<tenant_slug>.external-form"""
    parts = subject.split(".")
    if len(parts) == 4 and parts[0] == "m8flow" and parts[1] == "notifications" and parts[3] == "external-form":
        return parts[2] or None
    return None


async def process_message(msg: Any) -> None:
    """Email every recipient referenced by one requests_created event.

    Always ACKs: a send failure is recorded on the tracking row (status=failed) and
    retried by the sweep, which avoids NATS redelivery storms and keeps the claim
    column the single dedup authority."""
    try:
        try:
            data = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to parse message data: %s", e)
            return

        subject_slug = _extract_tenant_slug_from_subject(msg.subject)
        if not subject_slug:
            logger.error("Unexpected subject format, discarding: %s", msg.subject)
            return

        payload_slug = data.get("tenant_slug")
        if payload_slug and payload_slug != subject_slug:
            logger.error(
                "Tenant slug mismatch (subject '%s' != payload '%s'), discarding.", subject_slug, payload_slug
            )
            return

        tenant_id = data.get("tenant_id")
        reference_ids = data.get("reference_ids") or []
        if not tenant_id or not reference_ids:
            logger.error("Event missing tenant_id or reference_ids, discarding.")
            return

        for reference_id in reference_ids:
            try:
                result = await asyncio.to_thread(_notify_one, tenant_id, reference_id)
                logger.info(
                    "Notify reference=%s… (instance=%s): %s",
                    str(reference_id)[:8],
                    data.get("process_instance_id"),
                    result,
                )
            except Exception:
                logger.exception(
                    "Notify failed for reference=%s… (tenant=%s); the sweep will retry.",
                    str(reference_id)[:8],
                    tenant_id,
                )
    finally:
        await msg.ack()


async def main() -> None:
    global flask_app

    logger.info("Initializing M8Flow core application context...")
    from m8flow_backend.app import app as asgi_app
    flask_app = asgi_app.app.app

    logger.info("Starting M8Flow notification worker...")
    nc = NATS()

    async def disconnected_cb():
        logger.warning("Disconnected from NATS")

    async def reconnected_cb():
        logger.info(f"Reconnected to NATS at {nc.connected_url.netloc}")

    async def error_cb(e):
        logger.error(f"NATS connection error: {e}")

    try:
        await nc.connect(
            NATS_URL,
            reconnected_cb=reconnected_cb,
            disconnected_cb=disconnected_cb,
            error_cb=error_cb,
            max_reconnect_attempts=MAX_RECONNECTS,
        )
    except (NoServersError, ConnectionError) as e:
        logger.error(f"Failed to connect to NATS: {e}")
        sys.exit(1)

    js = nc.jetstream()

    try:
        await js.stream_info(STREAM_NAME)
        logger.info(f"Stream '{STREAM_NAME}' already exists.")
    except NotFoundError:
        logger.info(f"Stream '{STREAM_NAME}' not found. Creating with subject '{SUBJECT}'...")
        await js.add_stream(name=STREAM_NAME, subjects=[SUBJECT])
        logger.info(f"Stream '{STREAM_NAME}' created.")

    logger.info(f"Subscribing to {SUBJECT} (durable: {DURABLE_NAME})")
    try:
        sub = await js.pull_subscribe(SUBJECT, DURABLE_NAME, stream=STREAM_NAME)
    except Exception as e:
        logger.error(f"Failed to create pull subscription: {e}")
        await nc.close()
        sys.exit(1)

    sweep_task = asyncio.create_task(sweep_loop())

    logger.info("Notification worker loop started.")
    while running:
        try:
            msgs = await sub.fetch(batch=FETCH_BATCH, timeout=FETCH_TIMEOUT)
            for msg in msgs:
                await process_message(msg)
        except asyncio.TimeoutError:
            # No messages within the fetch window — normal idle poll.
            pass
        except ConnectionClosedError:
            logger.warning("NATS connection closed, exiting loop.")
            break
        except Exception as e:
            logger.exception("Unexpected error in worker loop: %s", e)
            await asyncio.sleep(1)

    logger.info("Closing connections...")
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    await nc.close()
    logger.info("Notification worker shutdown complete.")


def handle_shutdown(sig, frame) -> None:
    global running
    logger.info("Shutdown signal received, gracefully stopping...")
    running = False


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
