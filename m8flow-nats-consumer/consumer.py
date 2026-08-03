import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import time
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

try:
    from m8flow_telemetry.bootstrap import setup
    from m8flow_telemetry.metrics import record_nats_processing, set_nats_consumer_lag
    from m8flow_telemetry.nats_propagate import start_nats_consume_span

    setup("m8flow-nats-consumer")
except ImportError:  # pragma: no cover
    record_nats_processing = None
    set_nats_consumer_lag = None
    start_nats_consume_span = None
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


def _resolve_tenant_initiator(username: str, tenant_id: str) -> Any | None:
    """
    Resolve the initiating user for a trigger event.

    Fetch every user with this exact username, keep only those that belong to the
    target tenant, then ignore backend-signed session-token mirror rows — duplicate
    rows whose ``service`` is the backend's own JWT issuer (``SPIFFWORKFLOW_BACKEND_URL``)
    instead of a Keycloak realm issuer. A real OIDC user and its backend-signed mirror
    are the same person, so the real row is preferred. Returns ``None`` when no tenant
    user matches or when genuinely distinct identities share the username.
    """
    from flask import current_app

    from m8flow_backend.services.tenant_identity_helpers import (
        find_users_for_current_tenant_by_username,
    )

    tenant_matches = find_users_for_current_tenant_by_username(username, tenant_id=tenant_id)
    exact_matches = [user for user in tenant_matches if getattr(user, "username", None) == username]
    if not exact_matches:
        return None
    if len(exact_matches) == 1:
        return exact_matches[0]

    backend_issuer = (current_app.config.get("SPIFFWORKFLOW_BACKEND_URL") or "").strip()
    real_users = [
        user for user in exact_matches if (getattr(user, "service", "") or "").strip() != backend_issuer
    ]
    if len(real_users) == 1:
        return real_users[0]
    if not real_users:
        # Only backend-signed mirror rows exist; they still reference the real person.
        return exact_matches[0]

    # Multiple genuinely distinct identities share this username — ambiguous, fail closed.
    return None


class InitiatorNotFoundError(ValueError):
    """The initiating username did not resolve to a user in the target tenant."""


class ProcessModelNotFoundError(ValueError):
    """The requested process model does not exist."""


def _record_audit(**fields: Any) -> None:
    """Write one audit row for a message outcome.

    Never raises. Recording what happened must not change what happens: a monitoring
    write that failed must not turn a processed event into a retry, or a rejection into
    a crash.
    """
    from m8flow_backend.services.nats_event_audit_service import NatsEventAuditService

    try:
        with flask_app.app_context():
            NatsEventAuditService.record_outcome(**fields)
    except Exception:
        logger.exception("Failed to record NATS audit row (message handling unaffected).")


def _record_duplicate(**fields: Any) -> None:
    """Count one suppressed duplicate delivery. Never raises, for the same reason."""
    from m8flow_backend.services.nats_event_audit_service import NatsEventAuditService

    try:
        with flask_app.app_context():
            NatsEventAuditService.record_duplicate(**fields)
    except Exception:
        logger.exception("Failed to record NATS duplicate (message handling unaffected).")


def _tenant_id_from_subject(subject: str) -> str | None:
    """Best-effort tenant UUID for a message whose payload could not be trusted.

    The subject carries the tenant *slug*; the audit table stores the tenant UUID. Returns
    None when the subject is malformed or the slug matches no tenant, which is exactly the
    un-attributable case the audit table records with a NULL tenant.
    """
    slug = _extract_tenant_from_subject(subject)
    if not slug:
        return None

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    try:
        with flask_app.app_context():
            tenant = M8flowTenantModel.query.filter_by(slug=slug).one_or_none()
            return tenant.id if tenant else None
    except Exception:
        logger.exception("Failed to resolve tenant for subject '%s' while auditing.", subject)
        return None


