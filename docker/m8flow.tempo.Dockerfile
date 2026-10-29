FROM golang:1.26.10 AS builder

ARG TARGETARCH
ARG TEMPO_VERSION=2.10.10

RUN apt-get update \
    && apt-get install -y --no-install-recommends git make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src/tempo
RUN git clone --depth 1 --branch "v${TEMPO_VERSION}" https://github.com/grafana/tempo.git . \
    && go get \
        github.com/apache/thrift@v0.25.0 \
        github.com/go-openapi/swag@v0.29.2 \
    && go mod vendor \
    && GOOS=linux GOARCH=${TARGETARCH} make tempo

FROM grafana/tempo:3.1.1

ARG TARGETARCH

COPY --from=builder /src/tempo/bin/linux/tempo-${TARGETARCH} /tempo
