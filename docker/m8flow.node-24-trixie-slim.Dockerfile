# Node 24 on Debian Trixie with Debian's fixed ACL, attr, and zlib releases.
FROM node:24.22.1-trixie-slim

# Keep the package source immutable. Update this timestamp with the package pins.
ARG DEBIAN_SNAPSHOT=20261027T000000Z

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && printf '%s\n' "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ sid main" \
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
