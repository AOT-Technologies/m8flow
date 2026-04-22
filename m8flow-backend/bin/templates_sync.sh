#!/bin/sh
set -e

echo "Syncing templates to MinIO..."
mkdir -p /cache
# Optional one-time seed from S3 (non-destructive)
rclone copy minio:m8flow-templates /cache --config /config/rclone/rclone.conf  || true
rclone sync /cache minio:m8flow-templates --config /config/rclone/rclone.conf
echo "Done."
