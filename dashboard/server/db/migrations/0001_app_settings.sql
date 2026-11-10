-- Settings changed from the app (e.g. the settings panel), one row per key.
-- Values are JSON text so one table holds numbers, flags and lists.
-- Paths, keys and addresses are NOT here: those live in .env (config/settings.py).
CREATE TABLE app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
