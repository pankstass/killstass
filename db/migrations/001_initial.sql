CREATE TABLE users (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 public_id varchar(8) UNIQUE NOT NULL CHECK(public_id ~ '^[A-Z2-9]{8}$'),
 login varchar(64) NOT NULL UNIQUE, email varchar(254) UNIQUE,
 display_name varchar(64) NOT NULL, password_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE sessions (
 token_hash text PRIMARY KEY, user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 csrf text NOT NULL, expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE rate_limits (bucket text PRIMARY KEY, hits int NOT NULL, expires_at timestamptz NOT NULL);
CREATE TABLE friendships (
 requester_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 recipient_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 status text NOT NULL CHECK(status IN ('pending','accepted')),
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(requester_id<>recipient_id),
 PRIMARY KEY(requester_id,recipient_id)
);
CREATE UNIQUE INDEX friendship_pair ON friendships(least(requester_id,recipient_id),greatest(requester_id,recipient_id));
CREATE TABLE blocks (
 user_id bigint REFERENCES users ON DELETE CASCADE, target_id bigint REFERENCES users ON DELETE CASCADE,
 PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id)
);
CREATE TABLE catalogs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, code text UNIQUE NOT NULL,
 kind text NOT NULL CHECK(kind IN ('team','mission','objective','killzone','source')),
 edition text NOT NULL CHECK(edition IN ('2021','2024')), label text NOT NULL,
 config jsonb NOT NULL DEFAULT '{}', active boolean NOT NULL DEFAULT true
);
CREATE INDEX catalogs_kind ON catalogs(edition,kind) WHERE active;
CREATE TABLE guest_opponents (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 name varchar(64) NOT NULL, linked_user_id bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE challenges (
 id uuid PRIMARY KEY, sender_id bigint REFERENCES users ON DELETE SET NULL,
 recipient_id bigint REFERENCES users ON DELETE SET NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined','cancelled','expired')),
 proposal jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 CHECK(sender_id<>recipient_id)
);
CREATE INDEX challenges_incoming ON challenges(recipient_id,status,expires_at);
CREATE TABLE matches (
 id uuid PRIMARY KEY, created_by bigint REFERENCES users ON DELETE SET NULL,
 challenge_id uuid UNIQUE REFERENCES challenges, kind text NOT NULL CHECK(kind IN ('friend','guest')),
 status text NOT NULL CHECK(status IN ('setup','active','awaiting_confirmation','disputed','confirmed','unconfirmed','cancelled')),
 edition text NOT NULL DEFAULT '2024' CHECK(edition IN ('2021','2024')),
 mission_id bigint REFERENCES catalogs, killzone_id bigint REFERENCES catalogs,
 setup jsonb NOT NULL DEFAULT '{}', turns int NOT NULL DEFAULT 4 CHECK(turns BETWEEN 1 AND 12),
 current_turn int NOT NULL DEFAULT 1 CHECK(current_turn BETWEEN 1 AND 12),
 initiative smallint NOT NULL DEFAULT 1 CHECK(initiative IN (1,2)),
 submitted_by bigint REFERENCES users ON DELETE SET NULL,
 played_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(), version int NOT NULL DEFAULT 1,
 notes varchar(4000) NOT NULL DEFAULT ''
);
CREATE TABLE match_players (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 slot smallint NOT NULL CHECK(slot IN (1,2)), user_id bigint REFERENCES users ON DELETE SET NULL,
 guest_id uuid REFERENCES guest_opponents ON DELETE SET NULL,
 display_name varchar(64) NOT NULL, team_id bigint REFERENCES catalogs,
 roster varchar(4000) NOT NULL DEFAULT '', operative_count int CHECK(operative_count BETWEEN 1 AND 40),
 UNIQUE(match_id,slot), UNIQUE(match_id,user_id)
);
CREATE INDEX match_players_user ON match_players(user_id,match_id);
CREATE INDEX matches_date ON matches(played_at DESC,id);
CREATE TABLE turning_point_scores (
 player_id bigint NOT NULL REFERENCES match_players ON DELETE CASCADE,
 turning_point int NOT NULL CHECK(turning_point BETWEEN 1 AND 12),
 source_id bigint NOT NULL REFERENCES catalogs, vp int NOT NULL DEFAULT 0 CHECK(vp BETWEEN 0 AND 999),
 PRIMARY KEY(player_id,turning_point,source_id)
);
CREATE TABLE turning_point_states (
 player_id bigint NOT NULL REFERENCES match_players ON DELETE CASCADE,
 turning_point int NOT NULL CHECK(turning_point BETWEEN 1 AND 12),
 cp int NOT NULL DEFAULT 0 CHECK(cp BETWEEN 0 AND 99), notes varchar(2000) NOT NULL DEFAULT '',
 PRIMARY KEY(player_id,turning_point)
);
CREATE TABLE match_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 actor_id bigint REFERENCES users ON DELETE SET NULL, action text NOT NULL,
 before_data jsonb, after_data jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_match ON match_audit(match_id,id);
CREATE TABLE operations (
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE, request_id uuid NOT NULL,
 resource text NOT NULL, payload_hash text NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(user_id,request_id)
);
CREATE TABLE notifications (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 kind text NOT NULL, resource_id text NOT NULL, read_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user ON notifications(user_id,id DESC);
-- Единственный источник агрегатов: подтверждённые общие и собственные гостевые записи.
CREATE VIEW player_results AS
WITH totals AS (
 SELECT p.*,coalesce((SELECT sum(vp) FROM turning_point_scores s WHERE s.player_id=p.id),0)::int AS vp
 FROM match_players p
)
SELECT p.user_id,p.match_id,m.kind,m.edition,m.played_at,m.mission_id,m.killzone_id,
 p.team_id,op.team_id AS opponent_team_id,op.user_id AS opponent_id,op.display_name AS opponent_name,
 p.vp AS vp_for,op.vp AS vp_against,
 CASE WHEN p.vp>op.vp THEN 'win' WHEN p.vp=op.vp THEN 'draw' ELSE 'loss' END AS result
FROM totals p JOIN totals op ON op.match_id=p.match_id AND op.slot<>p.slot
JOIN matches m ON m.id=p.match_id
WHERE p.user_id IS NOT NULL AND (m.status='confirmed' OR (m.kind='guest' AND m.status='unconfirmed' AND m.created_by=p.user_id));
