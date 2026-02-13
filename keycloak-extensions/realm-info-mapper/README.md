# Realm Info Mapper

A Keycloak OIDC protocol mapper that adds the current realm’s name and ID to access tokens and ID tokens.

## What it does

- **Type**: Keycloak OIDC protocol mapper (SPI provider).
- **Provider ID**: `oidc-realm-info-mapper`.
- **Display name**: “Realm Info Mapper”.

When attached to a client, it adds two claims to the token:

| Claim                | Description                                    |
|----------------------|------------------------------------------------|
| `m8flow_tenant_name` | Name of the realm that issued the token       |
| `m8flow_tenant_id`   | ID of the realm that issued the token (tenant)|

The mapper reads the realm from the current Keycloak session, so the values are always for the realm in which the user authenticated. Applications can use these claims for multi-realm or tenant-aware logic without extra lookups.

**Compatibility**: Keycloak 26.0.7, Java 17.

## How to build

### Prerequisites

- **Java 17** (or compatible JDK)
- **Maven** (e.g. `mvn` on `PATH`)

### Build steps

From this directory (`keycloak-extensions/realm-info-mapper/`):

**Option 1 – script (recommended)**

```bash
./build.sh
```

**Option 2 – Maven**

```bash
mvn clean package
```

### Build output

- **Artifact**: `target/realm-info-mapper.jar`

If the build succeeds, the JAR is ready to be used as a Keycloak provider.

## Deployment

The JAR is loaded by Keycloak when placed in its providers directory. In this project, the Docker setup does that by mounting the built JAR:

- **Path in container**: `/opt/keycloak/providers/realm-info-mapper.jar`
- **Compose**: `docker/m8flow-docker-compose.yml` mounts `keycloak-extensions/realm-info-mapper/target/realm-info-mapper.jar` into that location.

So:

1. Build the mapper (see above).
2. Start (or restart) the stack that uses `m8flow-docker-compose.yml` so Keycloak picks up the JAR.

## Configuring in Keycloak

1. In the Keycloak admin UI, open the realm and go to **Clients** → select the client (e.g. the one used by m8flow).
2. Open the **Client scopes** tab and either edit the client’s scope or the scope used by that client.
3. Add a mapper: **Add mapper** → **By configuration** → choose **Realm Info Mapper**.
4. Save.

After that, tokens issued for that client will include `m8flow_tenant_name` and `m8flow_tenant_id` in the payload (typically under `otherClaims` or the root, depending on token type and client settings).
