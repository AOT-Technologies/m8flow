FROM golang:1.27.3-bookworm AS grafana-builder

ARG GRAFANA_VERSION=v11.6.15

RUN apt-get update \
    && apt-get install -y --no-install-recommends git make \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "${GRAFANA_VERSION}" https://github.com/grafana/grafana.git /src

WORKDIR /src

# Patch the vulnerable dependencies identified in Grafana's bundled Go binaries.
# Normalize a stale 11.6.16 package version when present. If package.json is
# already at 11.6.15, sed is a no-op and the grep still verifies the version.
RUN sed -i '0,/"version": "11\.6\.16"/s//"version": "11.6.15"/' package.json \
    && grep -q '"version": "11.6.15"' package.json \
    && sed -i '/Pin OpenTelemetry log packages to v0.12.2 for compatibility with dagger v0.18.8/d' go.mod \
    && go mod edit \
      -dropreplace=go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc \
      -dropreplace=go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp \
      -dropreplace=go.opentelemetry.io/otel/exporters/stdout/stdoutlog \
      -dropreplace=go.opentelemetry.io/otel/log \
      -dropreplace=go.opentelemetry.io/otel/sdk/log \
    && go get \
      github.com/apache/thrift@v0.25.0 \
      github.com/getkin/kin-openapi@v0.149.0 \
      github.com/openfga/openfga@v1.18.1 \
      github.com/segmentio/encoding@v0.5.4 \
      google.golang.org/grpc@v1.83.2 \
      go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp@v1.43.0 \
      go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.45.0 \
      go.opentelemetry.io/otel/log@v0.21.0 \
      go.opentelemetry.io/otel/sdk/log@v0.21.0 \
      go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc@v0.21.0 \
      go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp@v0.21.0 \
      go.opentelemetry.io/otel/exporters/stdout/stdoutlog@v0.21.0

RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    make build-go-fast GO_BUILD_TAGS=oss WIRE_TAGS=oss

FROM grafana/grafana:13.2.4-ubuntu

USER root

# The upstream Ubuntu image is pinned to an older Jammy OpenSSL build.
RUN apt-get update \
    && apt-get install -y --only-upgrade openssl libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=472:0 --from=grafana-builder /src/bin/linux-amd64/grafana /usr/share/grafana/bin/grafana
COPY --chown=472:0 --from=grafana-builder /src/bin/linux-amd64/grafana-server /usr/share/grafana/bin/grafana-server
COPY --chown=472:0 --from=grafana-builder /src/bin/linux-amd64/grafana-cli /usr/share/grafana/bin/grafana-cli

USER grafana
