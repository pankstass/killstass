-- v1.1: append-only upgrade. Existing matches deliberately remain legacy.
ALTER TABLE catalogs DROP CONSTRAINT catalogs_kind_check;
ALTER TABLE catalogs ADD CONSTRAINT catalogs_kind_check CHECK(kind IN ('team','mission','objective','killzone','source','pack','archetype','tac_op','rule'));
ALTER TABLE catalogs ADD COLUMN label_en text NOT NULL DEFAULT '';
ALTER TABLE catalogs ADD COLUMN source text CHECK(source IN ('battlekit','wahapedia'));
ALTER TABLE catalogs ADD COLUMN source_url text;
ALTER TABLE catalogs ADD COLUMN retrieved_at timestamptz;
ALTER TABLE catalogs ADD COLUMN rules_version text;
ALTER TABLE catalogs ADD COLUMN content_hash text CHECK(content_hash IS NULL OR content_hash ~ '^[a-f0-9]{64}$');
ALTER TABLE catalogs ADD COLUMN verification text NOT NULL DEFAULT 'legacy' CHECK(verification IN ('verified','unverified','conflict','legacy','local'));
CREATE TABLE game_sequence (
 code text PRIMARY KEY, edition text NOT NULL CHECK(edition IN ('2021','2024')),
 phase text NOT NULL, phase_order int NOT NULL, step_order int NOT NULL,
 label text NOT NULL, description text NOT NULL,
 source text NOT NULL CHECK(source IN ('battlekit','wahapedia')), source_url text NOT NULL,
 retrieved_at timestamptz NOT NULL, rules_version text NOT NULL, content_hash text NOT NULL CHECK(content_hash ~ '^[a-f0-9]{64}$'),
 verification text NOT NULL CHECK(verification IN ('verified','unverified','conflict')), active boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX sequence_active_order ON game_sequence(edition,phase_order,step_order) WHERE active;
ALTER TABLE matches ADD COLUMN scoring_mode text NOT NULL DEFAULT 'legacy' CHECK(scoring_mode IN ('legacy','approved2025'));
ALTER TABLE matches ADD COLUMN rules_snapshot jsonb NOT NULL DEFAULT '{}';
ALTER TABLE match_players ADD COLUMN aspect_counts jsonb NOT NULL DEFAULT '{}';
ALTER TABLE match_players ADD COLUMN primary_op text CHECK(primary_op IN ('crit','tac','kill'));
ALTER TABLE match_players ADD COLUMN primary_committed boolean NOT NULL DEFAULT false;
ALTER TABLE match_players ADD COLUMN tac_op_id bigint REFERENCES catalogs(id);
ALTER TABLE match_players ADD COLUMN tac_revealed boolean NOT NULL DEFAULT false;
ALTER TABLE turning_point_scores ADD COLUMN tac_op_id bigint REFERENCES catalogs(id);
CREATE TABLE operative_kills (
 player_id bigint NOT NULL REFERENCES match_players(id) ON DELETE CASCADE,
 turning_point int NOT NULL CHECK(turning_point BETWEEN 1 AND 12),
 delta int NOT NULL DEFAULT 0 CHECK(delta BETWEEN -40 AND 40),
 PRIMARY KEY(player_id,turning_point)
);
CREATE INDEX scores_tac ON turning_point_scores(tac_op_id,player_id) WHERE tac_op_id IS NOT NULL;
CREATE FUNCTION primary_bonus(v integer) RETURNS integer LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$ SELECT (greatest(v,0)+1)/2 $$;
CREATE FUNCTION kill_grade(kills integer, thresholds jsonb) RETURNS integer LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
 SELECT count(*)::integer FROM jsonb_array_elements_text(thresholds) x WHERE x::integer <= greatest(kills,0)
$$;
CREATE VIEW player_totals AS
WITH raw AS (
 SELECT p.id,p.match_id,p.primary_op,m.scoring_mode,m.status,
 coalesce((SELECT sum(s.vp) FROM turning_point_scores s WHERE s.player_id=p.id),0)::int AS raw_vp,
 coalesce((SELECT sum(s.vp) FROM turning_point_scores s WHERE s.player_id=p.id AND m.rules_snapshot->'sources'->>(s.source_id::text)='crit'),0)::int AS crit,
 coalesce((SELECT sum(s.vp) FROM turning_point_scores s WHERE s.player_id=p.id AND m.rules_snapshot->'sources'->>(s.source_id::text)='tac'),0)::int AS tac,
 coalesce((SELECT sum(k.delta) FROM operative_kills k WHERE k.player_id=p.id),0)::int AS incapacitated,
 kill_grade(coalesce((SELECT sum(k.delta) FROM operative_kills k WHERE k.player_id=p.id),0)::int,
 coalesce(m.rules_snapshot->'thresholds'->(op.operative_count::text),'[]'::jsonb)) AS grade
 FROM match_players p JOIN matches m ON m.id=p.match_id JOIN match_players op ON op.match_id=p.match_id AND op.slot<>p.slot
), components AS (
 SELECT r.*,r.grade+CASE WHEN r.status IN ('awaiting_confirmation','confirmed','disputed') AND r.grade>op.grade THEN 1 ELSE 0 END AS kill
 FROM raw r JOIN raw op ON op.match_id=r.match_id AND op.id<>r.id
), bonus AS (
 SELECT c.*,CASE WHEN scoring_mode='approved2025' AND status IN ('awaiting_confirmation','confirmed','disputed')
 THEN primary_bonus(CASE primary_op WHEN 'crit' THEN crit WHEN 'tac' THEN tac WHEN 'kill' THEN kill ELSE 0 END) ELSE 0 END AS primary_bonus FROM components c
)
SELECT id,match_id,raw_vp,crit,tac,kill,incapacitated,grade,primary_bonus,
 CASE WHEN scoring_mode='approved2025' THEN crit+tac+kill+primary_bonus ELSE raw_vp END::int AS vp FROM bonus;
CREATE OR REPLACE VIEW player_results AS
SELECT p.user_id,m.id AS match_id,m.kind,m.edition,m.played_at,m.mission_id,m.killzone_id,
 p.team_id,op.team_id AS opponent_team_id,op.user_id AS opponent_id,op.display_name AS opponent_name,
 pt.vp AS vp_for,ot.vp AS vp_against,
 CASE WHEN pt.vp>ot.vp THEN 'win' WHEN pt.vp=ot.vp THEN 'draw' ELSE 'loss' END AS result
FROM matches m JOIN match_players p ON p.match_id=m.id JOIN match_players op ON op.match_id=m.id AND op.slot<>p.slot
JOIN player_totals pt ON pt.id=p.id JOIN player_totals ot ON ot.id=op.id
WHERE p.user_id IS NOT NULL AND (m.status='confirmed' OR (m.kind='guest' AND m.status='unconfirmed' AND m.created_by=p.user_id));
