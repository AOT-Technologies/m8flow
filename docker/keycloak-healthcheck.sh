#!/usr/bin/env bash
# Lightweight Keycloak readiness probe used by the compose healthcheck.
#
# Why this exists:
# The previous healthcheck ran `kcadm.sh config credentials ...` on every
# interval. kcadm is a full Java CLI, so each check cold-starts a JVM. During
# Keycloak's first boot (server start + Quarkus augmentation + realm import) a
# JVM spawned every 10s competes for CPU on the same container that is trying to
# finish booting. On a resource-starved host -- exactly the state during a
# low-bandwidth `docker compose up`, when Docker Desktop is still pulling the
# other base images and the engine VM is saturated -- this self-inflicted load
# can push Keycloak's first boot past the health window, so Compose gives up with
# "dependency keycloak failed to start" even though nothing is actually wrong.
#
# This probe instead hits Keycloak's built-in management health endpoint
# (enabled via KC_HEALTH_ENABLED=true) over a raw TCP socket. No JVM, no curl
# (the UBI-micro base image ships neither curl nor wget), negligible CPU.
#
# Exit 0 only when /health/ready returns HTTP 200 (Keycloak fully started and
# ready to serve); non-zero otherwise.
port="${KC_HTTP_MANAGEMENT_PORT:-9000}"
exec 3<>"/dev/tcp/127.0.0.1/${port}" || exit 1
printf 'GET /health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3 || exit 1
IFS= read -r status_line <&3 || exit 1
case "${status_line}" in
  *" 200 "*) exit 0 ;;
  *) exit 1 ;;
esac
