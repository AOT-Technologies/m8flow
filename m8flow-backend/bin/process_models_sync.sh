#!/bin/sh
set -e

echo "Syncing process models to MinIO..."
mkdir -p /cache
rclone copy minio:m8flow-process-models /cache --config /config/rclone/rclone.conf || true
rclone sync /cache minio:m8flow-process-models --config /config/rclone/rclone.conf
echo "Done."
