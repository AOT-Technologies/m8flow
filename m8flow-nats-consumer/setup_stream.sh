#!/bin/sh
# Start NATS server with JetStream in background
nats-server -js &
pid=$!

# Wait for NATS to become ready
echo "Waiting for NATS to start..."
sleep 2

# Fetch the stream name from env or default
STREAM_NAME=${M8FLOW_NATS_STREAM_NAME:-M8FLOW_EVENTS}
SUBJECT=${M8FLOW_NATS_SUBJECT:-m8flow.events.>}

# Check if stream already exists, create if not
if ! nats stream info $STREAM_NAME > /dev/null 2>&1; then
echo "Creating stream $STREAM_NAME for defaults subjects..."
nats stream add $STREAM_NAME --subjects="$SUBJECT" --ack --max-msgs=-1 --max-bytes=-1 --max-age=1y --storage=file --retention=limits --max-msg-size=-1 --discard=old --replicas=1 --defaults
else
echo "Stream $STREAM_NAME already exists, skipping."
fi

# Bring NATS server back to foreground so the container stays running
wait $pid
