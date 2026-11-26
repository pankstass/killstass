-- v1.7: team & operative reference imported by the operator (scripts/import-teams.sh). Append-only.
-- Content comes from community sources (kt-datacards, BSData) and is NOT shipped with KILLSTASS:
-- the server operator imports it into this table; it is served read-only to signed-in users.
CREATE TABLE team_data (
 slug text PRIMARY KEY CHECK(slug ~ '^[a-z0-9][a-z0-9-]{1,63}$'),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 catalog_id bigint REFERENCES catalogs ON DELETE SET NULL,
 data jsonb NOT NULL,
 sources jsonb NOT NULL DEFAULT '{}',
 content_hash text NOT NULL CHECK(length(content_hash)=64),
 imported_at timestamptz NOT NULL DEFAULT now(),
 active boolean NOT NULL DEFAULT true
);
CREATE INDEX team_data_catalog ON team_data(catalog_id) WHERE active;
CREATE TABLE team_data_imports (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 imported_at timestamptz NOT NULL DEFAULT now(),
 built_at timestamptz,
 sources jsonb NOT NULL DEFAULT '{}',
 teams int NOT NULL CHECK(teams>=0),
 operatives int NOT NULL CHECK(operatives>=0),
 warnings jsonb NOT NULL DEFAULT '[]'
);
