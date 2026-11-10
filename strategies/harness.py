"""Shared machinery for running and judging strategies.

A strategy is any object with a `name` and an `on_tick(bt)` method. The
harness calls `on_tick` once per interval (default every second of market
time), records the bot's state, and afterwards computes the same metrics and
charts for every strategy, so they can be compared fairly on the same data.
"""

import bisect
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import lobster
from units import NS_PER_SECOND, btc, price_usd, usd

RECORDINGS = Path("data/coinbase/BTC-USD")

# crypto trades around the clock, so a year is 365 full days of minutes
MINUTES_PER_YEAR = 365 * 24 * 60


class Strategy(Protocol):
    name: str

    def on_tick(self, bt: lobster.Backtest) -> None:
        """Look at the market and the bot's orders; send orders or cancels."""


@dataclass
class Result:
    """Everything recorded during one run."""

    name: str
    start_ns: int
    t: list = field(default_factory=list)  # seconds since start
    mid: list = field(default_factory=list)  # ticks
    position: list = field(default_factory=list)  # lots
    pnl: list = field(default_factory=list)  # tick-lots
    fills: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def newest_recording() -> Path:
    files = sorted(RECORDINGS.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no recordings in {RECORDINGS}; run the recorder first")
    return files[-1]


def recording_span_ns(path: Path) -> tuple[int, int]:
    """Our receive times of a recording's first and last lines (cheap: reads two lines)."""
    with open(path, "rb") as f:
        first = json.loads(f.readline())["recv_ns"]
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 1_000_000))  # The last line is well under 1 MB
        last = json.loads(f.read().splitlines()[-1])["recv_ns"]
    return first, last


def has_trades(path: Path) -> bool:
    """Whether a recording includes the market_trades channel (older ones don't).

    Without trades, nothing ever reaches a resting bot order, so the file
    can't be used to evaluate a market maker.
    """
    with open(path) as f:
        for _, line in zip(range(500), f):
            if '"market_trades"' in line:
                return True
    return False


def open_backtest(path: Path, **config) -> lobster.Backtest:
    """Loads a recording, warning about any problems reading it."""
    bt = lobster.Backtest(str(path), **config)
    problems = {k: v for k, v in bt.read_summary().items() if k != "lines" and v}
    if problems:
        print(f"warning: problems reading {path}: {problems}")
    return bt


def run(
    bt: lobster.Backtest,
    strategy: Strategy,
    every_ns: int = NS_PER_SECOND,
    start_ns: int | None = None,
    end_ns: int | None = None,
) -> Result:
    """Runs `strategy` and computes its metrics.

    By default it trades from the start of the recording to the end. With
    `start_ns` / `end_ns` it only trades inside that window: the market is
    replayed up to `start_ns` with no bot, and trading stops at `end_ns`.
    The bot starts flat, so PnL is measured from the window's start.
    """
    if start_ns is not None:
        bt.run_until(start_ns)
    result = Result(name=strategy.name, start_ns=bt.now_ns)
    while not bt.market_finished() and (end_ns is None or bt.now_ns < end_ns):
        bt.run_until(bt.now_ns + every_ns)
        result.fills.extend(bt.take_fills())
        strategy.on_tick(bt)

        mid, pnl = bt.mid(), bt.pnl_at_mid()
        if mid is not None and pnl is not None:
            result.t.append((bt.now_ns - result.start_ns) / NS_PER_SECOND)
            result.mid.append(mid)
            result.position.append(bt.position)
            result.pnl.append(pnl)
    result.fills.extend(bt.take_fills())
    result.metrics = metrics(bt, result)
    return result


# ---- Metrics ----


def _mid_at(result: Result, seconds: float, after: bool) -> int | None:
    """The recorded mid at (or just after / just before) `seconds`."""
    if after:
        i = bisect.bisect_left(result.t, seconds)
        return result.mid[i] if i < len(result.t) else None
    i = bisect.bisect_right(result.t, seconds) - 1
    return result.mid[i] if i >= 0 else None


def markouts(result: Result, horizon_s: float) -> list[int]:
    """For each fill, how far the mid moved in our favor `horizon_s` later, in ticks.

    Positive: a good fill (we bought and the price rose, or sold and it fell).
    Negative: adverse selection, the price moved against us right after.
    """
    out = []
    for fill in result.fills:
        seconds = (fill.time_ns - result.start_ns) / NS_PER_SECOND
        later = _mid_at(result, seconds + horizon_s, after=True)
        if later is not None:
            move = later - fill.price
            out.append(move if fill.side == "buy" else -move)
    return out


def spread_capture(result: Result) -> int:
    """Money made at the moment of each fill versus the mid, in tick-lots.

    Buying below the mid or selling above it earns this. Total PnL is this
    plus (or minus) what the inventory did afterwards.
    """
    total = 0
    for fill in result.fills:
        seconds = (fill.time_ns - result.start_ns) / NS_PER_SECOND
        mid = _mid_at(result, seconds, after=False)
        if mid is None:
            continue
        edge = mid - fill.price if fill.side == "buy" else fill.price - mid
        total += edge * fill.quantity
    return total


