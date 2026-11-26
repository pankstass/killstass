-- v1.10: password reset codes, player profiles and avatars, Elo seasons and achievements, game nights,
-- TV screens, killzone boards and Web Push. Append-only: existing tables and columns are not changed.
-- db/migrate.sh grants the runtime role DML on every table after the versioned migrations.

-- One-time password reset codes issued by an administrator (#admin) or the operator (scripts/admin.sh).
CREATE TABLE password_resets (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 code_hash text NOT NULL,
 created_by bigint REFERENCES users ON DELETE SET NULL, -- NULL: scripts/admin.sh password LOGIN
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 used_at timestamptz,
 attempts smallint NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 100)
);
CREATE UNIQUE INDEX password_resets_open ON password_resets(user_id) WHERE used_at IS NULL;

-- Player page: optional motto, favourite team, privacy flag; avatar images (PNG/JPEG/WebP, re-encoded by the browser).
CREATE TABLE user_profiles (
 user_id bigint PRIMARY KEY REFERENCES users ON DELETE CASCADE,
 motto varchar(140) NOT NULL DEFAULT '',
 favorite_team_id bigint REFERENCES catalogs ON DELETE SET NULL,
 hidden boolean NOT NULL DEFAULT false, -- hidden from season tables, TV screens and non-friends
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE avatars (
 user_id bigint PRIMARY KEY REFERENCES users ON DELETE CASCADE,
 mime text NOT NULL CHECK(mime IN ('image/png','image/jpeg','image/webp')),
 data bytea NOT NULL CHECK(octet_length(data) BETWEEN 64 AND 196608),
 sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 updated_at timestamptz NOT NULL DEFAULT now()
);

-- Elo seasons (administrator). Ratings are recomputed from confirmed matches inside [starts_on, ends_on].
CREATE TABLE seasons (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 60),
 starts_on date NOT NULL,
 ends_on date NOT NULL CHECK(ends_on >= starts_on),
 k_factor smallint NOT NULL DEFAULT 24 CHECK(k_factor BETWEEN 4 AND 64),
 start_rating smallint NOT NULL DEFAULT 1500 CHECK(start_rating BETWEEN 100 AND 3000),
 created_by bigint, -- users.id of the administrator; no foreign key: seasons and achievements outlive accounts
 created_at timestamptz NOT NULL DEFAULT now()
);

