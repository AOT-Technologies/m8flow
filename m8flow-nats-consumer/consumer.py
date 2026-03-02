"""
consumer.py - M8Flow NATS Consumer Service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Standalone Python service that listens to NATS JetStream, decodes events,
derives the appropriate per-tenant API key, and creates process instances
in the M8Flow backend.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
from typing import Any

from dotenv import load_dotenv
from nats.aio.client import Client as NATS
from nats.errors import ConnectionClosedError, TimeoutError, NoServersError
from nats.js.errors import NotFoundError

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

# Config from Env
NATS_URL = os.environ.get("M8FLOW_NATS_URL", "nats://localhost:4222")
STREAM_NAME = os.environ.get("M8FLOW_NATS_STREAM_NAME", "M8FLOW_EVENTS")
SUBJECT = os.environ.get("M8FLOW_NATS_SUBJECT", "m8flow.events.>")
DURABLE_NAME = os.environ.get("M8FLOW_NATS_DURABLE_NAME", "m8flow-engine-consumer")
FETCH_BATCH = int(os.environ.get("M8FLOW_NATS_FETCH_BATCH", "10"))
FETCH_TIMEOUT = float(os.environ.get("M8FLOW_NATS_FETCH_TIMEOUT", "2.0"))

BACKEND_URL = os.environ.get("M8FLOW_BACKEND_URL", "http://localhost:8000")
NATS_API_KEY = os.environ.get("M8FLOW_NATS_API_KEY") # Optional global default

running = True


async def process_message(msg: Any) -> None:
    """Decode NATS message and forward to backend."""
    try:
        data = json.loads(msg.data.decode("utf-8"))
        logger.debug("Received event: %s", data)
    except Exception as e:
        logger.error("Failed to parse message data: %s", e)
        await msg.ack()  # Unparsable, discard
        return

    tenant_id = data.get("tenant_id")
    process_identifier = data.get("process_identifier")
    username = data.get("username")

    if not tenant_id or not process_identifier:
        logger.error(
            "Message missing required fields (tenant_id, process_identifier). Discarding. data=%s",
            data,
        )
        await msg.ack()
        return

    from extensions.app import app as flask_app
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.process_model_service import ProcessModelService
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id

    def execute_process_instantiation():
        with flask_app.app_context():
            token = set_context_tenant_id(tenant_id)
            try:
                target_user = username or "tenant-admin@spiffworkflow"
                user = UserModel.query.filter_by(username=target_user).first()
                if not user:
                    # Fallback for old/bad messages in the durable queue that hardcoded "tenant-admin"
                    user = UserModel.query.filter_by(username="tenant-admin@spiffworkflow").first()

                if not user:
                    logger.error(f"User '{target_user}' not found in the database. Cannot start process instance.")
                    return None

                from spiffworkflow_backend.services.file_system_service import FileSystemService
                print(f"!!! Looking for process model {process_identifier} in root_path: {FileSystemService.root_path()} tenant_id {tenant_id}", flush=True)
                
                try:
                    process_model = ProcessModelService.get_process_model(process_identifier)
                except Exception as e:
                    logger.error(f"Process model {process_identifier} not found: {e}")
                    return None
                    
                if not process_model:
                     logger.error(f"Process model {process_identifier} not found")
                     return None

                data_to_inject = data.get("payload", {})
                if username:
                    data_to_inject["_nats_initiator_username"] = target_user

                processor = ProcessInstanceService.create_and_run_process_instance(
                    process_model=process_model,
                    persistence_level="persistent",
                    data_to_inject=data_to_inject,
                    user=user,
                )
                db.session.commit()
                return processor.process_instance_model.id
            except Exception as e:
                db.session.rollback()
                raise e
            finally:
                reset_context_tenant_id(token)

    try:
        # Run the synchronous database operation in an executor to avoid blocking the async event loop
        instance_id = await asyncio.to_thread(execute_process_instantiation)
        
        if instance_id is None:
            logger.warning("Event processing aborted: Pre-requisites not met (e.g., user not found).")
            await msg.ack()
            return
            
        logger.info(
            "Process instance created natively | tenant=%s identifier=%s instance_id=%s",
            tenant_id,
            process_identifier,
            instance_id,
        )
        await msg.ack()
    except Exception as e:
        logger.error("Native process instantiation failed: %s", e)
        # We nak to requeue it, could be a transient DB error
        await msg.nak(delay=5)


async def main():
    if not NATS_API_KEY:
        logger.warning("M8FLOW_NATS_API_KEY not set. Backend calls will fail unless 'api_key' is provided in the event payloads.")

    logger.info("Starting M8Flow NATS Consumer...")
    
    nc = NATS()

    async def disconnected_cb():
        logger.warning("Disconnected from NATS")

    async def reconnected_cb():
        logger.info(f"Reconnected to NATS at {nc.connected_url.netloc}")

    async def error_cb(e):
        logger.error(f"NATS Connection Error: {e}")

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

    # The stream should be created by the NATS docker container entrypoint.
    # We verify it exists before trying to subscribe.
    try:
        await js.stream_info(STREAM_NAME)
    except NotFoundError:
        logger.error(
            f"Stream '{STREAM_NAME}' does not exist. Ensure NATS stream initialization script ran."
        )
        await nc.close()
        sys.exit(1)

    # Create durable pull subscription
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
            # Poll for batch of messages
            msgs = await sub.fetch(batch=FETCH_BATCH, timeout=FETCH_TIMEOUT)
            for msg in msgs:
                await process_message(msg)
        except TimeoutError:
            # Normal heartbeat
            pass
        except ConnectionClosedError:
            logger.warning("NATS connection closed, exiting loop.")
            break
        except Exception as e:
            logger.exception("Unexpected error in consumer loop: %s", e)
            await asyncio.sleep(1)

    logger.info("Closing NATS connection...")
    await nc.close()
    logger.info("Consumer shutdown complete.")


def handle_shutdown(sig, frame):
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
