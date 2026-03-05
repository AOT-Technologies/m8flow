# Integrating External Systems with M8Flow via NATS

This guide is for developers who want an external system (e.g., a billing service, e-commerce platform, or IoT device) to trigger M8Flow workflows by publishing events.

---

## 1. How It Works

You publish a JSON event to M8Flow's NATS server. The event must carry:

- A **Keycloak JWT** (`auth_token`) — proves your system is authorized to trigger events
- A **username** — the M8Flow user who will own the created workflow instance

M8Flow validates the token, looks up the user, and starts the workflow.

---

## 2. What You Need (from the M8Flow operator)

Before you can publish events, the M8Flow platform team must provision the following for your system:

| Credential             | Description                                                            |
| ---------------------- | ---------------------------------------------------------------------- |
| **NATS URL**           | e.g. `nats://nats.m8flow.ai:4222` (or `tls://...` for production)      |
| **Keycloak URL**       | e.g. `https://auth.m8flow.ai`                                          |
| **Keycloak Realm**     | e.g. `spiffworkflow`                                                   |
| **Client ID**          | `spiffworkflow-backend` (built-in client, no new client needed)        |
| **Client Secret**      | The secret for `spiffworkflow-backend` (from Keycloak Credentials tab) |
| **Tenant ID**          | Your M8Flow tenant UUID                                                |
| **Process Identifier** | The BPMN process path to trigger, e.g. `billing/invoice-paid`          |
| **Username**           | An M8Flow username your events should run as                           |

---

## 3. NATS Connectivity

NATS is **not HTTP** — it uses its own TCP-based protocol on port **4222**.

| Environment                 | NATS URL                    |
| --------------------------- | --------------------------- |
| Local development           | `nats://localhost:4222`     |
| LAN / staging               | `nats://192.168.x.x:4222`   |
| Production (e.g. m8flow.ai) | `tls://nats.m8flow.ai:4222` |

> For production, use `tls://` to encrypt traffic. Standard HTTP reverse proxies (nginx, etc.) cannot terminate NATS connections — port 4222 must be open directly on the host.

---

## 4. Publishing an Event

### Step 1: Get a JWT from Keycloak

```bash
curl -s -X POST \
  "https://auth.m8flow.ai/realms/spiffworkflow/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=spiffworkflow-backend" \
  -d "client_secret=<spiffworkflow-backend-secret>" \
  | jq -r '.access_token'
```

### Step 2: Publish to NATS

The event payload must be published to the subject:

```
m8flow.events.{tenant_id}.trigger
```

#### Python (using nats-py)

```python
import asyncio, json, httpx
import nats

NATS_URL      = "tls://nats.m8flow.ai:4222"
KEYCLOAK_URL  = "https://auth.m8flow.ai"
REALM         = "spiffworkflow"
CLIENT_ID     = "spiffworkflow-backend"
CLIENT_SECRET = "<spiffworkflow-backend-secret>"
TENANT_ID     = "your-m8flow-tenant-uuid"
USERNAME      = "john.doe@company.com"   # M8Flow user who owns the process
PROCESS       = "billing/invoice-paid"

async def main():
    # 1. Fetch JWT
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
            data={"grant_type": "client_credentials",
                  "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]

    # 2. Publish to NATS
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()

    event = {
        "tenant_id":          TENANT_ID,
        "process_identifier": PROCESS,
        "username":           USERNAME,
        "auth_token":         token,
        "payload": {
            "invoice_id": "INV-001",
            "amount":     500
        }
    }

    await js.publish(
        f"m8flow.events.{TENANT_ID}.trigger",
        json.dumps(event).encode()
    )
    print("Event published.")
    await nc.close()

asyncio.run(main())
```

#### Node.js (using nats.js)

```js
import { connect, StringCodec } from "nats";
import fetch from "node-fetch";

const NATS_URL = "tls://nats.m8flow.ai:4222";
const KEYCLOAK_URL = "https://auth.m8flow.ai";
const REALM = "spiffworkflow";
const CLIENT_ID = "spiffworkflow-backend";
const CLIENT_SECRET = "<spiffworkflow-backend-secret>";
const TENANT_ID = "your-m8flow-tenant-uuid";
const USERNAME = "john.doe@company.com";
const PROCESS = "billing/invoice-paid";

// 1. Fetch JWT
const tokenResp = await fetch(
  `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token`,
  {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
    }),
  },
);
const { access_token } = await tokenResp.json();

// 2. Publish to NATS
const nc = await connect({ servers: NATS_URL });
const js = nc.jetstream();
const sc = StringCodec();

await js.publish(
  `m8flow.events.${TENANT_ID}.trigger`,
  sc.encode(
    JSON.stringify({
      tenant_id: TENANT_ID,
      process_identifier: PROCESS,
      username: USERNAME,
      auth_token: access_token,
      payload: { invoice_id: "INV-001", amount: 500 },
    }),
  ),
);

await nc.close();
```

---

## 5. Event Schema Reference

| Field                | Type   | Required | Description                                    |
| -------------------- | ------ | -------- | ---------------------------------------------- |
| `tenant_id`          | string | ✅       | M8Flow tenant UUID                             |
| `process_identifier` | string | ✅       | BPMN process path, e.g. `group/process-name`   |
| `username`           | string | ✅       | M8Flow user who will own the process instance  |
| `auth_token`         | string | ✅       | Keycloak JWT (Client Credentials access token) |
| `payload`            | object | No       | Arbitrary JSON injected as workflow variables  |

---

## 6. Security Notes

- The JWT has a short expiry (typically 5 minutes). Fetch a fresh token before each publish.
- `auth_token` authenticates the **publisher** (is this system allowed to publish?). `username` controls **process ownership** (which M8Flow user runs the workflow). These are separate concerns.
- For production, configure NATS with username/password or NKeys so only provisioned clients can connect to port 4222.
- Never embed `client_secret` in client-side or browser code — this flow is for server-to-server only.
