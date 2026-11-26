#!/bin/sh
# v1.9: browser e2e and accessibility tests (Playwright + axe-core, tests/e2e) against a throwaway stack:
# database and API in an internal Docker network, Chromium in a container that shares the API's network
# namespace, so the app is http://localhost:8000 for the browser (a secure context: the session cookie is Secure).
# No production container, volume or port is touched.
#   ./scripts/e2e-docker.sh                                  all browser tests (roster tests skip without team data)
#   E2E_TEAMS_BUNDLE=teams-bundle.json ./scripts/e2e-docker.sh   load the team reference first (like import-teams.sh)
#   E2E_RULES_BUNDLE=rules-bundle.json ./scripts/e2e-docker.sh   v1.11: and/or the general rules (like import-rules.sh)
#   E2E_BROWSERS="chromium firefox webkit" ./scripts/e2e-docker.sh   v1.14: the same tests in each engine (default chromium)
# Building the test image needs mcr.microsoft.com/playwright and the npm registry (internet or a mirror).
set -eu
cd "$(dirname "$0")/.."
net=killstass-e2e-network
db=killstass-e2e-db
api=killstass-e2e-api
envfile=$(mktemp)
sql=$(mktemp)
chmod 600 "$envfile" "$sql"
cleanup() { docker rm -fv "$api" "$db" >/dev/null 2>&1 || true; docker network rm "$net" >/dev/null 2>&1 || true; rm -f "$envfile" "$sql"; }
# Refuse collisions instead of removing someone else's running test.
for c in "$db" "$api"; do
  if docker inspect "$c" >/dev/null 2>&1; then echo "Container $c already exists." >&2; rm -f "$envfile" "$sql"; exit 1; fi
done
if docker network inspect "$net" >/dev/null 2>&1; then echo 'E2E network already exists.' >&2; rm -f "$envfile" "$sql"; exit 1; fi
if [ -n "${E2E_TEAMS_BUNDLE:-}" ] && [ ! -f "$E2E_TEAMS_BUNDLE" ]; then echo "no such file: $E2E_TEAMS_BUNDLE" >&2; rm -f "$envfile" "$sql"; exit 1; fi
if [ -n "${E2E_RULES_BUNDLE:-}" ] && [ ! -f "$E2E_RULES_BUNDLE" ]; then echo "no such file: $E2E_RULES_BUNDLE" >&2; rm -f "$envfile" "$sql"; exit 1; fi
browsers=${E2E_BROWSERS:-chromium}
for b in $browsers; do
  case "$b" in chromium|firefox|webkit) ;; *) echo "unknown browser: $b (chromium, firefox, webkit)" >&2; rm -f "$envfile" "$sql"; exit 1 ;; esac
done
trap cleanup EXIT HUP INT TERM
password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
cat > "$envfile" <<ENV
POSTGRES_DB=killstass_e2e
POSTGRES_USER=killstass_owner
POSTGRES_PASSWORD=$password
DB_APP_PASSWORD=$password
POSTGRES_INITDB_ARGS=--encoding=UTF8 --auth-host=scram-sha-256
DATABASE_URL=postgresql://killstass_app:$password@$db:5432/killstass_e2e
APP_ORIGIN=http://localhost:8000
TZ=UTC
ENV
docker build -t killstass-db:e2e ./db
docker build -t killstass-api:e2e -f api/Dockerfile .
docker build -t killstass-e2e:local -f tests/e2e/Dockerfile .
docker network create --internal "$net" >/dev/null
docker run -d --name "$db" --network "$net" --env-file "$envfile" --memory 640m --cpus 1.25 killstass-db:e2e >/dev/null
migrations=$(ls db/migrations/*.sql | wc -l | tr -d ' ')
ready=0
for i in $(seq 1 60); do
  if docker exec "$db" sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -h 127.0.0.1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc 'SELECT count(*)>=$migrations FROM schema_migrations'" 2>/dev/null | grep -q t; then ready=1; break; fi
  sleep 2
done
[ "$ready" = 1 ] || { docker logs --tail=50 "$db" >&2; exit 1; }
docker run -d --name "$api" --network "$net" --env-file "$envfile" --read-only --tmpfs /tmp:size=16m,noexec,nosuid \
  --cap-drop ALL --security-opt no-new-privileges --memory 384m --cpus 1.0 killstass-api:e2e >/dev/null
ready=0
for i in $(seq 1 30); do
  if docker exec "$api" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" 2>/dev/null; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { docker logs --tail=50 "$api" >&2; exit 1; }
if [ -n "${E2E_TEAMS_BUNDLE:-}" ]; then
  docker exec -i "$api" python -m api.teamdata sql < "$E2E_TEAMS_BUNDLE" > "$sql"
  docker exec -i "$db" sh -c 'psql -X -q -A -t -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$sql" >/dev/null
  echo 'Team reference loaded.' >&2
fi
if [ -n "${E2E_RULES_BUNDLE:-}" ]; then
  docker exec -i "$api" python -m api.rulesdata sql < "$E2E_RULES_BUNDLE" > "$sql"
  docker exec -i "$db" sh -c 'psql -X -q -A -t -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$sql" >/dev/null
  echo 'General rules loaded.' >&2
fi
browser() { docker run --rm --network "container:$api" --shm-size 512m --memory 1536m --cpus 2 "$@"; }
fail() { echo "E2E tests failed. API log:" >&2; docker logs --tail=80 "$api" >&2; exit 1; }
# 1) everything as regular users (the administrator part of admin.test.mjs is skipped), in each engine
#    (v1.14: the Playwright image has Chromium, Firefox and WebKit; each run signs in again)
#    The per-address limits (sign-in, invitations) start afresh for each engine: one throwaway database, one IP.
for b in $browsers; do
  echo "E2E: $b" >&2
  echo 'DELETE FROM rate_limits;' | docker exec -i "$db" sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
  browser -e E2E_BROWSER="$b" killstass-e2e:local || fail
done
# 2) the database owner grants #admin to e2e-alpha (the app role cannot), then the administrator part is mandatory
echo "UPDATE users SET is_admin = true WHERE login = 'e2e-alpha';" |
  docker exec -i "$db" sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
browser -e E2E_ADMIN=1 -e E2E_BROWSER="${browsers%% *}" killstass-e2e:local node --test tests/e2e/admin.test.mjs || fail
echo "E2E tests passed ($browsers)."
