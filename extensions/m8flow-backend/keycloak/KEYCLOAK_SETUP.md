# Keycloak Setup Guide

## Overview

The `start_keycloak.sh` script automatically starts a Keycloak Docker container and imports two realms:
- **identity** realm (imported first)
- **tenant-a** realm (imported second)

## Prerequisites

- Docker installed and running
- `curl` command available
- `jq` command available
- Realm export files present:
  - `realm_exports/identity-realm-export.json`
  - `realm_exports/tenant-realm-export.json`

## Spoke client JWT keystore (keystore.p12)

For spoke-realm token/login and JWT client authentication, the backend uses a PKCS#12 keystore. Generate it **manually** from the repo root with the backend venv active:

```bash
# From repo root (default output: extensions/m8flow-backend/keystore.p12)
python extensions/m8flow-backend/bin/generate_keystore_p12.py

# Custom path and password
python extensions/m8flow-backend/bin/generate_keystore_p12.py -o /path/to/keystore.p12 -p yourpassword

# Use env for password (no prompt)
export M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD=yourpassword
python extensions/m8flow-backend/bin/generate_keystore_p12.py
```

**Options:**

- `-o`, `--output` — Output path (default: `extensions/m8flow-backend/keystore.p12` from cwd)
- `-p`, `--password` — Keystore password (or set `M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD`; otherwise you are prompted)
- `--days` — Certificate validity in days (default: 365)
- `--cn` — Certificate common name (default: `spiffworkflow-backend`)

After generating, set in your environment (or `.env`):

- `M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12` — Path to the `.p12` file (optional if using the default path)
- `M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD` — Keystore password

The script requires the `cryptography` package (provided by the backend venv).

## Admin user for realm APIs

The backend’s create-realm and partial-import APIs use a Keycloak master-realm admin user. When using the Keycloak Docker image with the standard entrypoint (`keycloak-entrypoint.sh`), a permanent **superadmin** user is created with roles needed for realm creation and partial import. The backend defaults to username **superadmin**. Set `KEYCLOAK_ADMIN_PASSWORD` or `M8FLOW_KEYCLOAK_ADMIN_PASSWORD` to the superadmin password (same as `KEYCLOAK_SUPERADMIN_PASSWORD` in the Keycloak container) so the backend can authenticate. Override the username with `KEYCLOAK_ADMIN_USER` or `M8FLOW_KEYCLOAK_ADMIN_USER` if you use a different admin user.

## Usage

```bash
cd extensions/m8flow-backend/bin
./start_keycloak.sh
```

## What the Script Does

1. **Validates environment**: Checks for required tools (docker, curl, jq) and realm export files
2. **Sets up Docker network**: Creates or verifies the `m8flow` network exists
3. **Manages container**: Stops and removes any existing `keycloak` container, then starts a new one
4. **Starts Keycloak**: Runs Keycloak 26.0.7 in Docker with:
   - Port 7002 (HTTP API)
   - Port 7009 (Health check)
   - Admin credentials: `admin` / `admin`
5. **Waits for readiness**: Polls health endpoint until Keycloak is ready
6. **Imports realms**: 
   - Checks if each realm already exists (skips if found)
   - Imports `identity` realm first
   - Imports `tenant-a` realm second

## Keycloak Access

- **Admin Console**: http://localhost:7002
- **Admin Username**: `admin`
- **Admin Password**: `admin`
- **API Base URL**: http://localhost:7002

## Realm Import Behavior

- If a realm already exists, the script will skip importing it (no error)
- If a realm doesn't exist, it will be imported automatically
- The script handles HTTP 409 (Conflict) gracefully if a realm is created between the check and import

## Realm template and RBAC users

When new tenant realms are created (e.g. via the create-realm API), they are provisioned from the realm template `realm_exports/spiffworkflow-realm.json`. The template includes:

- **RBAC realm roles:** `editor`, `super-admin`, `tenant-admin`, `integrator`, `reviewer`, `viewer`
- **One user per role:** usernames `editor`, `integrator`, `reviewer`, `super-admin`, `tenant-admin`, `viewer`, each assigned the matching realm role

These users are created with a **default password** (shared placeholder in the template). For security, admins should change these passwords after tenant creation, or configure Keycloak required actions (e.g. "Update Password") to force a password change on first login.

**Permissions and role alignment:** For the backend to grant API and UI permissions, Keycloak realm role names must match the group names defined in `m8flow.yml`: `super-admin`, `tenant-admin`, `editor`, `viewer`, `integrator`, `reviewer`. The template’s **spiffworkflow-backend** client includes a "groups" protocol mapper that adds the user’s realm roles to the token as the `groups` claim (ID and access token). On login, the backend reads this claim and adds the user to the corresponding Spiffworkflow groups, then applies permissions from `m8flow.yml`. Do not rename these realm roles in the template without updating `m8flow.yml` to match.

## Troubleshooting

- **Port conflicts**: Ensure ports 7002 and 7009 are not in use
- **Docker issues**: Verify Docker is running and you have permissions
- **Import failures**: Check that realm export JSON files are valid and accessible
- **Network issues**: The script creates the `m8flow` network if it doesn't exist

## Stopping Keycloak

To stop the Keycloak container:

```bash
docker stop keycloak
```

To remove the container:

```bash
docker rm keycloak
```