-- Achievements: built-in rules with an administrator-chosen threshold, optionally limited to one season.
CREATE TABLE achievements (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 code text UNIQUE NOT NULL CHECK(code ~ '^[a-z0-9_]{2,40}$'),
 title_ru text NOT NULL CHECK(length(title_ru) BETWEEN 1 AND 60),
 title_en text NOT NULL DEFAULT '' CHECK(length(title_en) <= 60),
 description_ru text NOT NULL DEFAULT '' CHECK(length(description_ru) <= 200),
 description_en text NOT NULL DEFAULT '' CHECK(length(description_en) <= 200),
 icon text NOT NULL DEFAULT 'star' CHECK(icon ~ '^[a-z-]{2,20}$'),
 rule text NOT NULL CHECK(rule IN ('matches','wins','win_streak','comeback','big_win','opponents','teams','tournament_wins','nights')),
 threshold int NOT NULL DEFAULT 1 CHECK(threshold BETWEEN 1 AND 1000),
 season_id bigint REFERENCES seasons ON DELETE RESTRICT, -- a season with achievements cannot be deleted
 active boolean NOT NULL DEFAULT true,
 builtin boolean NOT NULL DEFAULT false,
 position int NOT NULL DEFAULT 100 CHECK(position BETWEEN 0 AND 10000),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE user_achievements (
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 achievement_id bigint NOT NULL REFERENCES achievements ON DELETE CASCADE,
 earned_at timestamptz NOT NULL DEFAULT now(),
 match_id uuid REFERENCES matches ON DELETE SET NULL,
 PRIMARY KEY(user_id, achievement_id)
);
CREATE INDEX user_achievements_achievement ON user_achievements(achievement_id);
INSERT INTO achievements(code,title_ru,title_en,description_ru,description_en,icon,rule,threshold,builtin,position) VALUES
 ('first_win','Первая победа','First win','Выиграйте первый подтверждённый матч.','Win your first confirmed match.','trophy','wins',1,true,10),
 ('matches_10','10 матчей','10 matches','Сыграйте 10 подтверждённых матчей.','Play 10 confirmed matches.','flag','matches',10,true,20),
 ('comeback','Камбэк','Comeback','Победите, уступая после одного из поворотов на 3 ПО или больше.','Win after trailing by 3 VP or more at the end of a turning point.','bolt','comeback',3,true,30);

-- Game nights: date, who comes and with which team, pairs per table, calendar export.
CREATE TABLE game_nights (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 organizer_id bigint REFERENCES users ON DELETE SET NULL,
 title text NOT NULL CHECK(length(title) BETWEEN 1 AND 80),
 starts_at timestamptz NOT NULL,
 ends_at timestamptz NOT NULL CHECK(ends_at > starts_at),
 place text NOT NULL DEFAULT '' CHECK(length(place) <= 120),
 notes text NOT NULL DEFAULT '' CHECK(length(notes) <= 1000),
 capacity smallint CHECK(capacity BETWEEN 2 AND 64),
 status text NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','cancelled')),
 pairs_published_at timestamptz,
 version int NOT NULL DEFAULT 1 CHECK(version >= 1),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX game_nights_start ON game_nights(starts_at);
CREATE TABLE game_night_rsvps (
 night_id uuid NOT NULL REFERENCES game_nights ON DELETE CASCADE,
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 answer text NOT NULL CHECK(answer IN ('yes','maybe','no')),
 team_id bigint REFERENCES catalogs ON DELETE SET NULL,
 comment varchar(140) NOT NULL DEFAULT '',
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(night_id, user_id)
);
CREATE INDEX game_night_rsvps_user ON game_night_rsvps(user_id);
CREATE TABLE game_night_pairs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 night_id uuid NOT NULL REFERENCES game_nights ON DELETE CASCADE,
 table_no smallint NOT NULL CHECK(table_no BETWEEN 1 AND 64),
 a_id bigint REFERENCES users ON DELETE SET NULL,
 b_id bigint REFERENCES users ON DELETE SET NULL, -- NULL: bye
 match_id uuid REFERENCES matches ON DELETE SET NULL,
 UNIQUE(night_id, table_no)
);
-- Personal calendar subscription (webcal/https feed); only the hash is stored, the link is shown once.
CREATE TABLE calendar_tokens (
 user_id bigint PRIMARY KEY REFERENCES users ON DELETE CASCADE,
 token_hash text UNIQUE NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);

-- TV screens: read-only key in the link (#tv/<key>), created and revoked by an administrator.
CREATE TABLE tv_screens (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 label text NOT NULL CHECK(length(label) BETWEEN 1 AND 60),
 key text UNIQUE NOT NULL CHECK(key ~ '^[A-Za-z0-9_-]{24,64}$'),
 tournament_id uuid REFERENCES tournaments ON DELETE SET NULL, -- NULL: every active tournament
 created_by bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz
);

-- Killzone boards for match review: one per match (players edit) or a private free board.
-- Frame 0 is deployment, frame n is the end of turning point n; state is a JSON document in inches.
CREATE TABLE boards (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 owner_id bigint REFERENCES users ON DELETE CASCADE,
 match_id uuid UNIQUE REFERENCES matches ON DELETE CASCADE,
 title text NOT NULL DEFAULT '' CHECK(length(title) <= 80),
 width numeric(4,1) NOT NULL DEFAULT 30 CHECK(width BETWEEN 6 AND 60),
 height numeric(4,1) NOT NULL DEFAULT 22 CHECK(height BETWEEN 6 AND 60),
 seq bigint NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(owner_id IS NOT NULL OR match_id IS NOT NULL)
);
CREATE INDEX boards_owner ON boards(owner_id, updated_at DESC);
CREATE TABLE board_frames (
 board_id uuid NOT NULL REFERENCES boards ON DELETE CASCADE,
 frame smallint NOT NULL CHECK(frame BETWEEN 0 AND 12),
 state jsonb NOT NULL DEFAULT '{}',
 note varchar(500) NOT NULL DEFAULT '',
 version int NOT NULL DEFAULT 1 CHECK(version >= 1),
 updated_by bigint REFERENCES users ON DELETE SET NULL,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(board_id, frame)
);

-- Web Push (optional, PUSH_ENABLED=1 and the pushworker service with internet access).
CREATE TABLE push_subscriptions (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 endpoint text UNIQUE NOT NULL CHECK(endpoint ~ '^https://' AND length(endpoint) <= 1000),
 p256dh text NOT NULL CHECK(length(p256dh) BETWEEN 40 AND 200),
 auth text NOT NULL CHECK(length(auth) BETWEEN 8 AND 64),
 lang text NOT NULL DEFAULT 'ru' CHECK(lang IN ('ru','en')),
 created_at timestamptz NOT NULL DEFAULT now(),
 last_ok_at timestamptz,
 failures smallint NOT NULL DEFAULT 0 CHECK(failures BETWEEN 0 AND 1000)
);
CREATE INDEX push_subscriptions_user ON push_subscriptions(user_id);
CREATE TABLE push_outbox (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 kind text NOT NULL,
 resource_id text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- Instance settings written by the application (VAPID key pair).
CREATE TABLE app_settings (
 key text PRIMARY KEY CHECK(key ~ '^[a-z0-9_.]{1,64}$'),
 value jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
