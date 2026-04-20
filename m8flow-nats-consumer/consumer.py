import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

from dotenv import load_dotenv
from nats.aio.client import Client as NATS
from nats.errors import ConnectionClosedError, TimeoutError, NoServersError
from nats.js.errors import NotFoundError, KeyWrongLastSequenceError
from nats.js.kv import KeyValue

load_dotenv()

bpmn_dir = os.path.abspath(os.environ["M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"])

logging.basicConfig(
    level=os.getenv("M8FLOW_BACKEND_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("m8flow.nats.consumer")
logging.getLogger("m8flow.nats.token_service").setLevel(os.getenv("M8FLOW_NATS_TOKEN_SERVICE_LOG_LEVEL", "DEBUG"))

NATS_URL          = os.environ["M8FLOW_NATS_URL"]
STREAM_NAME       = os.environ["M8FLOW_NATS_STREAM_NAME"]
SUBJECT           = os.environ["M8FLOW_NATS_SUBJECT"]
DURABLE_NAME      = os.environ["M8FLOW_NATS_DURABLE_NAME"]
FETCH_BATCH       = int(os.environ["M8FLOW_NATS_FETCH_BATCH"])
FETCH_TIMEOUT     = float(os.environ["M8FLOW_NATS_FETCH_TIMEOUT"])

DEDUP_BUCKET      = os.environ["M8FLOW_NATS_DEDUP_BUCKET"]
DEDUP_TTL_SECONDS = int(os.environ["M8FLOW_NATS_DEDUP_TTL"])
RETRY_DELAY       = int(os.getenv("M8FLOW_NATS_RETRY_DELAY", "5"))
MAX_RECONNECTS    = int(os.getenv("M8FLOW_NATS_MAX_RECONNECTS", "-1"))

running = True

flask_app = None

def instantiate_process(
    tenant_id: str,
    process_identifier: str,
    username: str,
    payload: dict,
) -> int | None:
    """
    Resolve user + process model, then create and run a process instance.

    Runs synchronously inside a Flask app context (called via asyncio.to_thread).
    Returns the new process instance ID, or None if a pre-condition is not met.
    Raises on transient errors (e.g. DB failure) so the caller can requeue.
    """
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.process_model_service import ProcessModelService
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    with flask_app.app_context():
        token = set_context_tenant_id(tenant_id)
        try:
            user_slug = username.split("@")[-1]
            tenant = db.session.get(M8flowTenantModel, tenant_id)
            if not tenant:
                logger.error("Tenant not found in the database. Event discarded.")
                return None

            if tenant.slug != user_slug:
                logger.error("Tenant mismatch between user and event. Event discarded.")
                return None

            user = UserModel.query.filter_by(username=username).first()
            if user is None:
                logger.error(f"User '{username}' not found in the database for tenant '{tenant_id}'. Event discarded.")
                return None

            try:
                process_model = ProcessModelService.get_process_model(process_identifier)
            except Exception as e:
                logger.error(f"Process model '{process_identifier}' not found: {e}")
                return None

            data_to_inject = {**payload, "_nats_initiator_username": username}

            processor = ProcessInstanceService.create_and_run_process_instance(
                process_model=process_model,
                persistence_level="persistent",
                data_to_inject=data_to_inject,
                user=user,
            )
            db.session.commit()
            return processor.process_instance_model.id
        except Exception:
            db.session.rollback()
            raise
        finally:
            reset_context_tenant_id(token)

async def check_idempotency(kv: KeyValue | None, tenant_id: str, event_id: str) -> str | None:
    """Check if event is duplicate. Returns dedup_key if new/uncheckable, None if confirmed duplicate."""
    dedup_key = f"{tenant_id}-{event_id}"
    if kv:
        try:
            await kv.create(dedup_key, b"1")
        except KeyWrongLastSequenceError:
            logger.warning(
                "Duplicate event id='%s' for tenant='%s' — already processed. Discarding.",
                event_id, tenant_id,
            )
            return None
        except Exception as e:
            logger.warning("NATS KV dedup check failed (%s) — processing event without dedup guard.", e)
            
    return dedup_key

def _extract_tenant_from_subject(subject: str) -> str | None:
    """
    Extract the tenant_id from a NATS subject.
    Expected format: m8flow.events.<tenant_id>.trigger
    Returns None if the subject does not match the expected format.
    """
    parts = subject.split(".")
    # m8flow . events . <tenant_id> . trigger  => 4 parts
    if len(parts) == 4 and parts[0] == "m8flow" and parts[1] == "events" and parts[3] == "trigger":
        return parts[2] or None
    return None


async def process_message(msg: Any, kv: KeyValue | None) -> None:
    """Authenticate and process a single NATS event."""
    from spiffworkflow_backend.exceptions.api_error import ApiError
    try:
        data = json.loads(msg.data.decode("utf-8"))
        logger.debug("Received event: %s", data)
    except Exception as e:
        logger.error("Failed to parse message data: %s", e)
        await msg.ack()
        return

    # Authoritative tenant_id comes from the NATS subject, not the payload
    subject_tenant_id = _extract_tenant_from_subject(msg.subject)
    if not subject_tenant_id:
        logger.error("Event subject has unexpected format — cannot determine tenant. Discarding. subject=%s", msg.subject)
        await msg.ack()
        return

    # If the payload also carries a tenant_id, it must match the subject
    payload_tenant_id  = data.get("tenant_id")
    if payload_tenant_id and payload_tenant_id != subject_tenant_id:
        logger.error(
            "Tenant mismatch: payload tenant does not match subject tenant. Event discarded."
        )
        await msg.ack()
        return

    tenant_id          = subject_tenant_id
    process_identifier = data.get("process_identifier")
    username           = data.get("username")
    event_id           = data.get("id")
    api_key            = data.get("api_key")

    if not all([process_identifier, username]):
        logger.error(
            "Message missing required fields (process_identifier, username). "
            "Discarding."
        )
        await msg.ack()
        return

    if not api_key:
        logger.error("Rejecting event: 'api_key' is missing. tenant=%s", tenant_id)
        await msg.ack()
        return

    def _verify():
        from m8flow_backend.services.nats_token_service import NatsTokenService
        from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id
        with flask_app.app_context():
            token = set_context_tenant_id(tenant_id)
            try:
                return NatsTokenService.verify_token(tenant_id, api_key)
            finally:
                reset_context_tenant_id(token)

    is_valid = await asyncio.to_thread(_verify)

    if not is_valid:
        logger.error("Rejecting event: Invalid api_key for tenant %s", tenant_id)
        await msg.ack()
        return

    dedup_key = None
    if event_id and tenant_id:
        dedup_key = await check_idempotency(kv, tenant_id, event_id)
        if dedup_key is None:
            await msg.ack()
            return
    else:
        if not event_id:
            logger.warning("Event has no 'id' field — idempotency cannot be guaranteed.")

    try:
        instance_id = await asyncio.to_thread(
            instantiate_process,
            tenant_id,
            process_identifier,
            username,
            data.get("payload", {}),
        )

        if instance_id is None:
            logger.warning("Event processing aborted: pre-condition not met (see errors above).")
            if dedup_key and kv:
                try:
                    await kv.delete(dedup_key)
                except Exception:
                    pass
            await msg.ack()
            return

        logger.info(
            "Process instance created | tenant=%s identifier=%s instance_id=%s",
            tenant_id, process_identifier, instance_id,
        )
        await msg.ack()
    except ApiError as e:
        # Permanent business-logic failure (e.g. missing lane users, invalid BPMN config).
        # NAKing would cause endless retries since the data won't change — ACK to discard.
        logger.error(
            "Process instantiation failed (permanent error, discarding message): "
            "tenant=%s identifier=%s error=%s",
            tenant_id, process_identifier, e,
        )
        if dedup_key and kv:
            try:
                await kv.delete(dedup_key)
            except Exception:
                pass
        await msg.ack()
    except Exception as e:
        logger.error("Process instantiation failed (transient error, will retry): %s", e)
        if dedup_key and kv:
            try:
                await kv.delete(dedup_key)
            except Exception:
                pass
        await msg.nak(delay=RETRY_DELAY)

async def main() -> None:
    global flask_app
    
    logger.info("Initializing M8Flow core application context...")
    from m8flow_runtime.app import app as asgi_app
    flask_app = asgi_app.app.app

    logger.info("Starting M8Flow NATS Consumer...")
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

    kv: KeyValue | None = None
    try:
        kv = await js.create_key_value(
            bucket=DEDUP_BUCKET,
            ttl=DEDUP_TTL_SECONDS,
            max_bytes=0,
            history=1,
        )
        logger.info(f"NATS KV dedup bucket '{DEDUP_BUCKET}' ready (TTL: {DEDUP_TTL_SECONDS}s)")
    except Exception as e:
        logger.warning(f"KV dedup bucket unavailable ({e}) — dedup guard disabled. Events will be processed without idempotency protection.")
        kv = None

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

    logger.info("Consumer loop started.")
    while running:
        try:
            msgs = await sub.fetch(batch=FETCH_BATCH, timeout=FETCH_TIMEOUT)
            for msg in msgs:
                await process_message(msg, kv)
        except TimeoutError:
            pass
        except ConnectionClosedError:
            logger.warning("NATS connection closed, exiting loop.")
            break
        except Exception as e:
            logger.exception("Unexpected error in consumer loop: %s", e)
            await asyncio.sleep(1)

    logger.info("Closing connections...")
    await nc.close()
    logger.info("Consumer shutdown complete.")

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
