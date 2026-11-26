#!/bin/sh
# KILLSTASS v1.10: Web Push — notifications on phones and computers even when the app is closed.
# The api container stays without internet access and only queues messages (push_outbox); the optional
# `pushworker` service (COMPOSE_PROFILES=push, networks backend + edge) sends them to the browsers' push
# services. Browsers allow push only on a trusted HTTPS address: the domain with the Let's Encrypt
# certificate (scripts/domain.sh, scripts/cert.sh) or devices with the local CA installed. iPhone/iPad:
# iOS 16.4+, the site added to the Home Screen. Players turn it on in «Профиль → Уведомления на устройстве».
#   ./scripts/push.sh enable CONTACT    CONTACT: mailto:you@example.org (or an https:// page) for push services
#   ./scripts/push.sh disable
#   ./scripts/push.sh status            subscriptions, queue, last delivery
#   ./scripts/push.sh test LOGIN        a test notification to the devices of LOGIN
# Optional: PUSH_HTTPS_PROXY in .env when the server reaches the internet through a proxy.
set -eu
cd "$(dirname "$0")/.."
. ./scripts/lib.sh
need_root

case "${1:-status}" in
  enable)
    contact=${2:-$(envget PUSH_CONTACT)}
    case "$contact" in
      mailto:*@*|https://*) ;;
      *@*.*) contact="mailto:$contact" ;;
      *) die 'usage: push.sh enable mailto:you@example.org' ;;
    esac
    envset PUSH_CONTACT "$contact"
    envset PUSH_ENABLED 1
    profile_on push
    docker compose up -d --wait api
    docker compose up -d pushworker
    sleep 2
    docker compose logs --tail 3 pushworker || true
    say "Web Push is on (contact $contact). Check: ./scripts/push.sh test YOUR_LOGIN after subscribing a device."
    ;;
  disable)
    if profile_has push; then
      docker compose stop pushworker || true
      docker compose rm -f pushworker || true
    fi
    profile_off push
    envset PUSH_ENABLED 0
    docker compose up -d --wait api
    say 'Web Push is off (subscriptions are kept for the next enable).'
    ;;
  status)
    docker compose exec -T api python -m api.push status
    if profile_has push; then docker compose ps pushworker; else echo 'pushworker: disabled (COMPOSE_PROFILES)'; fi
    ;;
  test)
    login=${2:-}
    case "$login" in '' | *[!A-Za-z0-9_.-]*) die 'usage: push.sh test LOGIN' ;; esac
    docker compose exec -T api python -m api.push test "$login"
    ;;
  *) echo 'usage: push.sh enable CONTACT | disable | status | test LOGIN' >&2; exit 2 ;;
esac
