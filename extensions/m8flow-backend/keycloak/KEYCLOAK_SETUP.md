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

## Usage

```bash
cd extensions/m8flow-backend/bin
./start_keycloak.sh
```

## What the Script Does

1. **Validates environment**: Checks for required tools (docker, curl, jq) and realm export files
2. **Sets up Docker network**: Creates or verifies the `spiffworkflow` network exists
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

## Troubleshooting

- **Port conflicts**: Ensure ports 7002 and 7009 are not in use
- **Docker issues**: Verify Docker is running and you have permissions
- **Import failures**: Check that realm export JSON files are valid and accessible
- **Network issues**: The script creates the `spiffworkflow` network if it doesn't exist

## Stopping Keycloak

To stop the Keycloak container:

```bash
docker stop keycloak
```

To remove the container:

```bash
docker rm keycloak
```
