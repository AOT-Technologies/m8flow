FROM postgres:18.4

# Keep the Debian/glibc Postgres variant so existing Debian-initialized data
# volumes retain their collation provider. Replace the Go-based gosu binary
# with a small wrapper around util-linux setpriv, already present in the image.
# The upstream entrypoint continues to invoke "gosu postgres ...".
RUN rm /usr/local/bin/gosu \
  && printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'user="${1:?missing target user}"' \
      'shift' \
      'exec setpriv --reuid="$user" --regid="$user" --init-groups "$@"' \
      > /usr/local/bin/gosu \
  && chmod 0755 /usr/local/bin/gosu \
  && command -v setpriv \
  && gosu postgres true
