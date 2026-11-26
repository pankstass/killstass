#!/bin/sh
set -eu
export PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB"
# One session, advisory lock; each migration transactional, error aborts startup.
{
 echo '\set ON_ERROR_STOP on'
 echo 'SELECT pg_advisory_lock(73428391);'
 echo 'CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY, applied_at timestamptz DEFAULT now());'
 for f in /opt/killstass/migrations/*.sql; do
  v=$(basename "$f")
  printf "SELECT NOT EXISTS(SELECT 1 FROM schema_migrations WHERE version='%s') AS run \\gset\n" "$v"
  echo '\if :run'
  echo 'BEGIN;'
  printf '\\i %s\n' "$f"
  printf "INSERT INTO schema_migrations(version) VALUES('%s');\n" "$v"
  echo 'COMMIT;'
  echo '\endif'
 done
 echo 'SELECT pg_advisory_unlock(73428391);'
} | psql -X
# Runtime role: no superuser, no DDL. Password supplied via psql variable, never shell interpolation.
psql -X -v app_pass="$DB_APP_PASSWORD" <<'SQL'
\set ON_ERROR_STOP on
SELECT format('CREATE ROLE killstass_app LOGIN PASSWORD %L', :'app_pass')
WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='killstass_app') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO killstass_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO killstass_app;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO killstass_app;
REVOKE ALL ON schema_migrations FROM killstass_app;
GRANT SELECT ON schema_migrations TO killstass_app;
REVOKE UPDATE,DELETE ON match_audit FROM killstass_app;
REVOKE INSERT,UPDATE,DELETE ON catalogs,game_sequence,team_data,team_data_imports FROM killstass_app;
-- v1.11: rules reference, its search index and the update journal are written by the owner only (import scripts).
REVOKE INSERT,UPDATE,DELETE ON rule_entries,rule_imports,reference_updates,reference_search FROM killstass_app;
-- v1.9: users.is_admin is changed by the operator only (scripts/admin.sh), never by the runtime role.
REVOKE INSERT,UPDATE ON users FROM killstass_app;
GRANT INSERT(public_id,login,email,display_name,password_hash) ON users TO killstass_app;
GRANT UPDATE(display_name,password_hash) ON users TO killstass_app;
GRANT SELECT ON catalogs,game_sequence,team_data,team_data_imports,rule_entries,rule_imports,reference_updates,reference_search TO killstass_app;
-- Reapply on upgrade/restore; role is created above, after versioned migrations.
-- Short aggregate requests on ass-srv suffered from JIT overhead. New sessions only.
SELECT format('ALTER ROLE killstass_app IN DATABASE %I SET jit = off', current_database()) \gexec
SQL
