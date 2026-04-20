#!/bin/sh
set -eu

SRC="${SRC:-/host_attachments}"
DST="${1:-/data/slack_attachments}"

echo "Syncing Slack attachments..."
echo "  from: $SRC"
echo "  to:   $DST"

mkdir -p "$DST"

cp -f "$SRC"/* "$DST"/ 2>/dev/null || true

echo "Done."
