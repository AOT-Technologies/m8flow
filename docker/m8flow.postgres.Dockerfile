FROM postgres:15.19-alpine

# The Alpine variant already includes su-exec. Use it for the entrypoint's
# privilege drop instead of the bundled gosu binary, which carries vulnerable
# Go standard library components.
RUN rm /usr/local/bin/gosu /usr/local/bin/su-exec \
    && apk del su-exec \
    && apk add --no-cache su-exec \
    && sed -i 's#exec gosu postgres #exec /sbin/su-exec postgres #' /usr/local/bin/docker-entrypoint.sh \
    && test -x /sbin/su-exec \
    && ! grep -q 'gosu' /usr/local/bin/docker-entrypoint.sh
