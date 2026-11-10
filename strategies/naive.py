"""Strategy v1: the simplest possible market maker. Expected to lose money.

Every second: cancel whatever is resting, then quote one bid at Coinbase's best
bid and one ask at the best ask. If both fill, we earn the spread. The point of
this strategy is to measure *why* that doesn't happen often enough.

Run from the repo root, with the venv active:

    python strategies/naive.py                       # newest recording
    python strategies/naive.py data/coinbase/BTC-USD/<file>.jsonl --maker-fee-bps 40

Prints a summary, and saves a chart to strategies/output/naive.png if
matplotlib is installed (uv pip install matplotlib).
"""

import argparse
import bisect
from pathlib import Path

import lobster
from units import NS_PER_SECOND, btc, lots, price_usd, usd

RECORDINGS = Path("data/coinbase/BTC-USD")


def newest_recording() -> Path:
    files = sorted(RECORDINGS.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no recordings in {RECORDINGS}; run the recorder first")
    return files[-1]


def run(bt: lobster.Backtest, size: int, every_ns: int) -> dict:
    """The strategy loop. Returns time series and every fill, for analysis."""
    start = bt.now_ns
    series = {"t": [], "mid": [], "position": [], "pnl": []}
    fills = []

    while not bt.market_finished():
        bt.run_until(bt.now_ns + every_ns)
        fills.extend(bt.take_fills())

        # Requote: cancel what's resting, join the best bid and ask
        for order in bt.open_orders():
            bt.cancel(order.id)
        bid, ask = bt.best_bid(), bt.best_ask()
        if bid and ask:
            bt.submit_limit("buy", bid[0], size)
            bt.submit_limit("sell", ask[0], size)

        mid, pnl = bt.mid(), bt.pnl_at_mid()
        if mid is not None and pnl is not None:
            series["t"].append((bt.now_ns - start) / NS_PER_SECOND)
            series["mid"].append(mid)
            series["position"].append(bt.position)
            series["pnl"].append(pnl)

    fills.extend(bt.take_fills())
    return {"series": series, "fills": fills, "start": start}


def markouts(fills, series, start: int, horizon_s: float) -> list[float]:
    """For each fill, how far the mid moved in our favor `horizon_s` later, in ticks.

    Positive: the fill was good (we bought and the price rose, or sold and it
    fell). Negative: adverse selection, the price moved against us right after
    we traded, because the other side knew something we didn't.
    """
    times, mids = series["t"], series["mid"]
    out = []
    for fill in fills:
        later = (fill.time_ns - start) / NS_PER_SECOND + horizon_s
        i = bisect.bisect_left(times, later)
        if i >= len(times):
            continue  # Not enough data after this fill
        move = mids[i] - fill.price
        out.append(move if fill.side == "buy" else -move)
    return out


def max_drawdown(pnl: list[int]) -> int:
    """The biggest drop from a previous high, in tick-lots."""
    peak, worst = 0, 0
    for value in pnl:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def summarize(bt: lobster.Backtest, result: dict, path: Path) -> None:
    series, fills = result["series"], result["fills"]
    duration = series["t"][-1] if series["t"] else 0
    makers = sum(f.maker for f in fills)
    volume = sum(f.quantity for f in fills)
    buys = sum(f.quantity for f in fills if f.side == "buy")

    print(f"{path}  ({duration / 60:.1f} minutes)")
    print(f"  fills:        {len(fills)} ({makers} maker, {len(fills) - makers} taker)")
    print(f"  volume:       {btc(volume):.4f} BTC ({btc(buys):.4f} bought, {btc(volume - buys):.4f} sold)")
    print(f"  end position: {btc(bt.position):+.5f} BTC")
    print(f"  fees paid:    ${usd(bt.fees_paid):,.2f}")
    print(f"  PnL at mid:   ${usd(bt.pnl_at_mid() or 0):,.2f}")
    print(f"  max drawdown: ${usd(max_drawdown(series['pnl'])):,.2f}")
    print(f"  rejected:     {bt.rejections} (cancels that lost the race to a fill)")
    for horizon in (1, 5, 30):
        moves = markouts(fills, series, result["start"], horizon)
        if moves:
            average = sum(moves) / len(moves)
            share_bad = sum(m < 0 for m in moves) / len(moves)
            print(
                f"  markout {horizon:>2}s:  {average:+.2f} ticks per fill on average, "
                f"{share_bad:.0%} of fills moved against us"
            )


def plot(result: dict, out: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (install matplotlib for a chart: uv pip install matplotlib)")
        return

    s = result["series"]
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(s["t"], [price_usd(m) for m in s["mid"]])
    axes[0].set_ylabel("BTC mid ($)")
    axes[1].plot(s["t"], [btc(p) for p in s["position"]], color="tab:orange")
    axes[1].axhline(0, color="gray", linewidth=0.5)
    axes[1].set_ylabel("position (BTC)")
    axes[2].plot(s["t"], [usd(p) for p in s["pnl"]], color="tab:red")
    axes[2].axhline(0, color="gray", linewidth=0.5)
    axes[2].set_ylabel("PnL ($)")
    axes[2].set_xlabel("seconds")
    fig.suptitle("Strategy v1: join the best bid and ask every second")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"  chart: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recording", nargs="?", type=Path, default=None)
    parser.add_argument("--size-btc", type=float, default=0.001)
    parser.add_argument("--every-ms", type=float, default=1000)
    parser.add_argument("--latency-ms", type=float, default=10)
    parser.add_argument("--maker-fee-bps", type=int, default=0)
    parser.add_argument("--taker-fee-bps", type=int, default=0)
    args = parser.parse_args()

    path = args.recording or newest_recording()
    bt = lobster.Backtest(
        str(path),
        latency_ms=args.latency_ms,
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
    )
    problems = {k: v for k, v in bt.read_summary().items() if k != "lines" and v}
    if problems:
        print(f"warning: problems reading the recording: {problems}")

    result = run(bt, lots(args.size_btc), round(args.every_ms * 1_000_000))
    summarize(bt, result, path)
    plot(result, Path("strategies/output/naive.png"))


if __name__ == "__main__":
    main()