def _stream_seq(msg: Any) -> int | None:
    """JetStream sequence of this message — the pointer used to fetch its payload later."""
    try:
        return msg.metadata.sequence.stream
    except Exception:
        return None


def instantiate_process(
    tenant_id: str,
    process_identifier: str,
    username: str,
    payload: dict,
    audit: dict | None = None,
) -> int | None:
    """
    Resolve user + process model, then create and run a process instance.

    Runs synchronously inside a Flask app context (called via asyncio.to_thread).
    Returns the new process instance ID, or None if a pre-condition is not met.
    Raises on transient errors (e.g. DB failure) so the caller can requeue.
    """
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.process_model_service import ProcessModelService
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id

    with flask_app.app_context():
        token = set_context_tenant_id(tenant_id)
        try:
            # The new user model stores the bare preferred_username (no @tenant_slug suffix).
            # Tenant membership is determined via the service (Keycloak realm) field, not the
            # username. _resolve_tenant_initiator() fetches the user by username, narrows to the
            # target tenant, and ignores backend-signed session-token mirror duplicates.
            user = _resolve_tenant_initiator(username, tenant_id)
            if user is None:
                err = f"User '{username}' not found in the database for tenant '{tenant_id}'."
                logger.error(err)
                raise InitiatorNotFoundError(err)

            try:
                process_model = ProcessModelService.get_process_model(process_identifier)
            except Exception as e:
                err = f"Process model '{process_identifier}' not found: {e}"
                logger.error(err)
                raise ProcessModelNotFoundError(err)

            data_to_inject = {**payload, "_nats_initiator_username": username}

            processor = ProcessInstanceService.create_and_run_process_instance(
                process_model=process_model,
                persistence_level="persistent",
                data_to_inject=data_to_inject,
                user=user,
            )
            instance = processor.process_instance_model

            if audit is not None:
                # Recorded inside this transaction (commit=False) so the audit row and the
                # process instance land together — an instance can never exist without its
                # row. The service wraps it in a SAVEPOINT, so an unwritable audit row
                # rolls back alone and still lets the instance commit below.
                from m8flow_backend.models.nats_event_audit import NatsEventOutcome
                from m8flow_backend.services.nats_event_audit_service import NatsEventAuditService

                NatsEventAuditService.record_outcome(
                    tenant_id=tenant_id,
                    event_id=audit.get("event_id"),
                    outcome=NatsEventOutcome.instantiated.value,
                    stream_seq=audit.get("stream_seq"),
                    process_identifier=process_identifier,
                    username=username,
                    process_instance_id=instance.id,
                    commit=False,
                )

            db.session.commit()
            return {
                "id": instance.id,
                "status": instance.status,
                "process_model_identifier": instance.process_model_identifier,
                "created_at_in_seconds": instance.created_at_in_seconds,
                "updated_at_in_seconds": instance.updated_at_in_seconds,
            }

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


