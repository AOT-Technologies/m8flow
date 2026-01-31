#!/bin/sh
set -e

mkdir -p /cache

# Optional one-time seed from S3 (non-destructive)
rclone copy minio:m8flow-templates /cache --config /config/rclone/rclone.conf

echo "Templates sync: Push-only loop (local -> S3)..."
while true; do
  rclone sync /cache minio:m8flow-templates --config /config/rclone/rclone.conf
  sleep 3
done
