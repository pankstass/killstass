#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
file=${1:?Usage: restore.sh /absolute/path/file.dump --yes}
[ "${2:-}" = '--yes' ] || { echo 'Destructive restore. Make a backup first; pass --yes.' >&2; exit 1; }
[ -s "$file" ]
docker compose exec -T db pg_restore --list < "$file" >/dev/null
docker compose stop proxy api
# Transaction: failed restore rolls back; runtime schema grants restored below.
# Existing migration version table is included in the dump.
docker compose exec -T db sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-acl --single-transaction --exit-on-error' < "$file"
docker compose exec -T db /opt/killstass/migrate.sh
# Revoke all bearer tokens copied into the backup.
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "TRUNCATE sessions;"'
docker compose up -d api proxy
echo 'Restored. All players must log in again.'