async def process_message(msg: Any, kv: KeyValue | None, nc: NATS) -> None:
    """Authenticate and process a single NATS event."""
    from spiffworkflow_backend.exceptions.api_error import ApiError
    from m8flow_backend.models.nats_event_audit import NatsEventOutcome

    data = {}
    reply_to = None
    dedup_key = None
    tenant_id = None
    process_identifier = None
    username = None
    event_id = None
    started: float | None = None
    # Classified explicitly at each raise site rather than by matching on the exception
    # message, which would silently mis-classify the moment a message string is reworded.
    failure_outcome = NatsEventOutcome.transient_error.value

    try:
        try:
            data = json.loads(msg.data.decode("utf-8"))
            reply_to = data.get("reply_to")
        except Exception as e:
            logger.error("Failed to parse message data: %s", e)
            # Previously the most invisible path in the consumer: acked with no log-level
            # metric and no record at all. The payload is unreadable, so the tenant can
            # only come from the subject — and NULL when even that is malformed.
            await asyncio.to_thread(
                _record_audit,
                tenant_id=_tenant_id_from_subject(msg.subject),
                event_id=None,
                outcome=NatsEventOutcome.invalid_payload.value,
                error_message=f"could not parse message body: {e}",
                stream_seq=_stream_seq(msg),
            )
            await msg.ack()
            return

        event_id = data.get("id")

        # Authoritative tenant_id comes from the NATS subject, not the payload
        subject_tenant_id = _extract_tenant_from_subject(msg.subject)
        if not subject_tenant_id:
            failure_outcome = NatsEventOutcome.invalid_payload.value
            raise ValueError(f"Event subject has unexpected format — cannot determine tenant: {msg.subject}")

        # The NATS subject carries the slug for routing (e.g. m8flow.events.zoro.trigger).
        # The payload carries the tenant UUID for auth and process instantiation.
        payload_tenant_id = data.get("tenant_id")
        payload_tenant_slug = data.get("tenant_slug")

        if not payload_tenant_id:
            failure_outcome = NatsEventOutcome.invalid_payload.value
            raise ValueError("Event payload missing 'tenant_id' (UUID).")

        # Optional: validate that the slug in the subject matches what the publisher sent
        if payload_tenant_slug and payload_tenant_slug != subject_tenant_id:
            failure_outcome = NatsEventOutcome.tenant_mismatch.value
            raise ValueError(f"Tenant slug mismatch: subject slug '{subject_tenant_id}' != payload slug '{payload_tenant_slug}'")

        tenant_id = payload_tenant_id  # UUID
        process_identifier = data.get("process_identifier")
        username           = data.get("username")
        api_key            = data.get("api_key")

        started = time.perf_counter()
        msg_headers = dict(getattr(msg, "headers", None) or {})
        span_ctx = (
            start_nats_consume_span(msg.subject, tenant_id=tenant_id, headers=msg_headers)
            if start_nats_consume_span
            else contextlib.nullcontext()
        )

        with span_ctx:
            if not all([process_identifier, username]):
                failure_outcome = NatsEventOutcome.invalid_payload.value
                raise ValueError("Message missing required fields (process_identifier, username).")

            if not api_key:
                failure_outcome = NatsEventOutcome.rejected_auth.value
                raise ValueError(f"Rejecting event: 'api_key' is missing for tenant {tenant_id}")

            def _verify():
                from m8flow_backend.services.nats_token_service import NatsTokenService
                from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id
                with flask_app.app_context():
                    token = set_context_tenant_id(tenant_id)
                    try:
                        return NatsTokenService.authenticate_key(api_key)
                    finally:
                        reset_context_tenant_id(token)

            authenticated = await asyncio.to_thread(_verify)
            if authenticated is None:
                # Missing / malformed / unknown / expired / revoked key.
                failure_outcome = NatsEventOutcome.rejected_auth.value
                raise ValueError(f"Rejecting event: Invalid api_key for tenant {tenant_id}")

            if authenticated.tenant_id != tenant_id:
                # The key belongs to a different tenant than the event claims.
                failure_outcome = NatsEventOutcome.tenant_mismatch.value
                raise ValueError(
                    f"Rejecting event: api_key tenant {authenticated.tenant_id} does not match event tenant {tenant_id}"
                )

            def _scope_allows():
                from m8flow_backend.services.nats_token_service import NatsTokenService
                return NatsTokenService.scope_allows(authenticated.scope, process_identifier)

            # Defense in depth: the publish path already enforces scope, but re-check here so a
            # scoped key can never trigger a process outside its allow-list.
            if not await asyncio.to_thread(_scope_allows):
                failure_outcome = NatsEventOutcome.rejected_scope.value
                raise ValueError(
                    f"Rejecting event: api_key not scoped for process {process_identifier}"
                )

            if event_id and tenant_id:
                dedup_key = await check_idempotency(kv, tenant_id, event_id)
                if dedup_key is None:
                    # Duplicate event, already logged in check_idempotency. Bumps the
                    # original row's duplicate_count rather than overwriting its outcome —
                    # this delivery carries the same event id as the run that succeeded.
                    await asyncio.to_thread(
                        _record_duplicate,
                        tenant_id=tenant_id,
                        event_id=event_id,
                        stream_seq=_stream_seq(msg),
                        process_identifier=process_identifier,
                        username=username,
                    )
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
                    data.get("payload") or {},
                    {"event_id": event_id, "stream_seq": _stream_seq(msg)},
                )
            except InitiatorNotFoundError:
                failure_outcome = NatsEventOutcome.user_not_found.value
                raise
            except ProcessModelNotFoundError:
                failure_outcome = NatsEventOutcome.model_not_found.value
                raise

            logger.info(
                "Process instance created | tenant=%s identifier=%s instance_id=%s",
                tenant_id, process_identifier, instance_id.get("id"),
            )
            await msg.ack()

            # Reply to the publisher with process instance details
            if reply_to:
                try:
                    await nc.publish(reply_to, json.dumps(instance_id).encode("utf-8"))
                except Exception as e:
                    logger.warning("Failed to send reply to %s: %s", reply_to, e)

            if record_nats_processing is not None:
                record_nats_processing(tenant_id, duration_ms=(time.perf_counter() - started) * 1000, failed=False)

    except Exception as e:
        # Most failures are PERMANENT (validation, missing models, auth).
        # We ACK to discard the message and stop the infinite retry loop.
        error_msg = str(e)
        logger.error(
            "Event processing failed (ACKing message): tenant=%s identifier=%s error=%s type=%s",
            tenant_id, process_identifier, error_msg, type(e).__name__,
        )

        if record_nats_processing is not None:
            duration_ms = (time.perf_counter() - started) * 1000 if started is not None else 0.0
            record_nats_processing(tenant_id, duration_ms=duration_ms, failed=True)

        # The message is about to be ACKed away, so this row is the only lasting record of
        # why it never became a process instance.
        await asyncio.to_thread(
            _record_audit,
            tenant_id=tenant_id or _tenant_id_from_subject(msg.subject),
            event_id=event_id,
            outcome=failure_outcome,
            error_message=error_msg,
            stream_seq=_stream_seq(msg),
            process_identifier=process_identifier,
            username=username,
        )
        
        if dedup_key and kv:
            try:
                await kv.delete(dedup_key)
            except Exception:
                pass

        # Reply with error details so the API can return a meaningful response
        if reply_to:
            try:
                error_reply = {"error": True, "message": error_msg}
                await nc.publish(reply_to, json.dumps(error_reply).encode("utf-8"))
            except Exception as publish_err:
                logger.warning("Failed to send error reply to %s: %s", reply_to, publish_err)

        await msg.ack()

async def main() -> None:
    global flask_app

    logger.info("Initializing M8Flow core application context...")
    from m8flow_backend.app import app as asgi_app
    flask_app = asgi_app.app
    while not hasattr(flask_app, "app_context"):
        flask_app = flask_app.app

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

    async def _report_consumer_lag() -> None:
        if set_nats_consumer_lag is None:
            return
        try:
            info = await sub.consumer_info()
            set_nats_consumer_lag(getattr(info, "num_pending", 0))
        except Exception:
            pass

    logger.info("Consumer loop started.")
    while running:
        try:
            msgs = await sub.fetch(batch=FETCH_BATCH, timeout=FETCH_TIMEOUT)
            for msg in msgs:
                await process_message(msg, kv, nc)
            # Report current lag every iteration, not just on idle timeout —
            # under sustained backlog, fetch never times out, so a
            # timeout-only update would leave the gauge stale exactly when
            # the backlog is worst.
            await _report_consumer_lag()
        except TimeoutError:
            await _report_consumer_lag()
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
