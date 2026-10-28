FROM golang:1.27.3-alpine3.24 AS builder

ARG CGO_ENABLED=0
ENV CGO_ENABLED=${CGO_ENABLED}

WORKDIR /go/src/github.com/rclone/rclone
RUN apk add --no-cache bash gawk git make \
    && git clone --depth 1 --branch v1.75.2 https://github.com/rclone/rclone.git . \
    && make \
    && ./rclone version

FROM rclone/rclone:1.75.2

RUN apk add --no-cache --upgrade musl-utils zlib

COPY --from=builder /go/src/github.com/rclone/rclone/rclone /usr/local/bin/rclone
