#!/bin/sh
set -e

echo "Waiting for MinIO..."
MC_USER="${MINIO_ROOT_USER:-minioadmin}"
MC_PASS="${MINIO_ROOT_PASSWORD:-minioadmin}"
until mc alias set local http://minio:9000 "$MC_USER" "$MC_PASS" >/dev/null 2>&1; do
  sleep 1
done
echo "MinIO is ready."

mc mb -p local/m8flow-process-models >/dev/null 2>&1 || true
echo "Bucket ensured: m8flow-process-models"
mc mb -p local/m8flow-templates >/dev/null 2>&1 || true
echo "Bucket ensured: m8flow-templates"
