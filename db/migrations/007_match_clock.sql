-- v1.4: game clock. Append-only event log; elapsed time is always derived from server timestamps.
CREATE TABLE match_clock_events (
 id bigserial PRIMARY KEY,
 match_id uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
 action text NOT NULL CHECK(action IN ('configure','start','pause','switch')),
 mode text CHECK(mode IN ('stopwatch','chess','countdown')),
 limit_seconds int CHECK(limit_seconds BETWEEN 60 AND 36000),
 slot smallint CHECK(slot IN (1,2)),
 actor_id bigint REFERENCES users ON DELETE SET NULL,
 server_ts timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(action<>'configure' OR mode IS NOT NULL),
 CHECK(mode<>'countdown' OR action<>'configure' OR limit_seconds IS NOT NULL)
);
CREATE INDEX match_clock_events_match ON match_clock_events(match_id,id);
