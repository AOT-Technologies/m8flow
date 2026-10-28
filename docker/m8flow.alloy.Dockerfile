FROM grafana/alloy:v1.7.5

# The upstream image is Ubuntu 24.04. Apply the repository's current security
# updates for gnupg2 and OpenSSL without changing Alloy's entrypoint or user.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
