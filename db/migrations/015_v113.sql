-- v1.13: conceding a match, local players (people without an account) and the source of the operative count.
-- Additive: new columns and one table; player_totals keeps its columns (a conceded match counts 10:0).
-- v1.12 ignores all of it (it reads the view, which still works after a rollback of the code).
ALTER TABLE matches ADD COLUMN conceded_slot smallint CHECK(conceded_slot IN (1,2));
-- 'roster': from the attached roster; 'team': from the team's composition; 'manual': typed in.
ALTER TABLE match_players ADD COLUMN operative_source varchar(8) CHECK(operative_source IN ('roster','team','manual'));
-- One record per person, shared by every account that records matches against them (the club's list);
-- the name is unique case- and ё-insensitively. Deleting one keeps the matches (the name stays in them).
CREATE TABLE local_players (
 id uuid PRIMARY KEY,
 name varchar(64) NOT NULL CHECK(btrim(name) <> ''),
 created_by bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX local_players_name ON local_players(ks_fold(name));
ALTER TABLE match_players ADD COLUMN local_player_id uuid REFERENCES local_players ON DELETE SET NULL;
CREATE INDEX match_players_local ON match_players(local_player_id,match_id) WHERE local_player_id IS NOT NULL;
-- Same columns as in 005; a conceded match: 0 VP for the player who conceded, 10 for the opponent.
CREATE OR REPLACE VIEW player_totals AS
WITH raw AS (
 SELECT p.id,p.match_id,p.slot,p.primary_op,m.scoring_mode,m.status,m.conceded_slot,
 coalesce((SELECT sum(s.vp) FROM turning_point_scores s WHERE s.player_id=p.id),0)::int AS raw_vp,
 coalesce((SELECT sum(s.vp) FROM turning_point_scores s WHERE s.player_id=p.id AND m.rules_snapshot->'sources'->>(s.source_id::text)='crit'),0)::int AS crit,
 coalesce((SELECT sum(s.vp) FROM turning_point_scores s WHERE s.player_id=p.id AND m.rules_snapshot->'sources'->>(s.source_id::text)='tac'),0)::int AS tac,
 coalesce((SELECT sum(k.delta) FROM operative_kills k WHERE k.player_id=p.id),0)::int AS incapacitated,
 kill_grade(coalesce((SELECT sum(k.delta) FROM operative_kills k WHERE k.player_id=p.id),0)::int,
 coalesce(m.rules_snapshot->'thresholds'->(op.operative_count::text),'[]'::jsonb)) AS grade
 FROM match_players p JOIN matches m ON m.id=p.match_id JOIN match_players op ON op.match_id=p.match_id AND op.slot<>p.slot
), components AS (
 SELECT r.*,r.grade+CASE WHEN r.status IN ('awaiting_confirmation','confirmed','disputed','unconfirmed') AND r.grade>op.grade THEN 1 ELSE 0 END AS kill
 FROM raw r JOIN raw op ON op.match_id=r.match_id AND op.id<>r.id
), bonus AS (
 SELECT c.*,CASE WHEN scoring_mode='approved2025' AND status IN ('awaiting_confirmation','confirmed','disputed','unconfirmed')
 THEN primary_bonus(CASE primary_op WHEN 'crit' THEN crit WHEN 'tac' THEN tac WHEN 'kill' THEN kill ELSE 0 END) ELSE 0 END AS primary_bonus FROM components c
)
SELECT id,match_id,raw_vp,crit,tac,kill,incapacitated,grade,primary_bonus,
 CASE WHEN conceded_slot IS NOT NULL THEN CASE WHEN slot=conceded_slot THEN 0 ELSE 10 END
 WHEN scoring_mode='approved2025' THEN crit+tac+kill+primary_bonus ELSE raw_vp END::int AS vp FROM bonus;
