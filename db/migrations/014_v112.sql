-- v1.12: ready-made killzone terrain for the killzone sketch (web/killzones.js, api/boards.py LAYOUTS).
-- Additive: two columns on boards; existing tables, columns and data are not changed (v1.11 ignores them).
ALTER TABLE boards ADD COLUMN layout text CHECK(layout ~ '^[a-z0-9-]{1,40}$');
ALTER TABLE boards ADD COLUMN layout_swap boolean NOT NULL DEFAULT false;
