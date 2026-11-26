-- v1.5: read-only result links and local feedback. Append-only.
-- One link per match; only a SHA-256 of the token is stored, so a lost link is replaced, never shown again.
CREATE TABLE match_shares (
 token_hash text PRIMARY KEY CHECK(length(token_hash)=64),
 match_id uuid NOT NULL UNIQUE REFERENCES matches ON DELETE CASCADE,
 created_by bigint REFERENCES users ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- Feedback goes to the LAN operator only (scripts/feedback.sh). Deleting the account deletes its messages.
CREATE TABLE feedback (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 page text NOT NULL DEFAULT '' CHECK(length(page)<=200),
 message text NOT NULL CHECK(length(message) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT now(),
 handled_at timestamptz
);
CREATE INDEX feedback_open ON feedback(created_at) WHERE handled_at IS NULL;
