"""
consumer.py - M8Flow NATS Consumer Service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Standalone Python service that listens to NATS JetStream, validates
incoming JWT tokens via Keycloak JWKS, and natively creates process
instances in the M8Flow backend.
"""
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

import httpx
import jwt

from dotenv import load_dotenv
from nats.aio.client import Client as NATS
from nats.errors import ConnectionClosedError, TimeoutError, NoServersError
from nats.js.errors import NotFoundError, KeyWrongLastSequenceError
from nats.js.kv import KeyValue

# Load environment variables (docker-compose passes env_file from root)
load_dotenv()

# Enforce absolute path for process models (overriding any generic relative .env paths)
bpmn_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "process_models"))
os.environ["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = bpmn_dir
os.environ["M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = bpmn_dir

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("m8flow.nats.consumer")

# Config from Env (Strict production mode: fail-fast if missing)
NATS_URL          = os.environ["M8FLOW_NATS_URL"]
STREAM_NAME       = os.environ["M8FLOW_NATS_STREAM_NAME"]
SUBJECT           = os.environ["M8FLOW_NATS_SUBJECT"]
DURABLE_NAME      = os.environ["M8FLOW_NATS_DURABLE_NAME"]
FETCH_BATCH       = int(os.environ["M8FLOW_NATS_FETCH_BATCH"])
FETCH_TIMEOUT     = float(os.environ["M8FLOW_NATS_FETCH_TIMEOUT"])

# NATS KV config — used for event dedup
DEDUP_BUCKET      = os.environ["M8FLOW_NATS_DEDUP_BUCKET"]
DEDUP_TTL_SECONDS = int(os.environ["M8FLOW_NATS_DEDUP_TTL"])

running = True

# Cache for Keycloak public keys — avoids a JWKS fetch on every message
jwks_cache: dict = {}


async def get_public_keys(issuer_url: str) -> dict | None:
    """Fetch and cache the JWKS public keys from a Keycloak/OIDC issuer."""
    if issuer_url in jwks_cache:
        return jwks_cache[issuer_url]

    jwks_url = f"{issuer_url.rstrip('/')}/protocol/openid-connect/certs"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_url, timeout=5.0)
            resp.raise_for_status()
            public_keys = {
                jwk["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                for jwk in resp.json().get("keys", [])
                if "kid" in jwk
            }
            jwks_cache[issuer_url] = public_keys
            return public_keys
    except Exception as e:
        logger.error(f"Failed to fetch public keys from {jwks_url}: {e}")
        return None


async def validate_token(token: str, issuer_url: str) -> dict | None:
    """Validate a JWT against the OIDC issuer. Returns decoded claims or None."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        if not kid:
            logger.error("Token has no 'kid' in header.")
            return None

        public_keys = await get_public_keys(issuer_url)
        if not public_keys or kid not in public_keys:
            # Keys may have rotated — evict cache and retry once
            jwks_cache.pop(issuer_url, None)
            public_keys = await get_public_keys(issuer_url)
            if not public_keys or kid not in public_keys:
                logger.error(f"Could not find public key for kid: {kid}")
                return None

        # Audience validation is skipped: service account tokens may carry
        # different audiences depending on Keycloak client scope configuration.
        # Signature, expiry, and issuer are still fully validated.
        return jwt.decode(
            token,
            key=public_keys[kid],
            algorithms=["RS256"],
            issuer=issuer_url,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        logger.error("Token has expired.")
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
    except Exception as e:
        logger.error(f"Unexpected error validating token: {e}")
    return None


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
    # Lazy imports: these modules require env vars and Flask context to be ready.
    # They cannot be imported at module level before load_dotenv() + bpmn_dir setup.
    from extensions.app import app as asgi_app
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.process_model_service import ProcessModelService
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id

    # The extensions.app object is an AsgiTenantContextMiddleware wrapping a Connexion app.
    # We need the inner Flask app to create a context.
    # asgi_app -> connexion app -> flask app
    flask_app = asgi_app.app.app

    with flask_app.app_context():
        token = set_context_tenant_id(tenant_id)
        try:
            user = UserModel.query.filter_by(username=username).first()
            if user is None:
                logger.error(f"User '{username}' not found in the database. Event discarded.")
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
    dedup_key = f"{tenant_id}-{event_id}"  # NATS KV keys cannot contain colons
    if kv:
        try:
            await kv.create(dedup_key, b"1")
        except KeyWrongLastSequenceError:
            # KeyWrongLastSequenceError means the key already exists
            logger.warning(
                "Duplicate event id='%s' for tenant='%s' — already processed. Discarding.",
                event_id, tenant_id,
            )
            return None
        except Exception as e:
            logger.warning("NATS KV dedup check failed (%s) — processing event without dedup guard.", e)
            
    return dedup_key


async def authenticate_event(auth_token: str, username: str) -> bool:
    """Validate JWT signature and issuer. Returns True if valid, False otherwise."""
    # The iss claim contains the full Keycloak issuer URL (e.g. http://host:7002/realms/myrealm).
    # We read it without verification first so we know where to fetch the JWKS from.
    try:
        issuer_url = jwt.decode(auth_token, options={"verify_signature": False}).get("iss")
        if not issuer_url:
            logger.error("Token missing 'iss' claim. Cannot determine Keycloak issuer. Discarding.")
            return False
    except Exception as e:
        logger.error(f"Failed to decode token claims: {e}. Discarding.")
        return False

    decoded_token = await validate_token(auth_token, issuer_url)
    if not decoded_token:
        logger.error("Invalid or expired auth_token. Unauthorized. Event discarded.")
        return False

    logger.debug(
        "Authenticated event | publisher='%s' target_user='%s'",
        decoded_token.get("preferred_username"),
        username,
    )
    return True


async def process_message(msg: Any, kv: KeyValue | None) -> None:
    """Authenticate and process a single NATS event."""
    # --- 1. Parse ---
    try:
        data = json.loads(msg.data.decode("utf-8"))
        logger.debug("Received event: %s", data)
    except Exception as e:
        logger.error("Failed to parse message data: %s", e)
        await msg.ack()
        return

    # --- 2. Extract fields ---
    tenant_id          = data.get("tenant_id")
    process_identifier = data.get("process_identifier")
    username           = data.get("username")
    auth_token         = data.get("auth_token")
    event_id           = data.get("id")

    # --- 3. Validate required fields ---
    if not all([tenant_id, process_identifier, username, auth_token]):
        logger.error(
            "Message missing required fields (tenant_id, process_identifier, username, auth_token). "
            "Discarding. data=%s", data,
        )
        await msg.ack()
        return

    # --- 4. Idempotency check (NATS KV) ---
    dedup_key = None
    if event_id and tenant_id:
        dedup_key = await check_idempotency(kv, tenant_id, event_id)
        if dedup_key is None:
            await msg.ack()
            return
    else:
        if not event_id:
            logger.warning("Event has no 'id' field — idempotency cannot be guaranteed.")

    # --- 5. Authenticate: derive issuer from JWT, then validate signature ---
    if not await authenticate_event(auth_token, username):
        await msg.ack()
        return

    # --- 6. Instantiate process (sync DB work in a thread) ---
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
            # Remove the dedup key so a corrected retry is accepted
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
    except Exception as e:
        logger.error("Process instantiation failed: %s", e)
        # Remove the dedup key so the event can be requeued and retried
        if dedup_key and kv:
            try:
                await kv.delete(dedup_key)
            except Exception:
                pass
        await msg.nak(delay=5)  # Requeue — likely a transient DB error


async def main() -> None:
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
            max_reconnect_attempts=-1,
        )
    except (NoServersError, ConnectionError) as e:
        logger.error(f"Failed to connect to NATS: {e}")
        sys.exit(1)

    js = nc.jetstream()

    # --- NATS KV store (for event deduplication) ---
    kv: KeyValue | None = None
    try:
        kv = await js.create_key_value(
            bucket=DEDUP_BUCKET,
            ttl=DEDUP_TTL_SECONDS,
            max_bytes=0, # no limit
            history=1,   # only need 1 revision
        )
        logger.info(f"NATS KV dedup bucket '{DEDUP_BUCKET}' ready (TTL: {DEDUP_TTL_SECONDS}s)")
    except Exception as e:
        logger.warning(f"KV dedup bucket unavailable ({e}) — dedup guard disabled. Events will be processed without idempotency protection.")
        kv = None


    # Ensure the stream exists — create it if it doesn't (idempotent on restart)
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
            pass  # Normal — no messages in this poll window
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
