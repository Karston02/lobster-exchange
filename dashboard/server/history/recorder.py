"""Records the portfolio's value every minute, from the live feed's latest numbers.

It only records numbers that are fresh: the feed reloads accounts from Schwab
every minute and publishes right after, so if its latest message is more than
three minutes old, Schwab is unreachable and nothing is written (a gap in the
chart is more honest than a flat line of stale values).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from db import connect

from .store import record_values

log = logging.getLogger("lobster.history")

MAX_AGE_S = 180


class HistoryRecorder:
    def __init__(self, feed: Any, db_path: Path, clock: Callable[[], float] = time.time):
        self._feed = feed  # anything with .latest() -> the live message dict, or None
        self._db_path = db_path
        self._clock = clock
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            now = self._clock()
            await asyncio.sleep(60 - now % 60 + 1)  # a second after each minute starts
            try:
                self.record_once()
            except Exception:
                log.exception("couldn't record portfolio value")

    def record_once(self) -> bool:
        """Writes this minute's values. False if there was nothing fresh to write."""
        latest = self._feed.latest()
        now = self._clock()
        if not latest or now - datetime.fromisoformat(latest["as_of"]).timestamp() > MAX_AGE_S:
            return False
        totals = {"all": latest["portfolio"]["total_value_cents"]}
        for account in latest["accounts"]:
            totals[account["last4"].lstrip("…")] = account["total_value_cents"]
        conn = connect(self._db_path)
        try:
            record_values(conn, int(now // 60 * 60), totals)
        finally:
            conn.close()
        return True
