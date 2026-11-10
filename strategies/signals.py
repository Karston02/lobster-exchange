"""Does the order book predict where the price goes next? A data check.

For every second of a recording, measure the book's imbalance near the top:

    imbalance = (bid size - ask size) / (bid size + ask size)

+1 means only buyers are waiting, -1 only sellers. Then look at how the mid
moved over the next few seconds. If imbalance predicts the move, a market
maker can avoid quoting the side that's about to get run over (adverse
selection), which is what strategy v3 does.

    python strategies/signals.py                  # newest recording
    python strategies/signals.py <file>.jsonl --levels 5
"""

import argparse
from pathlib import Path

import harness
from units import NS_PER_SECOND

HORIZONS_S = (1, 5, 30)


def imbalance(bt, levels: int) -> float | None:
    bids, asks = bt.top("buy", levels), bt.top("sell", levels)
    bid_size = sum(q for _, q in bids)
    ask_size = sum(q for _, q in asks)
    if bid_size + ask_size == 0:
        return None
    return (bid_size - ask_size) / (bid_size + ask_size)


def correlation(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    return cov / (var_x * var_y) ** 0.5 if var_x and var_y else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recording", nargs="?", type=Path, default=None)
    parser.add_argument("--levels", type=int, default=1, help="price levels per side to add up")
    parser.add_argument("--every-ms", type=float, default=1000)
    args = parser.parse_args()

    path = args.recording or harness.newest_recording()
    bt = harness.open_backtest(path)
    every_ns = round(args.every_ms * 1_000_000)

    # Sample (imbalance, mid) at a fixed interval
    samples = []
    while not bt.market_finished():
        bt.run_until(bt.now_ns + every_ns)
        value, mid = imbalance(bt, args.levels), bt.mid()
        if value is not None and mid is not None:
            samples.append((value, mid))

    print(f"{path}: {len(samples)} samples, top {args.levels} level(s) per side")
    steps_per_second = NS_PER_SECOND / every_ns
    for horizon in HORIZONS_S:
        ahead = round(horizon * steps_per_second)
        pairs = [
            (samples[i][0], samples[i + ahead][1] - samples[i][1])
            for i in range(len(samples) - ahead)
        ]
        if len(pairs) < 10:
            continue
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        print(f"\n  next {horizon}s: correlation {correlation(xs, ys):+.3f}")

        # Split into five equal-sized groups from most sell-heavy to most buy-heavy
        ordered = sorted(pairs)
        size = len(ordered) // 5
        print("    imbalance group          avg imbalance   avg mid move (ticks)")
        names = ["sellers heavy", "", "balanced", "", "buyers heavy"]
        for g in range(5):
            group = ordered[g * size : (g + 1) * size] if g < 4 else ordered[4 * size :]
            avg_x = sum(x for x, _ in group) / len(group)
            avg_y = sum(y for _, y in group) / len(group)
            print(f"    {g + 1} {names[g]:<20}  {avg_x:+.2f}           {avg_y:+.2f}")


if __name__ == "__main__":
    main()
