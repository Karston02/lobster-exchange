"""Records Schwab's live market data streams to disk, exactly as received.

The stock counterpart of `lobster-recorder` (which records Coinbase). Run
during US market hours, from the repo root, with the venv active:

    uv pip install schwab-py
    python connectors/schwab/record.py AAPL SPY
    python connectors/schwab/record.py AAPL --no-book      # quotes and bars only

Each connection writes a new file, `<data dir>/schwab/<start ns>.jsonl` (the data
dir is the LOBSTER_DATA_DIR setting, `data/` by default). Every line
is `{"recv_ns": <our receive time>, "service": "...", "msg": <the message>}`.
Stop with Ctrl+C.

Streams recorded:
- LEVELONE_EQUITIES: best bid/ask, sizes, last trade price/size, volume
- NASDAQ_BOOK / NYSE_BOOK: order book snapshots (schwab-py's docs call these
  "largely reverse engineered", so inspect them with inspect_recording.py
  before trusting the field names)
- CHART_EQUITY: one-minute bars (open, high, low, close, volume)

Note: schwab-py converts Schwab's numeric field keys into names (e.g. "1"
becomes "BID_PRICE") before we see a message, so files hold that version.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from schwab.streaming import StreamClient

from connect import async_client, first_account_number, get_settings

MIN_BACKOFF_S = 1
MAX_BACKOFF_S = 60
FLUSH_EVERY_S = 1.0
PROGRESS_EVERY = 5_000


class Writer:
    """Appends one JSON line per message to a file, flushing about once a second."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.file = open(path, "w")
        self.count = 0
        self.by_service: dict[str, int] = {}
        self.last_flush = time.monotonic()

    def handler(self, service: str):
        """A schwab-py handler that records messages under `service`."""

        def handle(message) -> None:
            line = {"recv_ns": time.time_ns(), "service": service, "msg": message}
            self.file.write(json.dumps(line, separators=(",", ":")) + "\n")
            self.count += 1
            self.by_service[service] = self.by_service.get(service, 0) + 1
            if time.monotonic() - self.last_flush >= FLUSH_EVERY_S:
                self.file.flush()
                self.last_flush = time.monotonic()
            if self.count % PROGRESS_EVERY == 0:
                print(f"{self.count} messages recorded {self.by_service}")

        return handle

    def close(self) -> None:
        self.file.close()
        print(f"wrote {self.count} messages to {self.path} {self.by_service}")


async def record_session(client, account_id: int, symbols: list[str], book: bool, out_dir: Path) -> None:
    """One connection: subscribe, then record until it drops (raises) or is cancelled."""
    stream = StreamClient(client, account_id=account_id)
    await stream.login()

    writer = Writer(out_dir / f"{time.time_ns()}.jsonl")
    print(f"connected; recording {', '.join(symbols)} to {writer.path}")
    try:
        # Handlers first: schwab-py drops messages for services without one
        stream.add_level_one_equity_handler(writer.handler("LEVELONE_EQUITIES"))
        stream.add_chart_equity_handler(writer.handler("CHART_EQUITY"))
        if book:
            stream.add_nasdaq_book_handler(writer.handler("NASDAQ_BOOK"))
            stream.add_nyse_book_handler(writer.handler("NYSE_BOOK"))

        # Subscriptions one at a time (the docs say they aren't safe to run concurrently)
        await stream.level_one_equity_subs(symbols)
        await stream.chart_equity_subs(symbols)
        if book:
            await stream.nasdaq_book_subs(symbols)
            await stream.nyse_book_subs(symbols)

        while True:
            await stream.handle_message()
    finally:
        writer.close()
        try:
            await stream.logout()
        except Exception:
            pass  # The connection may already be gone


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+", help="e.g. AAPL SPY")
    parser.add_argument("--no-book", action="store_true", help="skip the order book streams")
    parser.add_argument("--out", type=Path, default=get_settings().data_dir / "schwab")
    args = parser.parse_args()
    symbols = [s.upper() for s in args.symbols]

    client = async_client()
    account_id = await first_account_number(client)

    backoff = MIN_BACKOFF_S
    while True:
        started = time.monotonic()
        try:
            await record_session(client, account_id, symbols, not args.no_book, args.out)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # Dropped connections, auth hiccups, ...
            print(f"session ended ({type(error).__name__}: {error})")
        if time.monotonic() - started > 60:
            backoff = MIN_BACKOFF_S  # It was a healthy session; start the backoff over
        print(f"reconnecting in {backoff} s")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped")
