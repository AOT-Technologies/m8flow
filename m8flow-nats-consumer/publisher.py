"""
publisher.py - M8Flow NATS Publisher Dev Utility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Utility for developers to inject M8Flow events directly into NATS
to test the m8flow-nats-consumer service.

Usage:
  python publisher.py --tenant_id my-tenant --process_identifier my-group/my-model
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import uuid

from nats.aio.client import Client as NATS
from nats.js.errors import NotFoundError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

NATS_URL = os.environ.get("M8FLOW_NATS_URL", "nats://localhost:4222")
STREAM_NAME = os.environ.get("M8FLOW_NATS_STREAM_NAME", "M8FLOW_EVENTS")


async def main():
    parser = argparse.ArgumentParser(description="Publish M8Flow NATS events")
    parser.add_argument("--tenant_id", required=True, help="Target tenant slug or id")
    parser.add_argument(
        "--process_identifier", required=True, help="e.g. process-group/process-model"
    )
    parser.add_argument("--username", default="system", help="User triggering event")
    parser.add_argument("--api_key", default=None, help="Optional SpiffWorkflow API Key for this event")
    parser.add_argument(
        "--payload", default="{}", help="JSON payload to inject as data"
    )

    args = parser.parse_args()

    try:
        payload_dict = json.loads(args.payload)
    except json.JSONDecodeError:
        logging.error("Invalid JSON payload.")
        sys.exit(1)

    nc = NATS()
    try:
        await nc.connect(NATS_URL)
    except Exception as e:
        logging.error(f"Failed to connect to NATS at {NATS_URL}: {e}")
        sys.exit(1)

    js = nc.jetstream()

    # Build the EventMessage payload
    event_id = str(uuid.uuid4())
    subject = f"m8flow.events.{args.tenant_id}.trigger"

    event_data = {
        "id": event_id,
        "subject": subject,
        "tenant_id": args.tenant_id,
        "username": args.username,
        "process_identifier": args.process_identifier,
        "payload": payload_dict,
    }

    if args.api_key:
        event_data["api_key"] = args.api_key

    event_json = json.dumps(event_data).encode("utf-8")

    logging.info(f"Publishing to subject: {subject}")
    logging.info(f"Data: {json.dumps(event_data, indent=2)}")

    try:
        ack = await js.publish(subject, event_json)
        logging.info(f"Successfully published! stream={ack.stream}, seq={ack.seq}")
    except NotFoundError:
         logging.error(f"Stream '{STREAM_NAME}' does not exist. Start consumer or NATS server first.")
    except Exception as e:
        logging.error(f"Publish failed: {e}")

    await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
