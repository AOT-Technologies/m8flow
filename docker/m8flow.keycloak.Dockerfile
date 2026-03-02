# Build the realm-info-mapper provider JAR (Keycloak 26.0.7, Java 17)
FROM eclipse-temurin:17-jdk-alpine AS builder
RUN apk add --no-cache maven

WORKDIR /build
COPY keycloak-extensions/realm-info-mapper /build/realm-info-mapper

RUN mvn -f /build/realm-info-mapper/pom.xml clean package -q -DskipTests

# Keycloak image with the provider JAR in place (no host mount required)
FROM keycloak/keycloak:26.0.7
COPY --from=builder /build/realm-info-mapper/target/realm-info-mapper.jar /opt/keycloak/providers/realm-info-mapper.jar
USER root
RUN chown keycloak:keycloak /opt/keycloak/providers/realm-info-mapper.jar
USER keycloak
