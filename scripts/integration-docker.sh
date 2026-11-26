#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Isolated network / ephemeral database. No production volume or published port.
net=killstass-test-network
db=killstass-test-db
tmp=$(mktemp)
chmod 600 "$tmp"
cleanup() { docker rm -fv "$db" >/dev/null 2>&1 || true; docker network rm "$net" >/dev/null 2>&1 || true; rm -f "$tmp"; }
# Refuse collisions instead of removing someone else's running test.
if docker inspect "$db" >/dev/null 2>&1; then echo 'Test container already exists.' >&2; rm -f "$tmp"; exit 1; fi
if docker network inspect "$net" >/dev/null 2>&1; then echo 'Test network already exists.' >&2; rm -f "$tmp"; exit 1; fi
trap cleanup EXIT HUP INT TERM
password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
cat > "$tmp" <<ENV
POSTGRES_DB=killstass_test
POSTGRES_USER=killstass_owner
POSTGRES_PASSWORD=$password
DB_APP_PASSWORD=$password
POSTGRES_INITDB_ARGS=--encoding=UTF8 --auth-host=scram-sha-256
DATABASE_URL=postgresql://killstass_app:$password@$db:5432/killstass_test
TEST_DATABASE_URL=postgresql://killstass_owner:$password@$db:5432/killstass_test
ENV
docker build -t killstass-db:test ./db
docker build -t killstass-tests:local -f tests/Dockerfile .
docker network create "$net" >/dev/null
docker run -d --name "$db" --network "$net" --env-file "$tmp" --memory 640m --cpus 1.25 killstass-db:test >/dev/null
ready=0
for i in $(seq 1 60); do
 if docker exec "$db" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*)>=4 FROM schema_migrations"' 2>/dev/null | grep -q t; then ready=1;break;fi
 sleep 2
done
[ "$ready" = 1 ] || { docker logs --tail=50 "$db"; exit 1; }
docker run --rm --network "$net" --env-file "$tmp" --memory 384m --cpus 1.0 killstass-tests:local
