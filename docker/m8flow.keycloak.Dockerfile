# Build realm-info-mapper provider JAR (Keycloak 26, Java 17).
FROM eclipse-temurin:17-jdk AS builder
ARG MAVEN_VERSION=3.9.9
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && curl -sL https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz | tar xz -C /opt \
  && ln -s /opt/apache-maven-${MAVEN_VERSION} /opt/maven \
  && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/maven/bin:$PATH"

WORKDIR /build
COPY keycloak-extensions/realm-info-mapper /build/realm-info-mapper

RUN mvn -f /build/realm-info-mapper/pom.xml clean package -q -DskipTests

# Keycloak with provider JAR (no host mount).
FROM quay.io/keycloak/keycloak:26.6.1
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

# Bootstrap admin (Keycloak 26+); avoids "Local access required" when using a proxy.
ENV KC_BOOTSTRAP_ADMIN_USERNAME=admin
ENV KC_BOOTSTRAP_ADMIN_PASSWORD=admin
# Health and features (align with start_keycloak.sh).
ENV KC_HEALTH_ENABLED=true
ENV JAVA_OPTS_APPEND="-Dkeycloak.profile.feature.token_exchange=enabled"
