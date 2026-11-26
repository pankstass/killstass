#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose exec -T db /opt/killstass/migrate.sh
