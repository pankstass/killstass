#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Dedicated test database only. New catalog tests skip DB work without TEST_DATABASE_URL.
if [ -n "${TEST_DATABASE_URL:-}" ]; then
 : "${DATABASE_URL:?Set runtime DATABASE_URL to the same test database}"
 python -m pytest -q tests
else
 python -m pytest -q tests/test_domain.py tests/test_catalog_ops.py tests/test_deployment.py
 echo 'Integration skipped: set TEST_DATABASE_URL (test owner with CREATEDB) and DATABASE_URL (app role), never production.'
fi
