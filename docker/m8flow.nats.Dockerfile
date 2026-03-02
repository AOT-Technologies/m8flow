FROM nats:2.10-alpine

# Install NATS CLI so we can configuring streams
RUN apk add --no-cache curl unzip \
    && curl -sSL https://github.com/nats-io/natscli/releases/download/v0.1.4/nats-0.1.4-linux-amd64.zip -o nats.zip \
    && unzip nats.zip \
    && mv nats-0.1.4-linux-amd64/nats /usr/local/bin/nats \
    && rm -rf nats-0.1.4-linux-amd64 nats.zip \
    && apk del curl unzip

# Create initialization script
COPY m8flow-nats-consumer/setup_stream.sh /setup_stream.sh
RUN chmod +x /setup_stream.sh

# Start using the initialization script
ENTRYPOINT ["/setup_stream.sh"]
