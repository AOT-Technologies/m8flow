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
FROM quay.io/keycloak/keycloak:26.0.7
COPY --from=builder /build/realm-info-mapper/target/realm-info-mapper.jar /opt/keycloak/providers/realm-info-mapper.jar
USER root
RUN chown keycloak:keycloak /opt/keycloak/providers/realm-info-mapper.jar
RUN mkdir -p /opt/keycloak/data/import
COPY extensions/m8flow-backend/keycloak/realm_exports/tenant-realm-export.json /opt/keycloak/data/import/tenant-a-realm.json
COPY extensions/m8flow-backend/keycloak/realm_exports/identity-realm-export.json /opt/keycloak/data/import/identity-realm.json
RUN chown -R keycloak:keycloak /opt/keycloak/data/import
USER keycloak

# Health, features, log level (align with start_keycloak.sh).
ENV KC_HEALTH_ENABLED=true
ENV JAVA_OPTS_APPEND="-Dkeycloak.profile.feature.token_exchange=enabled -Dkeycloak.profile.feature.admin_fine_grained_authz=enabled -D--spi-theme-static-max-age=-1 -D--spi-theme-cache-themes=false -D--spi-theme-cache-templates=false"
ENV KEYCLOAK_LOGLEVEL=ALL
ENV ROOT_LOGLEVEL=ALL
