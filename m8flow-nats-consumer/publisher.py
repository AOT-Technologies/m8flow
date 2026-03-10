import argparse
import asyncio
import json
import logging
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv
from nats.aio.client import Client as NATS
from nats.js.errors import NotFoundError

load_dotenv()

logger = logging.getLogger("m8flow.nats.publisher")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

NATS_URL     = os.environ["M8FLOW_NATS_URL"]
STREAM_NAME  = os.environ["M8FLOW_NATS_STREAM_NAME"]
KEYCLOAK_URL = os.environ["KEYCLOAK_URL"]


async def fetch_token(keycloak_base_url: str, realm: str, client_id: str, client_secret: str) -> str | None:
    """Fetch an access token from Keycloak using Client Credentials Grant."""
    token_url = f"{keycloak_base_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_url,
                data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json().get("access_token")
    except Exception as e:
        logger.error(f"Failed to fetch token from {token_url}: {e}")
        return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a signed M8Flow NATS event")
    parser.add_argument("--tenant_id",          required=True,  help="M8Flow tenant UUID")
    parser.add_argument("--process_identifier", required=True,  help="BPMN process path, e.g. group/process-model")
    parser.add_argument("--username",           required=True,  help="M8Flow user who will own the process instance")
    parser.add_argument("--realm",              required=True,  help="Keycloak realm name (e.g. 'spiffworkflow')")
    parser.add_argument("--client_id",          required=True,  help="Keycloak client ID (e.g. 'spiffworkflow-backend')")
    parser.add_argument("--client_secret",      required=True,  help="Keycloak client secret")
    parser.add_argument("--payload",            default="{}",   help="JSON string injected as process variables")
    args = parser.parse_args()

    try:
        payload_dict = json.loads(args.payload)
    except json.JSONDecodeError:
        logger.error("--payload is not valid JSON.")
        sys.exit(1)


    # Fetch JWT
    logger.info(f"Fetching token from Keycloak (realm={args.realm}, client={args.client_id})...")
    auth_token = await fetch_token(KEYCLOAK_URL, args.realm, args.client_id, args.client_secret)
    if not auth_token:
        logger.error("Could not obtain auth token. Exiting.")
        sys.exit(1)
    logger.info("Token obtained successfully.")

    # Connect to NATS
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
        "process_identifier": args.process_identifier,
        "username":           args.username,
        "auth_token":         auth_token,
        "payload":            payload_dict,
    }

    logger.info(f"Publishing to subject: {subject}")
    logger.info(f"Event data: {json.dumps(event_data, indent=2)}")

    try:
        # Nats-Msg-Id enables JetStream broker-level deduplication:
        # if the same event_id is published again within the dedup window
        # (default 2 min), the server discards the duplicate silently.
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
