#!/bin/sh
# KILLSTASS v1.10: the club's domain (e.g. killstass.su) next to the LAN address.
#   ./scripts/domain.sh set killstass.su   KS_DOMAIN and APP_ORIGIN in .env, restart api and proxy
#   ./scripts/domain.sh unset              back to the IP address only
#   ./scripts/domain.sh status             settings, DNS answer, served certificate
# DNS: an A record «killstass.su → 192.168.1.250» (the LAN address). The site stays closed to the internet:
# only the LAN (and Tailscale, scripts/tailscale.sh) can connect. Until ./scripts/cert.sh issue the domain
# uses the local CA, like the IP address; after it — a Let's Encrypt certificate (DNS-01, no open ports).
set -eu
cd "$(dirname "$0")/.."
. ./scripts/lib.sh
need_root
host=$(envget APP_HOST)
host=${host:-192.168.1.250}

check_dns() {
  answer=$(getent ahostsv4 "$1" 2>/dev/null | awk '{print $1; exit}' || true)
  if [ -z "$answer" ]; then
    say "DNS: $1 does not resolve yet. Create the A record $1 -> $host at the DNS provider."
  elif [ "$answer" != "$host" ]; then
    say "DNS: $1 -> $answer, expected $host. Fix the A record (or wait for the old TTL)."
  else
    say "DNS: $1 -> $host (ok)."
  fi
  say "If phones on Wi-Fi cannot open https://$1 although DNS is right, the router may drop public answers"
  say "with private addresses (DNS rebinding protection): allow $1 there or add a local DNS record."
}

case "${1:-status}" in
  set)
    d=$(printf '%s' "${2:-}" | tr 'A-Z' 'a-z')
    valid_domain "$d" || die 'usage: domain.sh set DOMAIN (for example killstass.su)'
    envset KS_DOMAIN "$d"
    envset APP_ORIGIN "https://$host,https://$d"
    if [ -s "local/acme/certificates/$d.crt" ] && [ -s "local/acme/certificates/$d.key" ]; then
      envset KS_TLS_MODE files
    else
      envset KS_TLS_MODE internal
    fi
    docker compose up -d --wait api proxy
    say "https://$d is served with the $(envget KS_TLS_MODE) certificate; https://$host keeps working."
    [ "$(envget KS_TLS_MODE)" = files ] || say "Next: a trusted certificate — ./scripts/cert.sh issue (see its header)."
    check_dns "$d"
    ;;
  unset)
    envdel KS_DOMAIN
    envset KS_TLS_MODE internal
    envset APP_ORIGIN "https://$host"
    docker compose up -d --wait api proxy
    say "domain removed; the site is https://$host only."
    ;;
  status)
    d=$(envget KS_DOMAIN)
    echo "APP_HOST=$host"
    echo "KS_DOMAIN=${d:-—}"
    echo "KS_TLS_MODE=$(envget KS_TLS_MODE)"
    echo "APP_ORIGIN=$(envget APP_ORIGIN)"
    echo "KS_ALLOW_NETS=$(allowed_nets)"
    if [ -n "$d" ]; then
      check_dns "$d"
      if command -v openssl >/dev/null 2>&1; then
        bind=$(envget BIND_IP)
        printf '' | openssl s_client -connect "${bind:-$host}:443" -servername "$d" 2>/dev/null |
          openssl x509 -noout -subject -issuer -enddate 2>/dev/null || say "no TLS answer for $d on ${bind:-$host}:443"
      fi
    fi
    ;;
  *) echo 'usage: domain.sh set DOMAIN | unset | status' >&2; exit 2 ;;
esac
