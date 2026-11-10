# Build realm-info-mapper provider JAR (Keycloak 26; JDK 25 LTS compiling to Java 17 bytecode).
FROM eclipse-temurin:25-jdk AS builder
ARG MAVEN_VERSION=3.9.9
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && curl --fail --show-error --location --retry 5 --retry-all-errors --retry-delay 2 \
    --output /tmp/apache-maven.tar.gz \
    https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz \
  && tar -tzf /tmp/apache-maven.tar.gz >/dev/null \
  && tar -xzf /tmp/apache-maven.tar.gz -C /opt \
  && rm /tmp/apache-maven.tar.gz \
  && ln -s /opt/apache-maven-${MAVEN_VERSION} /opt/maven \
  && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/maven/bin:$PATH"

WORKDIR /build
COPY keycloak-extensions/realm-info-mapper /build/realm-info-mapper

RUN mvn -f /build/realm-info-mapper/pom.xml clean package -q -DskipTests

# jq's official image is built as a static binary, so it can be copied into
# Keycloak's UBI Micro runtime without adding a package manager or shared libs.
FROM ghcr.io/jqlang/jq:1.8.2 AS jq

FROM quay.io/keycloak/keycloak:26.8.2-1 AS keycloak

# Red Hat ships no fixed sqlite-libs for UBI 9 (CVE-2026-119374, CVE-2026-119379).
# Only nss-softokn links it, and the JDK loads NSS only on a host in FIPS mode,
# which this image does not support. UBI Micro has no rpm, so drop the package
# from a copy of its rpm database here; the runtime stage deletes the files.
# The build fails if any other installed package depends on sqlite-libs.
FROM registry.access.redhat.com/ubi9/ubi-minimal:9.8 AS rpmdb
COPY --from=keycloak /var/lib/rpm /mnt/rootfs/var/lib/rpm
RUN out="$(rpm --root /mnt/rootfs --erase --test sqlite-libs 2>&1)"; \
    if printf '%s\n' "$out" | grep 'is needed by' | grep -qv 'by (installed) nss-softokn-'; then \
      printf '%s\n' "$out" 'sqlite-libs has users besides nss-softokn; keep it.' >&2; exit 1; \
    fi; \
    rpm --root /mnt/rootfs --erase --nodeps --justdb --noscripts sqlite-libs

# Keycloak with provider JAR (no host mount).
FROM keycloak
COPY --from=builder /build/realm-info-mapper/target/realm-info-mapper.jar /opt/keycloak/providers/realm-info-mapper.jar
COPY --from=jq /jq /usr/local/bin/jq
USER root
# Keycloak 26 uses UBI Micro which ships without any package manager.
# OS-level security patches should be obtained by pulling the latest Keycloak image.
COPY --from=rpmdb /mnt/rootfs/var/lib/rpm /var/lib/rpm
# Fail the build if any file outside NSS (libsoftokn3 and its unsupported test
# tools) still references libsqlite3.so.0, since that file would break at load.
RUN rm -rf /usr/lib64/libsqlite3.so* /usr/share/doc/sqlite-libs \
  && if grep -rlF libsqlite3.so.0 /usr /opt | grep -v -e '^/usr/lib64/libsoftokn3\.so$' -e '^/usr/lib64/nss/'; then \
       echo 'These files link libsqlite3, which is removed here; keep sqlite-libs.' >&2; exit 1; \
     fi
RUN mkdir -p /opt/keycloak/data/import
RUN mkdir -p /opt/keycloak/themes
COPY m8flow-backend/keycloak/realm_exports/m8flow-tenant-template.json /opt/keycloak/data/import/m8flow-tenant-template.json
COPY m8flow-backend/keycloak/themes/m8flow /opt/keycloak/themes/m8flow
RUN chown -R keycloak:keycloak /opt/keycloak/data/import
COPY docker/keycloak-init-realms.sh /opt/keycloak/bin/keycloak-init-realms.sh
COPY docker/keycloak-entrypoint.sh /opt/keycloak/bin/keycloak-entrypoint.sh
COPY docker/keycloak-client-secret.sh /opt/keycloak/bin/keycloak-client-secret.sh
RUN chown keycloak:keycloak /opt/keycloak/providers/realm-info-mapper.jar \
  && chmod 0755 /usr/local/bin/jq \
  && chown -R keycloak:keycloak /opt/keycloak/data/import \
  && chown -R keycloak:keycloak /opt/keycloak/themes/m8flow \
  && chmod +x /opt/keycloak/bin/keycloak-init-realms.sh /opt/keycloak/bin/keycloak-entrypoint.sh /opt/keycloak/bin/keycloak-client-secret.sh \
  && chown keycloak:keycloak /opt/keycloak/bin/keycloak-init-realms.sh /opt/keycloak/bin/keycloak-entrypoint.sh /opt/keycloak/bin/keycloak-client-secret.sh
USER keycloak

ENTRYPOINT ["/opt/keycloak/bin/keycloak-entrypoint.sh"]

# Bootstrap admin credentials come from KC_BOOTSTRAP_ADMIN_* at runtime, not from
# ENV here, so no password is baked into the image config. keycloak-entrypoint.sh
# refuses to start without KC_BOOTSTRAP_ADMIN_PASSWORD.
# Health and features (align with start_keycloak.sh).
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_FEATURES="organization,token-exchange,admin-fine-grained-authz"
