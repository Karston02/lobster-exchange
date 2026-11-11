-- Chart drawings, one row each, per symbol (shared by every timeframe).
-- Points are anchored to (time, price), not pixels, so a drawing stays put
-- when the chart scrolls, zooms or changes timeframe.
CREATE TABLE drawings (
    id         TEXT PRIMARY KEY,  -- made by the page (a UUID), so it can draw before saving
    symbol     TEXT NOT NULL,
    kind       TEXT NOT NULL,     -- hline, trend (more in step 2e)
    points     TEXT NOT NULL,     -- JSON: [{"time": unix seconds, "price": dollars}, ...]
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX drawings_by_symbol ON drawings (symbol);