def max_drawdown(pnl: list[int]) -> int:
    """The biggest drop from a previous high, in tick-lots (zero or negative)."""
    peak, worst = 0, 0
    for value in pnl:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def sharpe(pnl: list[int], t: list[float]) -> float:
    """Annualized Sharpe ratio from PnL changes over each minute.

    Sharpe = average return / standard deviation of returns, scaled to a year
    (x sqrt(minutes per year)). With only an hour or so of data it's a rough
    guide, not a precise number.
    """
    per_minute = []
    next_minute, last = 60.0, 0
    for seconds, value in zip(t, pnl):
        if seconds >= next_minute:
            per_minute.append(value - last)
            last, next_minute = value, next_minute + 60.0
    if len(per_minute) < 2:
        return 0.0
    mean = sum(per_minute) / len(per_minute)
    var = sum((x - mean) ** 2 for x in per_minute) / (len(per_minute) - 1)
    return mean / math.sqrt(var) * math.sqrt(MINUTES_PER_YEAR) if var else 0.0


def metrics(bt: lobster.Backtest, result: Result) -> dict:
    fills = result.fills
    pnl = bt.pnl_at_mid() or 0
    capture = spread_capture(result)
    minutes = (result.t[-1] / 60) if result.t else 0.0
    m = {
        "minutes": minutes,
        "fills": len(fills),
        "maker_fills": sum(f.maker for f in fills),
        "volume_btc": btc(sum(f.quantity for f in fills)),
        "end_position_btc": btc(bt.position),
        "max_abs_position_btc": btc(max((abs(p) for p in result.position), default=0)),
        "fees_usd": usd(bt.fees_paid),
        "spread_capture_usd": usd(capture),
        "inventory_pnl_usd": usd(pnl + bt.fees_paid - capture),
        "pnl_usd": usd(pnl),
        "max_drawdown_usd": usd(max_drawdown(result.pnl)),
        "pnl_per_hour_usd": usd(pnl) / (minutes / 60) if minutes else 0.0,
        "sharpe": sharpe(result.pnl, result.t),
        "rejections": bt.rejections,
    }
    for horizon in (1, 5, 30):
        moves = markouts(result, horizon)
        m[f"markout_{horizon}s_ticks"] = sum(moves) / len(moves) if moves else 0.0
        m[f"adverse_{horizon}s_share"] = sum(x < 0 for x in moves) / len(moves) if moves else 0.0
    return m


def print_summary(result: Result) -> None:
    m = result.metrics
    print(f"{result.name}  ({m['minutes']:.1f} minutes)")
    print(f"  fills:          {m['fills']} ({m['maker_fills']} maker), {m['volume_btc']:.4f} BTC traded")
    print(
        f"  position:       ends {m['end_position_btc']:+.5f} BTC, "
        f"largest {m['max_abs_position_btc']:.5f} BTC"
    )
    print(
        f"  PnL:            ${m['pnl_usd']:,.2f} = spread ${m['spread_capture_usd']:,.2f}"
        f" + inventory ${m['inventory_pnl_usd']:,.2f} - fees ${m['fees_usd']:,.2f}"
    )
    print(f"  max drawdown:   ${m['max_drawdown_usd']:,.2f}")
    print(f"  per hour:       ${m['pnl_per_hour_usd']:,.2f}, Sharpe {m['sharpe']:+.1f} (annualized)")
    print(f"  rejected:       {m['rejections']} (cancels that lost the race to a fill)")
    for horizon in (1, 5, 30):
        print(
            f"  markout {horizon:>2}s:    {m[f'markout_{horizon}s_ticks']:+.2f} ticks per fill, "
            f"{m[f'adverse_{horizon}s_share']:.0%} moved against us"
        )


def print_table(results: list[Result]) -> None:
    """One row per strategy, for side-by-side comparison."""
    columns = [
        ("fills", "fills", "{:d}"),
        ("end pos BTC", "end_position_btc", "{:+.4f}"),
        ("max |pos|", "max_abs_position_btc", "{:.4f}"),
        ("spread $", "spread_capture_usd", "{:,.2f}"),
        ("inventory $", "inventory_pnl_usd", "{:,.2f}"),
        ("fees $", "fees_usd", "{:,.2f}"),
        ("PnL $", "pnl_usd", "{:,.2f}"),
        ("drawdown $", "max_drawdown_usd", "{:,.2f}"),
        ("Sharpe", "sharpe", "{:+.1f}"),
        ("markout 5s", "markout_5s_ticks", "{:+.2f}"),
    ]
    width = max(len(r.name) for r in results)
    header = f"{'strategy':<{width}}  " + "  ".join(f"{title:>11}" for title, _, _ in columns)
    print(header)
    print("-" * len(header))
    for r in results:
        cells = "  ".join(f"{fmt.format(r.metrics[key]):>11}" for _, key, fmt in columns)
        print(f"{r.name:<{width}}  {cells}")


# ---- Charts ----


def plot(results: list[Result], out: Path, title: str) -> None:
    """Price, position and PnL over time; one line per strategy."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(install matplotlib for a chart: uv pip install matplotlib)")
        return

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    first = results[0]
    axes[0].plot(first.t, [price_usd(m) for m in first.mid], color="tab:blue")
    axes[0].set_ylabel("BTC mid ($)")
    for r in results:
        axes[1].plot(r.t, [btc(p) for p in r.position], label=r.name)
        axes[2].plot(r.t, [usd(p) for p in r.pnl], label=r.name)
    for ax in axes[1:]:
        ax.axhline(0, color="gray", linewidth=0.5)
    axes[1].set_ylabel("position (BTC)")
    axes[2].set_ylabel("PnL ($)")
    axes[2].set_xlabel("seconds")
    if len(results) > 1:
        axes[2].legend(loc="best", fontsize="small")
    fig.suptitle(title)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"chart: {out}")
