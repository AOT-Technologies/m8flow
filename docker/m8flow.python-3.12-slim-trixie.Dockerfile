# Python 3.12 on Debian Trixie, with the currently fixed Debian package
# releases for ACL, attr, and zlib. Trixie has not backported these fixes yet.
FROM python:3.12-slim-trixie

# Keep the package source immutable. Update this timestamp with the package pins.
ARG DEBIAN_SNAPSHOT=20261027T000000Z

RUN printf '%s\n' "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ sid main" \
      > /etc/apt/sources.list.d/sid.list \
  && printf '%s\n' 'Package: libacl1 libattr1 zlib1g' 'Pin: release a=unstable' 'Pin-Priority: 1001' '' 'Package: *' 'Pin: release a=unstable' 'Pin-Priority: -1' \
      > /etc/apt/preferences.d/sid \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
      libacl1=2.4.0-1 \
      libattr1=1:2.6.0-1 \
      zlib1g=1:1.3.dfsg+really1.3.2-4 \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /etc/apt/sources.list.d/sid.list /etc/apt/preferences.d/sid
