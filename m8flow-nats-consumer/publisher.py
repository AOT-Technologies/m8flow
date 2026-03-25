import argparse
import asyncio
import json
import logging
import os
import sys
import uuid

from dotenv import load_dotenv
from nats.aio.client import Client as NATS
from nats.js.errors import NotFoundError

load_dotenv()

logger = logging.getLogger("m8flow.nats.publisher")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

NATS_URL     = os.environ["M8FLOW_NATS_URL"]
STREAM_NAME  = os.environ["M8FLOW_NATS_STREAM_NAME"]

async def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a signed M8Flow NATS event")
    parser.add_argument("--tenant_id",          required=True,  help="M8Flow tenant UUID")
    parser.add_argument("--process_identifier", required=True,  help="BPMN process path, e.g. group/process-model")
    parser.add_argument("--username",           required=True,  help="M8Flow user who will own the process instance")
    parser.add_argument("--payload",            default="{}",   help="JSON string injected as process variables")
    parser.add_argument("--api_key",            required=True,  help="M8Flow API key (from /nats-tokens API)")
    args = parser.parse_args()

    if not args.api_key:
        logger.error("--api_key is required.")
        sys.exit(1)

    try:
        payload_dict = json.loads(args.payload)
    except json.JSONDecodeError:
        logger.error("--payload is not valid JSON.")
        sys.exit(1)

    nc = NATS()
    try:
        await nc.connect(NATS_URL)
    except Exception as e:
        logger.error(f"Failed to connect to NATS at {NATS_URL}: {e}")
        sys.exit(1)

    js = nc.jetstream()
    subject = f"m8flow.events.{args.tenant_id}.trigger"

    event_id = str(uuid.uuid4())
    event_data = {
        "id":                 event_id,
        "subject":            subject,
        "tenant_id":          args.tenant_id,
        "api_key":            args.api_key,
        "process_identifier": args.process_identifier,
        "username":           args.username,
        "payload":            payload_dict,
    }

    logger.info(f"Publishing to subject: {subject}")
    logger.info(f"Event data: {event_data}")

    try:
        ack = await js.publish(
            subject,
            json.dumps(event_data).encode("utf-8"),
            headers={"Nats-Msg-Id": event_id},
        )
        logger.info(f"Published successfully. stream={ack.stream}, seq={ack.seq}")
    except NotFoundError:
        logger.error(f"Stream '{STREAM_NAME}' does not exist. Ensure the NATS server is running.")
    except Exception as e:
        logger.error(f"Publish failed: {e}")
    finally:
        await nc.close()

if __name__ == "__main__":
    asyncio.run(main())
