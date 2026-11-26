ARG CADDY_IMAGE=caddy:2.10.0-alpine
FROM ${CADDY_IMAGE}
# High internal ports require no file capability. Keep cap_drop/no-new-privileges.
RUN setcap -r /usr/bin/caddy \
    && mkdir -p /data /config \
    && chown -R 10001:10001 /data /config
COPY Caddyfile /etc/caddy/Caddyfile
USER 10001:10001
