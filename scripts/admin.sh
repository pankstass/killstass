#!/bin/sh
# v1.9: operator only. The web admin page (#admin) is visible to accounts with users.is_admin;
# the runtime database role cannot change this flag, only the database owner (this script).
#   ./scripts/admin.sh list            administrators
#   ./scripts/admin.sh grant LOGIN     give LOGIN access to #admin
#   ./scripts/admin.sh revoke LOGIN    take it away
# v1.10:
#   ./scripts/admin.sh password LOGIN  one-time password reset code for LOGIN (valid RESET_TTL_MINUTES)
set -eu
cd "$(dirname "$0")/.."
q() { docker compose exec -T db sh -c 'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' psql "$@"; }
login=${2:-}
need_login() {
  case "$login" in ''|*[!A-Za-z0-9_.-]*) echo 'usage: admin.sh grant|revoke|password LOGIN (letters, digits, _ . -)' >&2; exit 1;; esac
}
case "${1:-list}" in
  list) q -c "SELECT login, display_name, created_at::date AS since FROM users WHERE is_admin ORDER BY login" ;;
  grant|revoke)
    need_login
    flag=true; [ "$1" = revoke ] && flag=false
    n=$(q -tA -v login="$login" -v flag="$flag" <<'SQL'
WITH u AS (UPDATE users SET is_admin = :'flag'::boolean WHERE login = :'login' RETURNING 1) SELECT count(*) FROM u;
SQL
)
    [ "$(printf '%s' "$n" | tr -d ' \r\n')" = 1 ] || { echo "No user with login $login" >&2; exit 1; }
    echo "$1: $login" ;;
  password)
    need_login
    docker compose exec -T api python -m api.accounts reset "$login" ;;
  *) echo 'usage: admin.sh [list|grant LOGIN|revoke LOGIN|password LOGIN]' >&2; exit 1 ;;
esac
