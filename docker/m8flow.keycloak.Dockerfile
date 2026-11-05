# Build realm-info-mapper provider JAR (Keycloak 26; JDK 25 LTS compiling to Java 17 bytecode).
# Official Maven image, so the build no longer streams Maven from archive.apache.org.
FROM maven:3.9.16-eclipse-temurin-25 AS builder

WORKDIR /build
COPY keycloak-extensions/realm-info-mapper /build/realm-info-mapper

RUN mvn -f /build/realm-info-mapper/pom.xml clean package -q -DskipTests

# Keycloak with provider JAR (no host mount).
FROM quay.io/keycloak/keycloak:26.8.1-1
COPY --from=builder /build/realm-info-mapper/target/realm-info-mapper.jar /opt/keycloak/providers/realm-info-mapper.jar
USER root
# Keycloak 26 uses UBI Micro which ships without any package manager.
# OS-level security patches should be obtained by pulling the latest Keycloak image.
RUN mkdir -p /opt/keycloak/data/import
RUN mkdir -p /opt/keycloak/themes
COPY m8flow-backend/keycloak/realm_exports/m8flow-tenant-template.json /opt/keycloak/data/import/m8flow-tenant-template.json
COPY m8flow-backend/keycloak/themes/m8flow /opt/keycloak/themes/m8flow
RUN chown -R keycloak:keycloak /opt/keycloak/data/import
COPY docker/keycloak-init-realms.sh /opt/keycloak/bin/keycloak-init-realms.sh
COPY docker/keycloak-entrypoint.sh /opt/keycloak/bin/keycloak-entrypoint.sh
RUN chown keycloak:keycloak /opt/keycloak/providers/realm-info-mapper.jar \
  && chown -R keycloak:keycloak /opt/keycloak/data/import \
  && chown -R keycloak:keycloak /opt/keycloak/themes/m8flow \
  && chmod +x /opt/keycloak/bin/keycloak-init-realms.sh /opt/keycloak/bin/keycloak-entrypoint.sh \
  && chown keycloak:keycloak /opt/keycloak/bin/keycloak-init-realms.sh /opt/keycloak/bin/keycloak-entrypoint.sh
USER keycloak

ENTRYPOINT ["/opt/keycloak/bin/keycloak-entrypoint.sh"]

# Bootstrap admin credentials come from KC_BOOTSTRAP_ADMIN_* at runtime, not from
# ENV here, so no password is baked into the image config. keycloak-entrypoint.sh
# refuses to start without KC_BOOTSTRAP_ADMIN_PASSWORD.
# Health and features (align with start_keycloak.sh).
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_FEATURES="organization,token-exchange,admin-fine-grained-authz"
