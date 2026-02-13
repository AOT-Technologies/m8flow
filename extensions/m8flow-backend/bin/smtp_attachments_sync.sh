#!/bin/sh
set -eu

SRC="/host_attachments"
DST="/app/email_attachments"

echo "Syncing SMTP attachments..."
echo "  from: $SRC"
echo "  to:   $DST"

mkdir -p "$DST"

# Copy files (non-recursive). Change to cp -R if you want subfolders too.
# Using -f to overwrite, preserving the volume as the “published” store.
cp -f "$SRC"/* "$DST"/ 2>/dev/null || true

echo "Done."
