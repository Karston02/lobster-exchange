-- The portfolio's value over time, recorded by the server every minute
-- (Schwab keeps no such history). One row per account per minute, plus 'all'.
CREATE TABLE value_history (
    account     TEXT NOT NULL,     -- 'all' (the whole portfolio) or an account's last four digits
    time        INTEGER NOT NULL,  -- Unix seconds, on the minute
    total_cents INTEGER NOT NULL,
    PRIMARY KEY (account, time)
) WITHOUT ROWID;  -- the key is the table: rows are stored in (account, time) order
