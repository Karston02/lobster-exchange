"""One dashboard replay: a backtest plus a strategy, advanced one tick at a time.

Kept separate from the web server (app.py) so the replay logic can be used
and tested without any networking.
"""

import sys
from pathlib import Path

# The strategies and their harness live in strategies/ at the repo root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "strategies"))

import harness  # noqa: E402
from strats import AvellanedaStoikov, ImbalanceFilter, InventorySkew, KeepPlace, Naive  # noqa: E402
from units import NS_PER_SECOND, lots, usd  # noqa: E402

RECORDINGS = ROOT / harness.RECORDINGS

# key: (name, description, builder(size in lots) -> strategy)
STRATEGIES = {
    "v1": ("v1 naive", "Re-join the best bid and ask every second", lambda size: Naive(size)),
    "v1b": ("v1b keep place", "Same quotes, but keep orders that are already right", lambda size: KeepPlace(size)),
    "v2": (
        "v2 inventory skew",
        "Lean quotes against the position; cap it at 0.01 BTC",
        lambda size: InventorySkew(size, lots(0.01), 1),
    ),
    "v3": (
        "v3 imbalance filter",
        "v2, plus skip the side the order book imbalance says will get run over",
        lambda size: ImbalanceFilter(size, lots(0.01), 1, 0.6),
    ),
    "v4": (
        "v4 avellaneda-stoikov",
        "Reservation price and volatility-based spread",
        lambda size: AvellanedaStoikov(size, lots(0.01)),
    ),
}


def list_recordings() -> list[dict]:
    """Every recording, newest first, with its length and whether it has trades."""
    out = []
    for path in sorted(RECORDINGS.glob("*.jsonl"), reverse=True):
        first, last = harness.recording_span_ns(path)
        out.append(
            {
                "name": path.name,
                "minutes": round((last - first) / NS_PER_SECOND / 60, 1),
                "has_trades": harness.has_trades(path),
            }
        )
    return out


def recording_path(name: str) -> Path:
    """Turns a recording's file name into its path, refusing anything outside RECORDINGS."""
    path = (RECORDINGS / name).resolve()
    if path.parent != RECORDINGS.resolve() or path.suffix != ".jsonl" or not path.exists():
        raise ValueError(f"unknown recording {name!r}")
    return path


class Session:
    def __init__(
        self,
        recording: str,
        strategy: str = "v2",
        size_btc: float = 0.001,
        latency_ms: float = 10,
        maker_fee_bps: int = 0,
        taker_fee_bps: int = 0,
        depth: int = 12,
    ):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        self.path = recording_path(recording)
        self.name, _, build = STRATEGIES[strategy]
        self.strategy = build(lots(size_btc))
        self.bt = harness.open_backtest(
            self.path,
            latency_ms=latency_ms,
            maker_fee_bps=maker_fee_bps,
            taker_fee_bps=taker_fee_bps,
        )
        self.depth = depth
        self.start_ns = self.bt.now_ns
        first, last = harness.recording_span_ns(self.path)
        self.duration_s = (last - first) / NS_PER_SECOND

    def seconds(self, time_ns: int) -> float:
        """Seconds since the replay started. Sent instead of raw nanoseconds,
        which are too big for JavaScript numbers to hold exactly."""
        return (time_ns - self.start_ns) / NS_PER_SECOND

    def hello(self) -> dict:
        return {
            "type": "hello",
            "recording": self.path.name,
            "strategy": self.name,
            "duration_s": self.duration_s,
        }

    def tick(self, every_ns: int = NS_PER_SECOND) -> dict | None:
        """Advances the market by `every_ns`, lets the strategy act, and
        returns what the dashboard should show. None when the recording ends."""
        if self.bt.market_finished():
            return None
        self.bt.run_until(self.bt.now_ns + every_ns)
        fills = self.bt.take_fills()
        self.strategy.on_tick(self.bt)
        return self.snapshot(fills)

    def snapshot(self, fills) -> dict:
        bt = self.bt
        pnl = bt.pnl_at_mid()
        return {
            "type": "tick",
            "t": self.seconds(bt.now_ns),
            "mid": bt.mid(),
            "bids": bt.top("buy", self.depth),
            "asks": bt.top("sell", self.depth),
            "orders": [
                {
                    # Bot ids start at 2^62, past what a JavaScript number holds exactly
                    "id": str(order.id),
                    "side": order.side,
                    "price": order.price,
                    "quantity": order.quantity,
                    "ahead": bt.queue_ahead(order.id),
                }
                for order in bt.open_orders()
            ],
            "fills": [
                {
                    "t": self.seconds(fill.time_ns),
                    "side": fill.side,
                    "price": fill.price,
                    "quantity": fill.quantity,
                    "maker": fill.maker,
                    "fee_usd": usd(fill.fee),
                }
                for fill in fills
            ],
            "position": bt.position,
            "pnl_usd": usd(pnl) if pnl is not None else None,
            "fees_usd": usd(bt.fees_paid),
            "fill_count": bt.fill_count,
            "rejections": bt.rejections,
        }

    def done(self) -> dict:
        pnl = self.bt.pnl_at_mid()
        return {
            "type": "done",
            "pnl_usd": usd(pnl) if pnl is not None else None,
            "fees_usd": usd(self.bt.fees_paid),
            "fill_count": self.bt.fill_count,
            "position": self.bt.position,
        }
