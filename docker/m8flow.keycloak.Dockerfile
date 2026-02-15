# Build realm-info-mapper provider JAR (Keycloak 26, Java 17).
FROM eclipse-temurin:17-jdk-alpine AS builder
RUN apk add --no-cache maven

WORKDIR /build
COPY keycloak-extensions/realm-info-mapper /build/realm-info-mapper

RUN mvn -f /build/realm-info-mapper/pom.xml clean package -q -DskipTests

# Keycloak with provider JAR (no host mount).
FROM quay.io/keycloak/keycloak:26.0.7
COPY --from=builder /build/realm-info-mapper/target/realm-info-mapper.jar /opt/keycloak/providers/realm-info-mapper.jar
USER root
RUN chown keycloak:keycloak /opt/keycloak/providers/realm-info-mapper.jar
USER keycloak

# Health, features, log level (align with start_keycloak.sh).
ENV KC_HEALTH_ENABLED=true
ENV JAVA_OPTS_APPEND="-Dkeycloak.profile.feature.token_exchange=enabled -Dkeycloak.profile.feature.admin_fine_grained_authz=enabled -D--spi-theme-static-max-age=-1 -D--spi-theme-cache-themes=false -D--spi-theme-cache-templates=false"
ENV KEYCLOAK_LOGLEVEL=ALL
ENV ROOT_LOGLEVEL=ALL
