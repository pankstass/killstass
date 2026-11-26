#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -e .env ]; then echo '.env already exists; not overwritten.'; exit 1; fi
umask 077
owner=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
app=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
sed -e "s/^DB_OWNER_PASSWORD=$/DB_OWNER_PASSWORD=$owner/" -e "s/^DB_APP_PASSWORD=$/DB_APP_PASSWORD=$app/" .env.example > .env
echo '.env created (0600).'
