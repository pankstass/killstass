#!/bin/sh
# Operator (v1.11): import the general Kill Team rules for the reference — weapon rules and the phase overview
# from warhammer-oracle (github.com/gregario/warhammer-oracle, read as data, its code is never run).
#   ./scripts/import-rules.sh               download the latest release and load it
#   ./scripts/import-rules.sh BUNDLE.json   load a prepared bundle (no internet needed)
#   ./scripts/import-rules.sh --status      show the last import
# Pin a release with ORACLE_REF=v0.2.99; SAVE_BUNDLE=FILE keeps the downloaded bundle. The complete update of the
# reference (rules + teams, backup, checks, report, rollback) is ./scripts/update-reference.sh.
set -eu
cd "$(dirname "$0")/.."
case "${1:-}" in
  --status) exec docker compose exec -T api python -m api.rulesdata status ;;
  -h|--help) sed -n 2,8p "$0"; exit 0 ;;
esac
SQL=$(mktemp /tmp/killstass-rules-sql.XXXXXX)
trap 'rm -f "$SQL"' EXIT
if [ -n "${1:-}" ]; then
  BUNDLE=$1
  [ -f "$BUNDLE" ] || { echo "no such file: $BUNDLE" >&2; exit 1; }
else
  BUNDLE=$(mktemp /tmp/killstass-rules.XXXXXX)
  trap 'rm -f "$SQL" "$BUNDLE"' EXIT
  echo 'Downloading from GitHub (warhammer-oracle)...' >&2
  docker run --rm --network bridge --read-only --tmpfs /tmp:size=16m --cap-drop ALL --security-opt no-new-privileges \
    -e ORACLE_REF="${ORACLE_REF:-}" killstass-api:local python -m api.rulesdata fetch > "$BUNDLE"
  if [ -n "${SAVE_BUNDLE:-}" ]; then cp "$BUNDLE" "$SAVE_BUNDLE"; echo "bundle saved to $SAVE_BUNDLE" >&2; fi
fi
# Same path as import-teams.sh: the api container checks the bundle and writes SQL, the database owner applies it
# in one transaction (the app role can only read rule_entries).
docker compose exec -T api python -m api.rulesdata sql < "$BUNDLE" > "$SQL"
docker compose exec -T db sh -c 'psql -X -q -A -t -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$SQL"
echo 'Done. Open "Справочник" in the app (refresh the page).' >&2
