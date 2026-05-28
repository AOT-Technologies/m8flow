# Keycloak Mappers

This JAR contains M8Flow-specific Keycloak OIDC protocol mappers.

## Included mappers

- `oidc-realm-info-mapper`
  Adds `m8flow_tenant_name` and `m8flow_tenant_id` to tokens.
- `oidc-normalized-group-membership-mapper`
  Emits Keycloak group paths without leading slash characters.

Examples for normalized groups:

- `/Manager` becomes `Manager`
- `/Business/Finance` becomes `Business/Finance`

**Compatibility**: Keycloak 26.6.1, Java 17.

## Build

From `keycloak-extensions/realm-info-mapper/`:

```bash
./build.sh
```

Or:

```bash
mvn clean package
```

Build output:

- `target/realm-info-mapper.jar`

## Deployment

The Docker setup loads the built JAR into Keycloak at:

- `/opt/keycloak/providers/realm-info-mapper.jar`

After rebuilding the JAR, restart or rebuild the Keycloak container so the provider is reloaded.

## Configuring in Keycloak

1. Open the realm in the Keycloak admin UI.
2. Open the target client or client scope.
3. Add a mapper by configuration.
4. Choose either `Realm Info Mapper` or `Normalized Group Membership Mapper`.
5. Save.
