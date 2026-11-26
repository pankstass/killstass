-- v1.9: operative tracker, administrators, LAN tournaments. Append-only; existing rows are untouched.
-- Administrators are granted by the server operator only (scripts/admin.sh); no API can change the flag.
ALTER TABLE users ADD COLUMN is_admin boolean NOT NULL DEFAULT false;

-- Operatives of a match (filled from the player's roster at the start or added from datacards).
-- wounds = 0 exactly when the operative is incapacitated; the turning point feeds operative_kills.
CREATE TABLE match_operatives (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 player_id bigint NOT NULL REFERENCES match_players ON DELETE CASCADE,
 position smallint NOT NULL CHECK(position BETWEEN 1 AND 40),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
 card text CHECK(card IS NULL OR length(card) <= 120),
 stats jsonb NOT NULL DEFAULT '{}',
 weapons jsonb NOT NULL DEFAULT '[]',
 wounds_max smallint NOT NULL CHECK(wounds_max BETWEEN 1 AND 99),
 wounds smallint NOT NULL CHECK(wounds BETWEEN 0 AND 99),
 order_token text NOT NULL DEFAULT 'conceal' CHECK(order_token IN ('engage','conceal')),
 activated_tp smallint CHECK(activated_tp BETWEEN 1 AND 12),
 incapacitated_tp smallint CHECK(incapacitated_tp BETWEEN 1 AND 12),
 CHECK(wounds <= wounds_max),
 CHECK((wounds = 0) = (incapacitated_tp IS NOT NULL)),
 CHECK(pg_column_size(stats) + pg_column_size(weapons) <= 16384),
 UNIQUE(player_id, position)
);
CREATE INDEX match_operatives_match ON match_operatives(match_id, player_id, position);

-- LAN tournaments: league (round robin) or Swiss pairing. Players are friends of the organizer or guest names.
CREATE TABLE tournaments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 owner_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
 format text NOT NULL CHECK(format IN ('swiss','league')),
 rounds smallint NOT NULL CHECK(rounds BETWEEN 1 AND 30),
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','finished')),
 current_round smallint NOT NULL DEFAULT 0 CHECK(current_round BETWEEN 0 AND 30),
 version int NOT NULL DEFAULT 1 CHECK(version >= 1),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tournaments_owner ON tournaments(owner_id, created_at DESC);
CREATE TABLE tournament_players (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tournament_id uuid NOT NULL REFERENCES tournaments ON DELETE CASCADE,
 user_id bigint REFERENCES users ON DELETE SET NULL,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 64),
 seed smallint NOT NULL CHECK(seed BETWEEN 1 AND 64),
 dropped boolean NOT NULL DEFAULT false,
 UNIQUE(tournament_id, seed)
);
CREATE UNIQUE INDEX tournament_players_user ON tournament_players(tournament_id, user_id) WHERE user_id IS NOT NULL;
CREATE INDEX tournament_players_member ON tournament_players(user_id) WHERE user_id IS NOT NULL;
-- player2_id NULL = bye. vp1/vp2 entered by hand win over the result of the linked match.
CREATE TABLE tournament_pairings (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tournament_id uuid NOT NULL REFERENCES tournaments ON DELETE CASCADE,
 round smallint NOT NULL CHECK(round BETWEEN 1 AND 30),
 table_no smallint NOT NULL CHECK(table_no BETWEEN 1 AND 32),
 player1_id bigint NOT NULL REFERENCES tournament_players ON DELETE CASCADE,
 player2_id bigint REFERENCES tournament_players ON DELETE CASCADE,
 match_id uuid UNIQUE REFERENCES matches ON DELETE SET NULL,
 vp1 int CHECK(vp1 BETWEEN 0 AND 999),
 vp2 int CHECK(vp2 BETWEEN 0 AND 999),
 reported_by bigint REFERENCES users ON DELETE SET NULL,
 CHECK((vp1 IS NULL) = (vp2 IS NULL)),
 CHECK(player2_id IS NULL OR player2_id <> player1_id),
 UNIQUE(tournament_id, round, table_no)
);
CREATE INDEX tournament_pairings_round ON tournament_pairings(tournament_id, round);
