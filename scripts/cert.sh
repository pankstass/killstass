#!/bin/sh
# KILLSTASS v1.10: Let's Encrypt certificate for KS_DOMAIN by the DNS-01 challenge (lego in a container).
# The CA checks a TXT record that lego creates through the DNS provider's API: no inbound connection,
# the server stays closed to the internet. Needs outbound HTTPS (Let's Encrypt, the provider's API).
#   ./scripts/cert.sh issue     the first certificate, then KS_TLS_MODE=files and a proxy restart
#   ./scripts/cert.sh renew     renews when a third of the lifetime is left (killstass-cert.timer), restarts proxy
#   ./scripts/cert.sh status    the stored certificate
# .env: KS_DOMAIN (./scripts/domain.sh set), ACME_EMAIL, ACME_DNS_PROVIDER — the lego code of the DNS hosting:
#   regru, nicru, beget, timewebcloud, selectelv2, yandex360, yandexcloud, cloudflare, … Optional: ACME_SERVER
#   (https://acme-staging-v02.api.letsencrypt.org/directory for a trial run), LEGO_IMAGE.
# local/acme.env (root, 0600): the provider's API credentials, one KEY=value per line without quotes,
#   e.g. REGRU_USERNAME=… and REGRU_PASSWORD=… (list: docker run --rm goacme/lego:v4.29.0 dnshelp -c regru).
# Files: local/acme/ (account and certificates, owned by uid 10001 like the proxy); the proxy reads
# local/acme/certificates/DOMAIN.crt|.key as /certs.
set -eu
cd "$(dirname "$0")/.."
. ./scripts/lib.sh
need_root
domain=$(envget KS_DOMAIN)
email=$(envget ACME_EMAIL)
provider=$(envget ACME_DNS_PROVIDER)
server=$(envget ACME_SERVER)
image=$(envget LEGO_IMAGE)
image=${image:-goacme/lego:v4.29.0}
crt="local/acme/certificates/$domain.crt"
key="local/acme/certificates/$domain.key"

prepare() {
  [ -n "$domain" ] && [ "$domain" != killstass.invalid ] || die 'set the domain first: ./scripts/domain.sh set killstass.su'
  valid_domain "$domain" || die "KS_DOMAIN=$domain is not a domain name"
  case "$email" in *@*.*) ;; *) die 'ACME_EMAIL in .env: the e-mail of the Let'"'"'s Encrypt account' ;; esac
  printf '%s\n' "$provider" | grep -Eq '^[a-z0-9]+$' || die 'ACME_DNS_PROVIDER in .env: the lego code of the DNS provider (e.g. regru)'
  [ -s local/acme.env ] || die 'local/acme.env with the DNS provider API credentials is missing (see the header of this script)'
  chmod 600 local/acme.env
  mkdir -p local/acme/certificates
  chown -R 10001:10001 local/acme
  chmod 700 local/acme
}
lego() {
  # shellcheck disable=SC2086
  docker run --rm --user 10001:10001 --read-only --tmpfs /tmp:size=8m --cap-drop ALL \
    --security-opt no-new-privileges:true --env-file local/acme.env -v "$(pwd)/local/acme:/acme" "$image" \
    --accept-tos --email "$email" --dns "$provider" --dns.resolvers 1.1.1.1:53 --dns.resolvers 8.8.8.8:53 \
    ${server:+--server "$server"} --domains "$domain" --path /acme "$@"
}
fingerprint() { [ -s "$crt" ] && sha256sum "$crt" | cut -c1-64 || echo none; }
show() {
  if command -v openssl >/dev/null 2>&1; then
    openssl x509 -in "$crt" -noout -subject -issuer -enddate
  else
    lego list
  fi
}

case "${1:-status}" in
  issue)
    prepare
    lego run
    [ -s "$crt" ] && [ -s "$key" ] || die "lego finished without $crt"
    envset KS_TLS_MODE files
    docker compose up -d --wait proxy
    show
    say "https://$domain now uses the Let's Encrypt certificate. Automatic renewal:"
    say '  cp systemd/killstass-cert.* /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now killstass-cert.timer'
    ;;
  renew)
    prepare
    [ -s "$crt" ] || die 'no certificate yet: ./scripts/cert.sh issue'
    before=$(fingerprint)
    lego renew --dynamic
    if [ "$(fingerprint)" != "$before" ]; then
      if [ "$(envget KS_TLS_MODE)" = files ]; then docker compose restart proxy; fi
      say "renewed: $(show | tr '\n' ' ')"
    else
      say 'not due for renewal yet'
    fi
    ;;
  status)
    echo "KS_DOMAIN=${domain:-—} KS_TLS_MODE=$(envget KS_TLS_MODE) ACME_DNS_PROVIDER=${provider:-—}"
    if [ -n "$domain" ] && [ -s "$crt" ]; then show; else echo 'no Let'"'"'s Encrypt certificate stored'; fi
    ;;
  *) echo 'usage: cert.sh issue | renew | status' >&2; exit 2 ;;
esac
