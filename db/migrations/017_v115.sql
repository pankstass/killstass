-- v1.15: distinguish a recorded final result from a match played on the board.
-- Additive: v1.14 ignores this column; score rows and match status remain compatible.
ALTER TABLE matches ADD COLUMN recorded_result boolean NOT NULL DEFAULT false;
