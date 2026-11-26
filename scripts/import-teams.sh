#!/bin/sh
# Operator: import the team & operative reference (v1.7) with roster-builder schemas (v1.8).
#   ./scripts/import-teams.sh               download the latest data from GitHub and load it
#   ./scripts/import-teams.sh BUNDLE.json   load a prepared bundle (no internet needed)
#   ./scripts/import-teams.sh --status      show the last import
# Sources: github.com/Wen-Qualtu/kt-datacards and github.com/BSData/wh40k-killteam (pin with KTD_REF / BSDATA_REF).
# The web app itself never goes online: downloading runs in a throwaway container on Docker's default network.
set -eu
cd "$(dirname "$0")/.."
case "${1:-}" in
  --status) exec docker compose exec -T api python -m api.teamdata status ;;
  -h|--help) sed -n 2,7p "$0"; exit 0 ;;
esac
SQL=$(mktemp /tmp/killstass-teams-sql.XXXXXX)
trap 'rm -f "$SQL"' EXIT
if [ -n "${1:-}" ]; then
  BUNDLE=$1
  [ -f "$BUNDLE" ] || { echo "no such file: $BUNDLE" >&2; exit 1; }
else
  BUNDLE=$(mktemp /tmp/killstass-teams.XXXXXX)
  trap 'rm -f "$SQL" "$BUNDLE"' EXIT
  echo 'Downloading from GitHub (kt-datacards, BSData)...' >&2
  docker run --rm --network bridge --read-only --tmpfs /tmp:size=16m --cap-drop ALL --security-opt no-new-privileges \
    -e KTD_REF="${KTD_REF:-main}" -e BSDATA_REF="${BSDATA_REF:-master}" \
    killstass-api:local python -m api.teamdata fetch > "$BUNDLE"
  if [ -n "${SAVE_BUNDLE:-}" ]; then cp "$BUNDLE" "$SAVE_BUNDLE"; echo "bundle saved to $SAVE_BUNDLE" >&2; fi
fi
# The app role can only read the reference: the api container validates the bundle and turns it into SQL,
# the database owner applies it in one transaction over the local socket of the db container.
docker compose exec -T api python -m api.teamdata sql < "$BUNDLE" > "$SQL"
docker compose exec -T db sh -c 'psql -X -q -A -t -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$SQL"
echo 'Done. Open "Команды" in the app (refresh the page).' >&2
