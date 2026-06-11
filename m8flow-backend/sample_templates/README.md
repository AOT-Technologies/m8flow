# Sample Templates

Pre-built workflow templates that can be loaded into the database on startup.

## Templates included

| ZIP file | Description |
|----------|-------------|
| [`Single Approval - ( WFH Approval Process with Timeout ).zip`](#template-1) | WFH Approval Process with Timeout |
| [`Two-Step Leave Approval with Email Notifications.zip`](#template-2) | Two-Step Leave Approval with Email Notifications |
| [`Approval with Conditional Escalation - ( Expense Claim Process with DMN ).zip`](#template-3) | Expense Claim Process with DMN-based conditional escalation |
| [`Form-Driven Approval with Dynamic Assignee - ( IT Support Complaint Handling ).zip`](#template-4) | IT Support Complaint Handling with dynamic assignee |
| [`Salesforce Lead Creation with Slack Notification.zip`](#template-5) | Salesforce Lead Creation with Slack Notification |
| [`PostgreSQL Table Lifecycle Management.zip`](#template-6) | PostgreSQL Table Lifecycle Management |



## Automatic loading via environment variable

Set `M8FLOW_LOAD_SAMPLE_TEMPLATES=true` in your `.env` file (or export it) before starting the backend:

```env
M8FLOW_LOAD_SAMPLE_TEMPLATES=true
```

On startup the backend will:

1. Scan this directory for `.zip` files.
2. Skip any template whose key already exists in the database (no duplicates).
3. Extract each ZIP file, store the contained files on the filesystem, and insert a row into the `m8flow_templates` table.
4. Templates are created as **PUBLIC** and **published**, so every user can see and use them immediately.
5. The canonical shared-realm tenant owns the templates.

Accepted truthy values: `true`, `1`, `yes`, `on` (case-insensitive).

The variable defaults to `false` so templates are never loaded unless you opt in.

## Manual import via the UI

If you prefer not to enable automatic loading, you can import templates one-by-one through the Templates UI:

1. Download the desired `.zip` file from this directory.
2. Open the M8Flow frontend and navigate to **Templates**.
3. Use the **Import** button and upload the ZIP.

---

# User Assignment Using Keycloak Groups

Each user/manual task is placed in a **BPMN lane named after a Keycloak group**. At runtime the task is offered to every member of that group in the active tenant — no per-user configuration is required.

### Default Groups

| Group           | Purpose                                |
| --------------- | -------------------------------------- |
| Submitters     | Users initiating requests              |
| Approvers      | Approval and review activities         |
| Designers      | Content creation and design activities |
| Support        | Support and complaint handling         |
| Administrators | Administrative and operational tasks   |
| Viewers        | Read-only access                       |

These groups are provisioned by default in every tenant (see `src/m8flow_backend/config/keycloak/default_groups.json`). Add users to the relevant group under **Administration → Groups** (or in Keycloak) and they will immediately be able to claim and complete tasks in the matching lane.

### Benefits

- No hardcoded users
- Easier environment setup
- Better RBAC alignment
- Consistent template behavior across deployments
- Simplified onboarding

## Using Sample Templates

### General Prerequisites

> **Complete all steps below before starting any sample template process. Skipping any step will cause the workflow to fail or stall.**

**1. Ensure the default groups have members**

Each template assigns tasks to the default Keycloak groups above. Make sure the groups used by the template you are running (for example `Submitters` and `Approvers`) have at least one member in your tenant.

- Go to **Administration → Groups** and add users to the relevant groups.
- Any member of a lane's group can claim and complete that lane's tasks — no individual user assignment is needed.

**2. Configure all required secrets before starting the process**

Templates that integrate with external services (SMTP email, Salesforce, Slack, PostgreSQL) use `M8FLOW_SECRET` variables. If a required secret is missing, the service task will fail at runtime.

- Go to **Configuration → Secrets** in the M8Flow UI.
- Add every secret listed in the template's guide below before you start the process.

**3. (Optional) Map lanes to different groups**

The lane names in each template (e.g. `Approvers`, `Support`) correspond directly to Keycloak group identifiers. If your tenant organises work under different groups, open the template in the **Process Editor**, select the lane, and rename it to the target group identifier (for example `Reviewers`). Everyone in that group will then be able to claim and complete the lane's tasks.

---

### Template-by-Template Guide

---

<a id="template-1"></a>

#### 1. `Single Approval - ( WFH Approval Process with Timeout ).zip`

This is a single approval workflow for Work From Home requests. It uses a timer so that if the manager does not respond to the request, it will automatically time out after **1 day**.

**Task assignment (Keycloak groups):**
- **Submit WFH Request** → `Submitters`
- **Review WFH Request** → `Approvers`

**Prerequisites:**
- Make sure the `Submitters` and `Approvers` groups have members in your tenant (**Administration → Groups**).
- No secrets required for this template.

---

<a id="template-2"></a>

#### 2. `Two-Step Leave Approval with Email Notifications.zip`

This is a two-step leave approval workflow. The employee submits a leave request, the Manager reviews it first, and then HR makes the final decision. Email notifications (approved / rejected) are sent to the employee automatically at each step via SMTP.

**Task assignment (Keycloak groups):**
- **Submit Leave Request** → `Submitters`
- **Manager Review Leave Request** → `Approvers`
- **HR Review Leave Request** → `Approvers`

**Prerequisites:**
- Make sure the `Submitters` and `Approvers` groups have members in your tenant (**Administration → Groups**).
- Add the following secrets under **Configuration → Secrets** before starting the process:
  - `SMTP_USER` — your SMTP username / sender email
  - `SMTP_PASSWORD` — your SMTP password or app-specific password
  - `SMTP_HOST` — your SMTP host
  - `SMTP_PORT` — your SMTP port

---

<a id="template-3"></a>

#### 3. `Approval with Conditional Escalation - ( Expense Claim Process with DMN ).zip`

This is an expense claim workflow with DMN-based automatic eligibility checking. The employee submits an expense claim, the Manager reviews it, and if approved, a DMN rule (`check_eligibility`) evaluates whether the claim can be auto-approved or if it needs Finance team review.

**Task assignment (Keycloak groups):**
- **Submit Expense Claim** → `Submitters`
- **Review Expense Claim** (Manager) → `Approvers`
- **Review Expense Claim (Finance)** → `Approvers`

The DMN auto-approval logic (`check_eligibility`) is unchanged.

**Prerequisites:**
- Make sure the `Submitters` and `Approvers` groups have members in your tenant (**Administration → Groups**).
- No secrets required for this template.

---

<a id="template-4"></a>

#### 4. `Form-Driven Approval with Dynamic Assignee - ( IT Support Complaint Handling ).zip`

This workflow handles IT support complaints. The submitter registers a complaint and selects a complaint type (Hardware or Software). The workflow then dynamically routes the complaint to the correct support team member based on the type selected.

**Task assignment (Keycloak groups):**
- **Submit Customer Complaint** → `Submitters`
- **Review Software Complaint** → `Approvers`
- **Review Hardware Complaint** → `Approvers`

Gateway routing based on `complaint_type` is unchanged.

**Prerequisites:**
- Make sure the `Submitters` and `Approvers` groups have members in your tenant (**Administration → Groups**).
- No secrets required for this template.

---

<a id="template-5"></a>

#### 5. `Salesforce Lead Creation with Slack Notification.zip`

This workflow allows any user to enter lead details via a form, creates the lead in Salesforce using the API, and then sends a notification to a Slack channel confirming the lead was created.

**Task assignment (Keycloak groups):**
- **Enter Lead Details** (data entry) → `Submitters`
- **Process Completed** (manual confirmation) → `Administrators`

The data-preparation script tasks (Initialize Lead Data, Prepare Salesforce Payload, Prepare Slack Notification) are not user-assignment scripts and are unchanged.

**Prerequisites:**
- Make sure the `Submitters` and `Administrators` groups have members in your tenant (**Administration → Groups**).
- Add the following secrets under **Configuration → Secrets** before starting the process:
  - `SF_ACCESS_TOKEN` — Salesforce OAuth access token
  - `SF_INSTANCE_URL` — your Salesforce instance URL (e.g. `https://yourorg.salesforce.com`)
  - `SF_REFRESH_TOKEN` — Salesforce OAuth refresh token
  - `SF_CLIENT_ID` — Salesforce Connected App client ID
  - `SF_CLIENT_SECRET` — Salesforce Connected App client secret
  - `SLACK_TOKEN` — Slack Bot token (starts with `xoxb-`)
  - `SLACK_CHANNEL_ID` — the ID of the Slack channel to post the notification to

---

<a id="template-6"></a>

#### 6. `PostgreSQL Table Lifecycle Management.zip`

This workflow demonstrates reading from and writing to a PostgreSQL database directly through the workflow engine. It walks through a user registration scenario where data is inserted into and retrieved from a Postgres table.

**Task assignment (Keycloak groups):**
- All manual tasks — **Confirm Table Creation**, **Confirm Data Insertion**, **Display Records**, **Deletion Completed** → `Administrators`

The PostgreSQL database service tasks are unchanged.

**Prerequisites:**
- Make sure the `Administrators` group has members in your tenant (**Administration → Groups**).
- Add the following secret under **Configuration → Secrets** before starting the process:
  - `POSTGRES_CONNECTION_STRING` — full PostgreSQL connection string, e.g. `dbname=databasename user=username password=password host=hostname port=portnumber`
