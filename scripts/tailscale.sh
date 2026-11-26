#!/bin/sh
# KILLSTASS v1.10: access from outside the club through Tailscale (WireGuard) without opening the server to
# the internet. The `tailscale` service (COMPOSE_PROFILES=tailscale, host network) announces the route
# TS_ROUTES=192.168.1.250/32 to your tailnet: a phone with the Tailscale app opens the same address
# (https://killstass.su or https://192.168.1.250) from anywhere. Tailnet clients (100.64.0.0/10) are added
# to KS_ALLOW_NETS for the proxy and the firewall.
#   ./scripts/tailscale.sh enable [AUTHKEY]   start (an auth key «tskey-auth-…» only for the first start)
#   ./scripts/tailscale.sh disable            stop; LAN access stays as it was
#   ./scripts/tailscale.sh status
# After the first start approve the route 192.168.1.250/32 of the machine «killstass» in the admin console
# (Machines → killstass → Edit route settings) unless autoApprovers do it. Linux clients: --accept-routes.
set -eu
cd "$(dirname "$0")/.."
. ./scripts/lib.sh
need_root
TSNET=100.64.0.0/10
ts() { docker compose exec -T tailscale tailscale "$@"; }

case "${1:-status}" in
  enable)
    key=${2:-}
    if [ -n "$key" ]; then
      case "$key" in tskey-*) ;; *) die 'an auth key starts with tskey- (admin console → Settings → Keys)' ;; esac
      envset TS_AUTHKEY "$key"
    elif [ ! -s local/tailscale/tailscaled.state ] && [ -z "$(envget TS_AUTHKEY)" ]; then
      die 'first start: ./scripts/tailscale.sh enable tskey-auth-… (admin console → Settings → Keys)'
    fi
    modprobe tun 2>/dev/null || true
    [ -c /dev/net/tun ] || die '/dev/net/tun is missing (kernel module tun)'
    mkdir -p local/tailscale
    chmod 700 local/tailscale
    profile_on tailscale
    nets_add "$TSNET"
    ./scripts/firewall.sh
    docker compose up -d --wait proxy
    docker compose up -d tailscale
    state=''
    for _ in $(seq 1 30); do
      state=$(ts status --json 2>/dev/null | sed -n 's/.*"BackendState": *"\([A-Za-z]*\)".*/\1/p' | head -n 1 || true)
      [ "$state" = Running ] && break
      sleep 2
    done
    [ "$state" = Running ] || die "tailscale is «${state:-not started}»: docker compose logs --tail 30 tailscale"
    # The node identity is in local/tailscale now; the one-time key is not needed any more.
    envdel TS_AUTHKEY
    say "tailscale is up: $(ts ip -4 2>/dev/null | head -n 1) ($(envget TS_HOSTNAME || true))"
    say 'Approve the route 192.168.1.250/32 in the admin console if it is not approved yet.'
    ;;
  disable)
    if profile_has tailscale; then
      docker compose stop tailscale || true
      docker compose rm -f tailscale || true
    fi
    profile_off tailscale
    nets_del "$TSNET"
    ./scripts/firewall.sh
    docker compose up -d --wait proxy
    say 'tailscale stopped (its identity stays in local/tailscale; remove the machine in the admin console if needed).'
    ;;
  status)
    echo "COMPOSE_PROFILES=$(envget COMPOSE_PROFILES) KS_ALLOW_NETS=$(allowed_nets)"
    if profile_has tailscale; then ts status || true; else echo 'tailscale is disabled'; fi
    ;;
  *) echo 'usage: tailscale.sh enable [AUTHKEY] | disable | status' >&2; exit 2 ;;
esac
