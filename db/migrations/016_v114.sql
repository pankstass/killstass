-- v1.14: the equipment a player selects in secret before the battle (revealed to the opponent when the match
-- starts), the command points of the game sequence (one record per granted step), ploys used on the board
-- (the match protocol) and the browser error log for #admin.
-- Additive: one column and new tables; v1.13 ignores all of it (a rollback of the code keeps working).
-- Up to four options, each a server-built copy {key,name,group,rules,weapons}: the match keeps what was played.
ALTER TABLE match_players ADD COLUMN equipment jsonb NOT NULL DEFAULT '[]'
 CHECK(jsonb_typeof(equipment)='array' AND jsonb_array_length(equipment)<=4);
-- Turning point 0: the 2CP after the equipment reveal (the start); 1-12: the Ready step of that turning point.
-- The primary key makes a grant happen once; gains = CP per slot, e.g. {"1": 1, "2": 2}.
CREATE TABLE match_cp_grants (
 match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 turning_point int NOT NULL CHECK(turning_point BETWEEN 0 AND 12),
 gains jsonb NOT NULL DEFAULT '{}',
 granted_by bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(match_id,turning_point)
);
CREATE TABLE match_ploys (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 player_id bigint NOT NULL REFERENCES match_players ON DELETE CASCADE,
 turning_point int NOT NULL CHECK(turning_point BETWEEN 1 AND 12),
 kind varchar(12) NOT NULL CHECK(kind IN ('strategy','firefight')),
 name varchar(120) NOT NULL CHECK(btrim(name) <> ''),
 cost smallint NOT NULL CHECK(cost BETWEEN 0 AND 9),
 used_by bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX match_ploys_match ON match_ploys(match_id,turning_point,id);
CREATE INDEX match_ploys_player ON match_ploys(player_id);
-- Unhandled browser errors: one row per fingerprint and day (repeats only raise count), kept 30 days.
-- No form data, no URLs with parameters: the page is the route name (#match, #rosters…).
CREATE TABLE client_errors (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 day date NOT NULL DEFAULT current_date,
 fingerprint char(64) NOT NULL,
 kind varchar(16) NOT NULL CHECK(kind IN ('error','rejection')),
 message varchar(500) NOT NULL,
 source varchar(200) NOT NULL DEFAULT '',
 stack varchar(2000) NOT NULL DEFAULT '',
 page varchar(40) NOT NULL DEFAULT '',
 version varchar(20) NOT NULL DEFAULT '',
 agent varchar(160) NOT NULL DEFAULT '',
 user_id bigint REFERENCES users ON DELETE SET NULL,
 count int NOT NULL DEFAULT 1 CHECK(count >= 1),
 first_at timestamptz NOT NULL DEFAULT now(),
 last_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(fingerprint,day)
);
CREATE INDEX client_errors_last ON client_errors(last_at DESC);
