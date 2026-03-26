# Sample Templates

Pre-built workflow templates that can be loaded into the database on startup.

## Templates included

| ZIP file | Description |
|----------|-------------|
| [`Single Approval - ( WFH Approval Process with Timeout ).zip`](#template-1) | WFH Approval Process with Timeout |
| [`Two-Step Leave Approval with Email Notifications.zip`](#template-2) | Two-Step Leave Approval with Email Notifications |
| [`Sequential Approval with Rework Loop - ( Content Review & Iteration Workflow ).zip`](#template-3) | Content Review & Iteration Workflow with rework loop |
| [`Approval with Conditional Escalation - ( Expense Claim Process with DMN ).zip`](#template-4) | Expense Claim Process with DMN-based conditional escalation |
| [`Form-Driven Approval with Dynamic Assignee - ( IT Support Complaint Handling ).zip`](#template-5) | IT Support Complaint Handling with dynamic assignee |
| [`Salesforce Lead Creation with Slack Notification.zip`](#template-6) | Salesforce Lead Creation with Slack Notification |
| [`PostgreSQL Table Lifecycle Management.zip`](#template-7) | PostgreSQL Table Lifecycle Management |



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
5. The default tenant (`M8FLOW_DEFAULT_TENANT_ID`, defaults to `default`) owns the templates.

Accepted truthy values: `true`, `1`, `yes`, `on` (case-insensitive).

The variable defaults to `false` so templates are never loaded unless you opt in.

## Manual import via the UI

If you prefer not to enable automatic loading, you can import templates one-by-one through the Templates UI:

1. Download the desired `.zip` file from this directory.
2. Open the M8Flow frontend and navigate to **Templates**.
3. Use the **Import** button and upload the ZIP.

---

## Using Sample Templates

### General Prerequisites

> **Complete all steps below before starting any sample template process. Skipping any step will cause the workflow to fail or stall.**

**1. Ensure all required users exist in your tenant**

Each template assigns tasks to specific users via a `lane_owners` script. All users listed in that script must be created in your tenant before starting the process.

- Go to **Administration → Users** and create any missing users.
- User assignments use the format **`username@tenant_slug`** — replace `your_tenant_slug` with your actual tenant slug (e.g. if your tenant slug is `default`, a user would be `emma@default`).
- After creating each user, assign them an appropriate **role** such as `reviewer` or `editor` so they have the correct permissions to claim and complete tasks.

**2. Update user assignments in the BPMN script task**

Each template contains a script task that sets the `lane_owners` dictionary. You must update the placeholder usernames to match real users in your tenant.

- Open the template in the **Process Editor**.
- Find the script task named "Determine …" or "Resolve …" at the start of the process.
- Update the `lane_owners` values using the **`username@tenant_slug`** format:

```python
lane_owners = {
    "Lane Name": ["username@your_tenant_slug"],
}
```

**3. Configure all required secrets before starting the process**

Templates that integrate with external services (SMTP email, Salesforce, Slack, PostgreSQL) use `SPIFF_SECRET` variables. If a required secret is missing, the service task will fail at runtime.

- Go to **Configuration → Secrets** in the M8Flow UI.
- Add every secret listed in the template's guide below before you start the process.

**4. (Optional) Rename lanes to match your organisation's roles**

The lane names in each template (e.g. `Manager`, `HR`, `Reviewer`) are just labels — you can rename them to match the roles you use in your tenant. For example, if your tenant uses a `reviewer` role instead of `Manager`, you can rename the lane and update the `lane_owners` key to match:

> When you rename a lane to a role name (e.g. `reviewer`), all users in your tenant who have the `reviewer` role will be able to claim and complete tasks in that lane — no individual user assignment is needed.

---

### Template-by-Template Guide

---

<a id="template-1"></a>

#### 1. `Single Approval - ( WFH Approval Process with Timeout ).zip`

This is a single approval workflow for Work From Home requests. It uses a timer so that if the manager does not respond to the request, it will automatically time out after **1 day**.

**Prerequisites:**
- Open the template in the Process Editor and find the **"Resolve WFH Approver"** script task.
- Update the user assignments to match users in your tenant:
  - `emma@your_tenant_slug` — the employee submitting the WFH request
  - `manager@your_tenant_slug` — the manager who reviews and approves/rejects
- Make sure both users are created in your tenant under **Administration → Users**.
- No secrets required for this template.

---

<a id="template-2"></a>

#### 2. `Two-Step Leave Approval with Email Notifications.zip`

This is a two-step leave approval workflow. The employee submits a leave request, the Manager reviews it first, and then HR makes the final decision. Email notifications (approved / rejected) are sent to the employee automatically at each step via SMTP.

**Prerequisites:**
- Open the template in the Process Editor and find the **"Determine Leave Approvers"** script task.
- Update the user assignments to match users in your tenant:
  - `manager@your_tenant_slug` — the manager who does the first review
  - `john@your_tenant_slug` and `emma@your_tenant_slug` — HR members who do the final review
- Make sure all three users are created in your tenant under **Administration → Users**.
- Add the following secrets under **Configuration → Secrets** before starting the process:
  - `SMTP_USER` — your SMTP username / sender email
  - `SMTP_PASSWORD` — your SMTP password or app-specific password
  - `SMTP_HOST` — your SMTP host
  - `SMTP_PORT` — your SMTP port

---

<a id="template-3"></a>

#### 3. `Sequential Approval with Rework Loop - ( Content Review & Iteration Workflow ).zip`

This workflow handles a content review loop. The Publisher submits content, and the Reviewer either approves it or requests changes. If changes are requested, the content goes back to the Publisher for revision. The loop repeats until the Reviewer approves the content.

**Prerequisites:**
- Open the template in the Process Editor and find the **"Determine Reviewer"** script task.
- Update the user assignments to match users in your tenant:
  - `noah@your_tenant_slug` — the publisher who submits and revises content
  - `emma@your_tenant_slug` — the reviewer who approves or requests changes
- Make sure both users are created in your tenant under **Administration → Users**.
- No secrets required for this template.

---

<a id="template-4"></a>

#### 4. `Approval with Conditional Escalation - ( Expense Claim Process with DMN ).zip`

This is an expense claim workflow with DMN-based automatic eligibility checking. The employee submits an expense claim, the Manager reviews it, and if approved, a DMN rule (`check_eligibility`) evaluates whether the claim can be auto-approved or if it needs Finance team review.

**Prerequisites:**
- Open the template in the Process Editor and find the **"Determine Expense Approvers"** script task.
- Update the user assignments to match users in your tenant:
  - `manager@your_tenant_slug` — the manager who does the initial review
  - `james@your_tenant_slug` — the finance member who handles escalated claims
- Make sure both users are created in your tenant under **Administration → Users**.
- No secrets required for this template.

---

<a id="template-5"></a>

#### 5. `Form-Driven Approval with Dynamic Assignee - ( IT Support Complaint Handling ).zip`

This workflow handles IT support complaints. The submitter registers a complaint and selects a complaint type (Hardware or Software). The workflow then dynamically routes the complaint to the correct support team member based on the type selected.

**Prerequisites:**
- Open the template in the Process Editor and find the **"Determine Support Team"** script task.
- Update the user assignments to match users in your tenant:
  - `emma@your_tenant_slug` — handles Hardware complaints
  - `john@your_tenant_slug` — handles Software complaints
- Make sure both users are created in your tenant under **Administration → Users**.
- No secrets required for this template.

---

<a id="template-6"></a>

#### 6. `Salesforce Lead Creation with Slack Notification.zip`

This workflow allows any user to enter lead details via a form, creates the lead in Salesforce using the API, and then sends a notification to a Slack channel confirming the lead was created.

**Prerequisites:**
- No specific user lane assignments — any logged-in user can start this process.
- Add the following secrets under **Configuration → Secrets** before starting the process:
  - `SF_ACCESS_TOKEN` — Salesforce OAuth access token
  - `SF_INSTANCE_URL` — your Salesforce instance URL (e.g. `https://yourorg.salesforce.com`)
  - `SF_REFRESH_TOKEN` — Salesforce OAuth refresh token
  - `SF_CLIENT_ID` — Salesforce Connected App client ID
  - `SF_CLIENT_SECRET` — Salesforce Connected App client secret
  - `SLACK_TOKEN` — Slack Bot token (starts with `xoxb-`)
  - `SLACK_CHANNEL_ID` — the ID of the Slack channel to post the notification to

---

<a id="template-7"></a>

#### 7. `PostgreSQL Table Lifecycle Management.zip`

This workflow demonstrates reading from and writing to a PostgreSQL database directly through the workflow engine. It walks through a user registration scenario where data is inserted into and retrieved from a Postgres table.

**Prerequisites:**
- No specific user lane assignments — any logged-in user can start this process.
- Add the following secret under **Configuration → Secrets** before starting the process:
  - `POSTGRES_CONNECTION_STRING` — full PostgreSQL connection string, e.g. `dbname=databasename user=username password=password host=hostname port=portnumber`
