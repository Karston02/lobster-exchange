-- Text drawings carry their words; any drawing can be locked against moving and deleting.
-- (Existing rows get the defaults: no text, unlocked.)
ALTER TABLE drawings ADD COLUMN text TEXT NOT NULL DEFAULT '';
ALTER TABLE drawings ADD COLUMN locked INTEGER NOT NULL DEFAULT 0;  -- SQLite has no boolean: 0 or 1
