#!/bin/sh
# v1.9: release smoke checks (run by update.sh; safe to run by hand at any time).
#   ./scripts/smoke.sh --pre    before the old stack stops: compose file, `caddy validate` of the NEW proxy image
#   ./scripts/smoke.sh --post   after the new stack is up: /api/health (status, VERSION, migration count),
#                               schema_migrations in PostgreSQL, the page's version meta, versioned static files
# v1.10 (--post): /sw.js of the release and the app icon; warnings (no failure, no rollback) for the TLS
#   certificate of KS_DOMAIN and for the optional pushworker / tailscale services of COMPOSE_PROFILES.
set -eu
cd "$(dirname "$0")/.."
. ./scripts/lib.sh
VERSION=$(tr -d ' \r\n' < VERSION)
MIGRATIONS=$(ls db/migrations/*.sql | wc -l | tr -d ' ')
fail() { echo "smoke: FAIL: $*" >&2; exit 1; }
ok() { echo "smoke: ok: $*"; }
warn() { echo "smoke: WARN: $*" >&2; }
case "${1:-}" in
  --pre)
    docker compose config -q || fail 'docker-compose.yml / .env'
    # The freshly built image validates its own Caddyfile. Scratch storage in the container's /tmp:
    # the live caddy_data volume (internal CA) is not touched.
    if ! out=$(docker compose run --rm --no-deps -T -e XDG_DATA_HOME=/tmp -e XDG_CONFIG_HOME=/tmp \
        --entrypoint caddy proxy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1); then
      printf '%s\n' "$out" | tail -n 5 >&2
      fail 'caddy validate (the running stack was not touched)'
    fi
    ok "caddy validate, compose config (release $VERSION)"
    ;;
  --post)
    docker compose exec -T -e EXPECT_VERSION="$VERSION" -e EXPECT_MIGRATIONS="$MIGRATIONS" api python - <<'PY' || fail 'api checks'
import json, os, pathlib, re, sys, time, urllib.request
base = 'http://127.0.0.1:8000'
want_v, want_m = os.environ['EXPECT_VERSION'], int(os.environ['EXPECT_MIGRATIONS'])
def get(path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.headers.get('Content-Type', ''), r.read()
for attempt in range(10):
    try:
        status, _, body = get('/api/health'); break
    except Exception as e:
        if attempt == 9: sys.exit(f'/api/health: {e}')
        time.sleep(2)
h = json.loads(body)
if h.get('status') != 'ok': sys.exit(f'/api/health status: {h}')
if h.get('version') != want_v: sys.exit(f"/api/health version {h.get('version')} != VERSION {want_v}")
if h.get('migrations') != want_m: sys.exit(f"/api/health migrations {h.get('migrations')} != {want_m} files in db/migrations")
_, _, page = get('/')
page = page.decode()
if not re.search(r'<meta name="killstass-version" content="%s"\s*/?>' % re.escape(want_v), page) or '{{' in page:
    sys.exit('index.html: version meta missing')
js = [p.relative_to('web').as_posix() for p in pathlib.Path('web').rglob('*.js') if p.name != 'sw.js']
if not {'main.js', 'boot.js'} <= set(js): sys.exit('web JavaScript files missing')
for f in js + ['style.css', 'i18n/ru.json', 'icons.svg']:
    status, ctype, _ = get(f'/static/v/{want_v}/{f}')
    if status != 200: sys.exit(f'/static/v/{want_v}/{f}: HTTP {status}')
status, ctype, sw = get('/sw.js')
sw = sw.decode()
if status != 200 or 'javascript' not in ctype or f'KILLSTASS {want_v}' not in sw or '{{' in sw: sys.exit('/sw.js: wrong release')
status, ctype, _ = get('/static/icon-192.png')
if status != 200 or ctype != 'image/png': sys.exit(f'/static/icon-192.png: HTTP {status} {ctype}')
print(f'api {want_v}, {want_m} migrations, page meta, versioned static, service worker')
PY
    applied=$(docker compose exec -T db sh -c 'exec psql -X -tAq -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM schema_migrations"' | tr -d ' \r\n')
    [ "$applied" = "$MIGRATIONS" ] || fail "schema_migrations has $applied rows, db/migrations has $MIGRATIONS files"
    docker compose exec -T proxy wget -q -O /dev/null http://127.0.0.1:8090/health || fail 'proxy health'
    docker compose exec -T proxy wget -q -O /dev/null http://api:8000/api/health || fail 'proxy -> api'
    ok "schema_migrations=$applied, proxy -> api (release $VERSION)"
    running=$(docker compose ps --status running --services 2>/dev/null || true)
    for svc in pushworker tailscale; do
      prof=$svc; [ "$svc" = pushworker ] && prof=push
      if profile_has "$prof" && ! printf '%s\n' "$running" | grep -qx "$svc"; then
        warn "$svc is not running (docker compose logs $svc)"
      fi
    done
    dom=$(envget KS_DOMAIN)
    if [ -n "$dom" ] && [ "$dom" != killstass.invalid ]; then
      ip=$(envget BIND_IP); ip=${ip:-192.168.1.250}
      if ! command -v openssl >/dev/null; then
        warn "openssl is not installed: TLS of $dom not checked"
      elif [ "$(envget KS_TLS_MODE)" = files ]; then
        if echo | openssl s_client -connect "$ip:443" -servername "$dom" -verify_hostname "$dom" -verify_return_error >/dev/null 2>&1
        then ok "TLS $dom: trusted certificate"
        else warn "TLS $dom: the certificate is not trusted or expired (./scripts/cert.sh status)"
        fi
      elif echo | openssl s_client -connect "$ip:443" -servername "$dom" 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -q "DNS:$dom"
      then ok "TLS $dom: internal certificate (Let's Encrypt: ./scripts/cert.sh issue)"
      else warn "TLS $dom: the proxy has no certificate for the domain (./scripts/domain.sh status)"
      fi
    fi
    ;;
  *) echo 'usage: smoke.sh --pre|--post' >&2; exit 2 ;;
esac
