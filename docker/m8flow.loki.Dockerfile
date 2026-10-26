FROM golang:1.27.3 AS builder

ARG IMAGE_TAG=3.7.8

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src/loki
RUN git clone --depth 1 --branch v3.7.8 https://github.com/grafana/loki.git . \
    && go get \
        github.com/apache/thrift@v0.25.0 \
        github.com/aws/aws-sdk-go-v2/service/s3@v1.114.2 \
        github.com/go-openapi/swag@v0.29.2 \
        go.opentelemetry.io/otel/sdk/log@v0.21.0 \
    && make clean \
    && make BUILD_IN_CONTAINER=false IMAGE_TAG=${IMAGE_TAG} loki

FROM grafana/loki:3.7.8

COPY --from=builder /src/loki/cmd/loki/loki /usr/bin/loki
