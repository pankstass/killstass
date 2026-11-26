-- v1.2: quick start without friendship (match invites) and single-device hot-seat matches.
-- Append-only: existing matches keep kind/status/scoring_mode; totals still derive from primary rows.
ALTER TABLE matches DROP CONSTRAINT matches_kind_check;
ALTER TABLE matches ADD CONSTRAINT matches_kind_check CHECK(kind IN ('friend','guest','hotseat'));
-- One-time join codes. A code is a short-lived join secret, not an auth credential:
-- it only fills the empty slot 2 of a match still in setup, for an authenticated account.
CREATE TABLE match_invites (
 code varchar(8) PRIMARY KEY CHECK(code ~ '^[A-Z2-9]{6,8}$'),
 match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 created_by bigint REFERENCES users ON DELETE CASCADE,
 expires_at timestamptz NOT NULL,
 used_by bigint REFERENCES users ON DELETE SET NULL,
 used_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX invites_one_open ON match_invites(match_id) WHERE used_at IS NULL;
-- Ended hot-seat matches are 'unconfirmed' (no remote opponent): kill-grade bonus and primary bonus apply.
CREATE OR REPLACE VIEW player_totals AS
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
 SELECT r.*,r.grade+CASE WHEN r.status IN ('awaiting_confirmation','confirmed','disputed','unconfirmed') AND r.grade>op.grade THEN 1 ELSE 0 END AS kill
 FROM raw r JOIN raw op ON op.match_id=r.match_id AND op.id<>r.id
), bonus AS (
 SELECT c.*,CASE WHEN scoring_mode='approved2025' AND status IN ('awaiting_confirmation','confirmed','disputed','unconfirmed')
 THEN primary_bonus(CASE primary_op WHEN 'crit' THEN crit WHEN 'tac' THEN tac WHEN 'kill' THEN kill ELSE 0 END) ELSE 0 END AS primary_bonus FROM components c
)
SELECT id,match_id,raw_vp,crit,tac,kill,incapacitated,grade,primary_bonus,
 CASE WHEN scoring_mode='approved2025' THEN crit+tac+kill+primary_bonus ELSE raw_vp END::int AS vp FROM bonus;
-- Hot-seat results count only for the owner, exactly like guest quick records.
CREATE OR REPLACE VIEW player_results AS
SELECT p.user_id,m.id AS match_id,m.kind,m.edition,m.played_at,m.mission_id,m.killzone_id,
 p.team_id,op.team_id AS opponent_team_id,op.user_id AS opponent_id,op.display_name AS opponent_name,
 pt.vp AS vp_for,ot.vp AS vp_against,
 CASE WHEN pt.vp>ot.vp THEN 'win' WHEN pt.vp=ot.vp THEN 'draw' ELSE 'loss' END AS result
FROM matches m JOIN match_players p ON p.match_id=m.id JOIN match_players op ON op.match_id=m.id AND op.slot<>p.slot
JOIN player_totals pt ON pt.id=p.id JOIN player_totals ot ON ot.id=op.id
WHERE p.user_id IS NOT NULL AND (m.status='confirmed' OR (m.kind IN ('guest','hotseat') AND m.status='unconfirmed' AND m.created_by=p.user_id));
