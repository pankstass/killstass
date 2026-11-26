-- v1.3: who had the initiative in each turning point. Append-only; matches.initiative stays the setup value.
CREATE TABLE turning_point_initiative (
 match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 turning_point int NOT NULL CHECK(turning_point BETWEEN 1 AND 12),
 slot smallint NOT NULL CHECK(slot IN (1,2)),
 decided_by bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(match_id,turning_point)
);
