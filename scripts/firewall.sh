#!/bin/sh
# KILLSTASS LAN guard: only the networks of KS_ALLOW_NETS (.env; default 192.168.1.0/24, tailscale.sh adds
# 100.64.0.0/10) reach BIND_IP:80/443. Own chain/table only: Docker, fail2ban, SSH and other rules stay untouched.
set -eu
cd "$(dirname "$0")/.."
. ./scripts/lib.sh
need_root
IP=${BIND_IP:-$(envget BIND_IP)}
IP=${IP:-192.168.1.250}
NETS=${KS_ALLOW_NETS:-$(allowed_nets)}
printf '%s\n' "$IP" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || die "BIND_IP '$IP' is not an IPv4 address"
for n in $NETS; do
  valid_cidr "$n" || die "KS_ALLOW_NETS: '$n' is not an IPv4 network such as 192.168.1.0/24"
done
[ -n "$NETS" ] || die 'KS_ALLOW_NETS is empty'
# Prefer DOCKER-USER when Docker uses iptables (including iptables-nft compatibility).
if command -v iptables >/dev/null && iptables -w -nL DOCKER-USER >/dev/null 2>&1; then
  iptables -w -N KILLSTASS-LAN 2>/dev/null || true
  iptables -w -F KILLSTASS-LAN
  for n in $NETS; do
    iptables -w -A KILLSTASS-LAN -s "$n" -j RETURN
  done
  # The original destination (before Docker DNAT) identifies the published ports of the proxy.
  for port in 80 443; do
    iptables -w -A KILLSTASS-LAN -p tcp -m conntrack --ctdir ORIGINAL --ctorigdst "$IP" --ctorigdstport "$port" -j DROP
  done
  iptables -w -A KILLSTASS-LAN -j RETURN
  iptables -w -C DOCKER-USER -j KILLSTASS-LAN 2>/dev/null || iptables -w -I DOCKER-USER 1 -j KILLSTASS-LAN
  say "iptables DOCKER-USER guard installed: $IP:80/443 only from $NETS"
elif command -v nft >/dev/null; then
  # shellcheck disable=SC2086 # word splitting of the list is intended
  SET=$(printf '%s\n' $NETS | paste -sd, - | sed 's/,/, /g')
  # Own table only; never flush ruleset or edit Docker tables. Atomic replace of our own chains.
  if ! nft list table inet killstass >/dev/null 2>&1; then nft add table inet killstass; fi
  nft -f - <<NFT
flush table inet killstass
add chain inet killstass forward_guard { type filter hook forward priority -10; policy accept; }
add chain inet killstass input_guard { type filter hook input priority -10; policy accept; }
add rule inet killstass forward_guard meta nfproto ipv4 meta l4proto tcp ct direction original ct original ip daddr $IP ct original proto-dst { 80, 443 } ip saddr != { $SET } counter drop
add rule inet killstass input_guard ip daddr $IP tcp dport { 80, 443 } ip saddr != { $SET } counter drop
NFT
  say "nftables guard installed: $IP:80/443 only from $NETS"
else
  die 'no supported Docker firewall found; inspect the firewall before exposing the site'
fi
