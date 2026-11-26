-- v1.8: roster builder. team_data gains the BattleScribe-derived roster schema (imported by the operator,
-- read-only for the app); rosters belong to users; a match player may reference the roster it played.
ALTER TABLE team_data ADD COLUMN roster_schema jsonb, ADD COLUMN roster_hash text CHECK(roster_hash IS NULL OR length(roster_hash)=64);
CREATE TABLE rosters (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 team_slug text NOT NULL CHECK(team_slug ~ '^[a-z0-9][a-z0-9-]{1,63}$'),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
 data jsonb NOT NULL,
 schema_hash text,
 summary jsonb NOT NULL DEFAULT '{}',
 version int NOT NULL DEFAULT 1 CHECK(version>=1),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(pg_column_size(data) <= 262144)
);
CREATE INDEX rosters_user ON rosters(user_id, updated_at DESC);
ALTER TABLE match_players ADD COLUMN roster_id uuid REFERENCES rosters ON DELETE SET NULL;
