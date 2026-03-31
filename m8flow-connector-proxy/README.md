# m8flow-connector-proxy
This is the M8Flow Connector Proxy. It serves as an intermediary service enabling seamless communication between the M8Flow engine and external systems. You can configure multiple connectors to be used safely and efficiently in Service Tasks to handle integrations.


# Connectors

Connectors are isolated Python packages that conform to a pre-defined protocol in order to enable communication with external systems. They are designed to be invoked from BPMN Service Tasks within M8Flow.

### Available Connectors

| Connector | Description |
|-----------|-------------|
| [**HTTP**](#http-connector) | Standard HTTP/REST client for API integrations. |
| [**SMTP**](#smtp-connector) | Sending emails via SMTP protocol. |
| [**Postgres**](#postgresql-connector-postgres_v2) | Database operations for PostgreSQL. |
| [**Slack**](#slack-connector) | Sending messages and interacting with Slack APIs. |
| [**Salesforce**](#salesforce-connector)| Integrating with the Salesforce CRM platform. |
| [**Stripe**](#stripe-connector) | Payment processing and billing with Stripe. |

## How to Access Connectors

Connectors are directly integrated into the M8Flow process modeler and are configured using **Service Tasks**. 

To use a connector in your workflow:
1. Select a **Service Task** element in your BPMN diagram.
2. In the properties panel on the right side of the screen, expand the **M8flow Service Properties** section.
3. Use the **Operator ID** dropdown to browse and select the specific connector service and operation you wish to execute.


## General Connector Guidelines

Before configuring any connector, please keep the following rules in mind:
- **Sensitive Data**: All sensitive information (like passwords, API keys, and tokens) should be stored securely in the M8Flow Secrets UI and referenced in your workflow parameters.
- **String Parameters**: When providing a string value directly in the properties panel, you **must** enclose it in double quotes (e.g., `"your-string-value"`).
- **Integer Parameters**: Numeric parameters do not require double quotes and can be entered as plain numbers (e.g., `42`).


## Connector Usage Guides

### HTTP Connector

The HTTP Connector enables BPMN Service Tasks to make outbound HTTP requests (GET, POST, PUT, PATCH, DELETE, HEAD) to external REST APIs. It supports two execution modes: **V1** (runs inside the backend) and **V2** (runs via the external Connector Proxy).


**Configuration in Service Task:**
- **Operator ID:** Select an HTTP operator. Operators ending in `V2` (e.g., `http/GetRequestV2`) use the external proxy, while others (e.g., `http/GetRequest`) run internally.
- **Parameters:** Values can be entered directly, or configured securely in the Secrets UI and accessed using the format `"SPIFF_SECRET:<secret_name>"`.
  - `url` (Required): The API endpoint, enclosed in double quotes (e.g., `"https://jsonplaceholder.typicode.com/posts/1"`).
  - `headers` / `params` / `data`: Must be valid JSON objects. Use `data` for the request body, not `json` (e.g., `{"Accept": "application/json"}`).
  - `basic_auth_username` / `basic_auth_password`: Enclose in double quotes if entered directly, or reference a secret (e.g., `"SPIFF_SECRET:USER_PASSWORD"`).

**Handling Responses:**
Responses from V2 operators are wrapped in a specific format. Use a Script Task to parse the incoming data:
```python
# V2 Handling Example
data = response.get("command_response", {}).get("body", response)
```

---

### SMTP Connector

The SMTP Connector enables BPMN Service Tasks to send emails. It supports plain text, HTML email bodies, file attachments, and authenticated or unauthenticated SMTP configurations.

> **Security Note:** Credentials should never be hardcoded in BPMN models. All sensitive data (such as `smtp_user` and `smtp_password`) must be configured securely via M8Flow Secrets and referenced in your workflow (e.g., `"SPIFF_SECRET:SMTP_PASSWORD"`).

**Configuration in Service Task:**
- **Operator ID:** Select the SMTP email operator (e.g., `SendHTMLEmail`).
- **Required Parameters:** 
  - `smtp_host` (String): The SMTP server address (e.g., `"smtp.example.com"`).
  - `smtp_port` (Integer): The SMTP server port (e.g., `587` or `25`).
  - `email_subject` / `email_body` (String): The subject and plain-text body of the email.
  - `email_to` / `email_from` (String): Delivery recipient and sender addresses. Multiple recipients can be separated by commas or semicolons.
- **Optional Parameters:** 
  - `smtp_user` / `smtp_password`: Required for authentication. Use a secret (e.g., `"SPIFF_SECRET:SMTP_PASSWORD"`) to securely inject the password.
  - `smtp_starttls` (Boolean): Set to `True` to enforce STARTTLS. Enclose boolean values as standard types, not strings.
  - `email_body_html` (String): The HTML version of the email body.
  - `email_cc` / `email_bcc` / `email_reply_to` (String): Additional routing addresses.
  - `attachments` (List of JSON Objects): Add a list of objects containing the `filename` and either a `content_base64` string or a filesystem `path`. *Paths must reside within the allowed `M8FLOW_CONNECTOR_SMTP_ATTACHMENTS_FOLDER`.*

> **Note on UI Warnings:** Some optional fields (such as conditionally required authentication parameters or boolean defaults) may trigger validation warnings in the BPMN Modeler UI. You can safely ignore these warnings as long as your required operational parameters are present.

---

### PostgreSQL Connector (`postgres_v2`)

The PostgreSQL Connector allows you to interact directly with a PostgreSQL database from within M8Flow. It provides operations for executing raw SQL queries, creating and dropping tables, and performing standard CRUD operations (Insert, Select, Update, Delete).

**Configuration in Service Task:**
- **Operator ID:** Select a Postgres operator (e.g., `postgres_v2/SelectValuesV2`, `postgres_v2/DoSQL`, `postgres_v2/InsertValuesV2`).
- **Required Parameters:** 
  - `database_connection_str` (String): The psycopg2 formatted connection string (e.g., `"dbname=mydatabase user=myuser password=mypassword host=192.168.1.9 port=5432"`). *Be sure to safely manage your connection string using M8Flow secrets (e.g., `"SPIFF_SECRET:POSTGRES_CONNECTION_STRING"`) to avoid hardcoding credentials.*
  - `table_name` (String): The target table for your operation. *(Not required if using the `DoSQL` operator)*.
  - `schema` (JSON Object): A dynamic JSON payload that defines the specific command's instructions.
    - **Insert**: `{"columns": ["name", "email"], "values": [["John", "test@example.com"]]}`
    - **Update/Select/Delete**: Use a `"where"` array for filtering (e.g., `{"where": [["email", "=", "test@example.com"]]}`).
    - **DoSQL**: `{"sql": "SELECT id, created_at::text FROM users"}`

**Handling Responses:**
Results, including fetched rows, are saved into a process variable formatted as `task_result__<TaskID>`. You can extract the `body` field from this variable using a Script Task or Post-Script:

```python
# Extract the resulting data array from a task with the ID "FetchUsers"
data = task_result__FetchUsers["body"]
```

> **Warning on Timestamps:** The `SelectValuesV2` operator currently cannot serialize Python `datetime` objects. If you need to query columns that contain timestamps (e.g., `created_at`), do not use `SelectValuesV2`. Instead, use the `DoSQL` operator and explicitly cast the timestamp to text within your query (e.g., `SELECT created_at::text FROM users`).

---

### Slack Connector

The Slack Connector integrates the Slack Web API into your M8Flow workflows, enabling Service Tasks to post messages to channels, send direct messages, and upload files.

**Prerequisites (Slack App Setup):**
1. Create a custom Slack App in your workspace via the [Slack API Developer Portal](https://api.slack.com/apps).
2. Under **OAuth & Permissions**, add the required Bot Token Scopes:
   - `chat:write` *(Required to send messages).*
   - `files:write` *(Required to upload files).*
3. Install the app to your workspace and copy the generated **Bot User OAuth Token** (starts with `xoxb-`).
4. **Channel Membership:** To post messages or files to a specific channel, you must manually invite your bot to that channel inside Slack (e.g., type `/invite @YourBotName`). Direct messages do not require an invite.

**Configuration in Service Task:**
- **Operator ID:** Select a Slack operator: `PostMessage`, `SendDirectMessage`, or `UploadFile`.
- **Required Parameters** (varies by command):
  - `token` (String): Your Slack token. *Always store this securely using M8Flow Secrets (e.g., `"SPIFF_SECRET:SLACL_TOKEN"`).*
  - `channel` or `user_id` (String): The target destination ID (e.g., `"C01234ABCD"`, `"#general"`, or `"U01234ABCD"`).
  - `message` (String): The text content for `PostMessage` or `SendDirectMessage`.
  - `filepath` or `content_base64` (String): Required ONLY for the `UploadFile` operator.

**Optional Formatting (Block Kit):**
For rich, structured messages with buttons or complex layouts, you can provide a JSON array of [Slack Block Kit](https://api.slack.com/block-kit) elements using the optional `blocks` parameter.

> **Bot vs. User Tokens:** A Bot Token (`xoxb-`) posts as the bot itself. If you need to post as an actual human user, you can configure a User Token (`xoxp-`). Be extraordinarily careful with User Tokens as they grant broad permissions and the user must inherently be a member of the target channel for the post to succeed.

---

### Salesforce Connector

The Salesforce Connector integrates your M8Flow workflows with the Salesforce CRM REST API (v58.0), enabling seamless CRUD (Create, Read, Update, Delete) operations for the `Lead` and `Contact` objects.

**Prerequisites (Salesforce Setup):**
1. Log in to your Salesforce account (Developer Edition or Sandbox environments are highly recommended for testing purposes).
2. Create a **Connected App** in the Salesforce App Manager with OAuth Settings enabled and appropriate API access scopes.
3. Retrieve your **Consumer Key** (`client_id`) and **Consumer Secret** (`client_secret`).
4. Generate an active OAuth 2.0 **Access Token** and copy your **Instance URL** (e.g., `https://na50.salesforce.com`).

**Configuration in Service Task:**
- **Operator ID:** Select a Salesforce operation: `CreateLead`, `ReadLead`, `UpdateLead`, `DeleteLead`, `CreateContact`, `ReadContact`, `UpdateContact`, or `DeleteContact`.
- **Authentication Parameters** (Required for all commands):
  - `access_token` (String): Your OAuth 2.0 Access Token. *Always store this securely using M8Flow Secrets (e.g., `"SPIFF_SECRET:SF_ACCESS_TOKEN"`).*
  - `instance_url` (String): Your Salesforce instance URL. *Store securely via secrets.*
  - **Auto-Refresh (Optional):** If you provide the `refresh_token`, `client_id`, and `client_secret` parameters alongside the required ones, the connector will attempt to automatically fetch new tokens if it receives a 401 Unauthorized response.
- **Operation Parameters** (Varies by command):
  - `record_id` (String): The ID of the Salesforce record you want to Read, Update, or Delete (e.g., Leads begin with `00Q`, Contacts with `003`).
  - `fields` (Stringified JSON): A string representing a JSON object that contains the fields you map to the record. This is required for `Create` and `Update` operations. 
    - Example for a Create/Update command: `"{\"LastName\": \"Doe\", \"Company\": \"Acme Corp\"}"`

> **Note on Field Mapping:** When providing the `fields` payload, ensure your data types strictly match the expected Salesforce field definitions (e.g., names are strings, revenue/employee counts are numbers, and dates follow ISO formats). Invalid data types or unrecognized fields will result in validation errors and stop your workflow.

---

### Stripe Connector

The Stripe Connector allows your workflows to connect to Stripe, a popular system for handling payments. With this connector, your automated workflow can take payments or manage recurring subscriptions without needing to know any complex code.

**Supported Actions:**
We currently support the following actions in the connector:
1. **CreatePaymentIntent**: The modern way to process a payment. 
2. **CreateCharge**: The legacy (older) way to process a one-time payment. 
3. **CreateSubscription**: Set up recurring billing for a customer.
4. **CancelSubscription**: Stop an ongoing subscription.

#### Understanding Payment Tokens
You will never type real credit card numbers into your M8Flow workflows. Instead, Stripe uses secure text strings called **tokens** to represent a payment method.

> **How to test payments:** For testing purposes, we give `"tok_visa"` as the payment source. You do not need to use a real credit card or generate any complex codes. Just type the exact word `"tok_visa"` into the **source** field of your Service Task, and Stripe will successfully pretend a real Visa card was used!


#### 1. Getting Your Stripe Account Ready
1. Create a free account at [Stripe](https://stripe.com). You do NOT need to add a real bank account to test the connector.
2. In your Stripe Dashboard, make sure **Test mode** is turned ON (look for the orange "Test mode" toggle in the top-right). Test mode lets you safely try things out without real money.
3. In the left bottom sidebar, click **Developers**, then go to **API keys**.
4. Find your **Secret key** (it will start with `sk_test_`). 
5. Treat this key like a highly sensitive password! NEVER share it or type it directly into your workflow.

#### 2. Configuring the Service Task
When you select a Stripe operation in your workflow, you will need to fill in some details:

- **api_key (Required for all):** Your Stripe Secret Key. *Always keep this safe by using M8Flow Secrets. Just type `"SPIFF_SECRET:stripe_api_key"` as the value.*

**When creating a Payment Intent or Charge:**
- **amount:** The amount you want to charge. *Warning:* Stripe counts money in the smallest unit (like pennies). So, if you want to charge $10.00 USD, entering `"10"` will only charge 10 cents! You must enter `"1000"` for $10.00.
- **currency:** The 3-letter currency code (for example, `"usd"` or `"eur"`).
- **source:** Used when creating a charge to specify how to pay. Use secure tokens here, like `"tok_visa"` for testing.

**When managing Subscriptions:**
- **customer_id:** The unique ID for the person buying the subscription (starts with `cus_`).
- **price_id:** The unique ID for the product plan you created in your Stripe Dashboard.
- **subscription_id:** The active subscription you want to cancel (starts with `sub_`).

**Preventing Duplicate Charges (idempotency_key):**
- All actions have an optional `idempotency_key` parameter. This is a unique transaction label (for example, `"order_12345"`). 
- If your workflow accidentally runs the same task twice, Stripe will check this key. If it sees the same key from earlier that day, it realizes it was already processed and strictly prevents the customer from being charged twice.