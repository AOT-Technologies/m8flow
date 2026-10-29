FROM golang:1.27.3-alpine3.23 AS builder

RUN apk --no-cache add bash build-base cmake device-mapper findutils git \
    libc6-compat linux-headers ndctl-dev pkgconfig python3 thin-provisioning-tools wget zfs \
    && echo 'hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4' >> /etc/nsswitch.conf \
    && rm -rf /var/cache/apk/*

RUN wget https://sourceforge.net/projects/perfmon2/files/libpfm4/libpfm-4.11.0.tar.gz \
    && echo "112bced9a67d565ff0ce6c2bb90452516d1183e5  libpfm-4.11.0.tar.gz" | sha1sum -c \
    && tar -xzf libpfm-4.11.0.tar.gz \
    && rm libpfm-4.11.0.tar.gz \
    && DBG="-g -Wall -Wno-error=cpp" make -e -C libpfm-4.11.0 \
    && make install -C libpfm-4.11.0

WORKDIR /go/src/github.com/google/cadvisor
RUN git clone --depth 1 --branch v0.60.6 https://github.com/google/cadvisor.git . \
    && cd cmd \
    && go get google.golang.org/grpc@v1.83.2 \
    && cd .. \
    && GO_FLAGS="-tags=libpfm,netgo" VERSION=0.60.6 ./build/build.sh

FROM ghcr.io/google/cadvisor:v0.60.6

RUN apk add --no-cache --upgrade zlib musl-utils

COPY --from=builder /go/src/github.com/google/cadvisor/_output/cadvisor /usr/bin/cadvisor
