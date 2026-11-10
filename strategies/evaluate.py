"""Honest evaluation: tune on earlier data, then test on later data.

Tuning parameters and judging results on the same data is how backtests lie:
with enough knobs, something always looks good by luck. So this script:

1. Cuts every recording (that includes trades) into windows of equal length.
2. Puts the earlier windows in a *training* set and the later ones in a *test*
   set (time order, never shuffled: the future must not leak into the past).
3. For each strategy family, tries a grid of parameters on the training set
   and picks the one with the best total PnL.
4. Runs those picks, untouched, on the test set and reports both.

If a strategy is much better in training than in test, it was overfit.

    python strategies/evaluate.py
    python strategies/evaluate.py --window-min 5 --maker-fee-bps 40 --taker-fee-bps 60
"""

import argparse
import itertools
import time
from pathlib import Path

import harness
from strats import AvellanedaStoikov, ImbalanceFilter, InventorySkew, Naive
from units import NS_PER_SECOND, lots


def windows(paths: list[Path], window_ns: int) -> list[tuple[Path, int, int]]:
    """Every full window in every recording, in time order: (file, start, end)."""
    out = []
    for path in paths:
        first, last = harness.recording_span_ns(path)
        # Skip the first few seconds so strategies that need history can warm up
        start = first + 5 * NS_PER_SECOND
        while start + window_ns <= last:
            out.append((path, start, start + window_ns))
            start += window_ns
    return sorted(out, key=lambda w: w[1])


def families(size: int) -> dict:
    """Each strategy family with the parameter grid to search."""
    return {
        "v1 naive": (lambda: Naive(size), [{}]),
        "v2 inventory skew": (
            lambda skew, max_btc: InventorySkew(size, lots(max_btc), skew),
            [{"skew": s, "max_btc": m} for s, m in itertools.product([1, 2, 4], [0.005, 0.01])],
        ),
        "v3 imbalance filter": (
            lambda skew, max_btc, threshold: ImbalanceFilter(size, lots(max_btc), skew, threshold),
            [
                {"skew": s, "max_btc": 0.01, "threshold": t}
                for s, t in itertools.product([1, 2], [0.3, 0.5, 0.7, 0.9])
            ],
        ),
        "v4 avellaneda-stoikov": (
            lambda gamma, k: AvellanedaStoikov(size, lots(0.01), gamma=gamma, k=k),
            [{"gamma": g, "k": k} for g, k in itertools.product([3e-6, 1e-5, 3e-5], [0.5, 1.0, 2.0])],
        ),
    }


def run_on(windows_, make, params, config) -> dict:
    """Runs one parameter setting on every window; sums the results."""
    total = {"pnl_usd": 0.0, "fees_usd": 0.0, "fills": 0, "minutes": 0.0, "spread_capture_usd": 0.0}
    per_window = []
    for path, start, end in windows_:
        bt = harness.open_backtest(path, **config)
        result = harness.run(bt, make(**params), start_ns=start, end_ns=end)
        m = result.metrics
        per_window.append(m["pnl_usd"])
        for key in total:
            total[key] += m[key]
    total["windows_won"] = sum(p > 0 for p in per_window)
    total["windows"] = len(per_window)
    total["pnl_per_hour_usd"] = total["pnl_usd"] / (total["minutes"] / 60) if total["minutes"] else 0.0
    # Sharpe across windows: average window PnL / its spread, scaled to a year
    if len(per_window) > 1:
        mean = sum(per_window) / len(per_window)
        sd = (sum((p - mean) ** 2 for p in per_window) / (len(per_window) - 1)) ** 0.5
        window_min = total["minutes"] / len(per_window)
        total["sharpe"] = mean / sd * (harness.MINUTES_PER_YEAR / window_min) ** 0.5 if sd else 0.0
    else:
        total["sharpe"] = 0.0
    return total


def describe(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items()) or "-"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window-min", type=float, default=10)
    parser.add_argument("--train-share", type=float, default=0.6)
    parser.add_argument("--size-btc", type=float, default=0.001)
    parser.add_argument("--latency-ms", type=float, default=10)
    parser.add_argument("--maker-fee-bps", type=int, default=0)
    parser.add_argument("--taker-fee-bps", type=int, default=0)
    args = parser.parse_args()

    config = {
        "latency_ms": args.latency_ms,
        "maker_fee_bps": args.maker_fee_bps,
        "taker_fee_bps": args.taker_fee_bps,
    }
    paths = sorted(harness.RECORDINGS.glob("*.jsonl"))
    usable = [p for p in paths if harness.has_trades(p)]
    skipped = len(paths) - len(usable)
    all_windows = windows(usable, round(args.window_min * 60 * NS_PER_SECOND))
    split = max(1, round(len(all_windows) * args.train_share))
    train, test = all_windows[:split], all_windows[split:]
    print(
        f"{len(usable)} recordings with trades ({skipped} skipped without), "
        f"{len(all_windows)} windows of {args.window_min:g} min: "
        f"{len(train)} train, {len(test)} test. Settings: {config}"
    )
    if not test:
        raise SystemExit("not enough data for a test set yet; record more, or use a smaller --window-min")

    rows = []
    started = time.time()
    for name, (make, grid) in families(lots(args.size_btc)).items():
        tried = [(run_on(train, make, params, config), params) for params in grid]
        best_train, best = max(tried, key=lambda pair: pair[0]["pnl_usd"])
        on_test = run_on(test, make, best, config)
        rows.append((name, best, best_train, on_test))
        print(f"  {name}: tried {len(grid)} settings, best on train: {describe(best)}")
    print(f"  ({time.time() - started:.0f} s)")

    print()
    header = (
        f"{'strategy':<22} {'':<6} {'$/hour':>9} {'Sharpe':>8} {'fills':>7} "
        f"{'spread $':>9} {'fees $':>8} {'windows won':>12}"
    )
    print(header)
    print("-" * len(header))
    for name, best, on_train, on_test in rows:
        for label, r in (("train", on_train), ("test", on_test)):
            print(
                f"{name if label == 'train' else '':<22} {label:<6} {r['pnl_per_hour_usd']:>9,.2f} "
                f"{r['sharpe']:>+8.1f} {r['fills']:>7} {r['spread_capture_usd']:>9,.2f} "
                f"{r['fees_usd']:>8,.2f} {r['windows_won']:>5} of {r['windows']:<4}"
            )
    print()
    print("Read the test rows: they're the only honest numbers. A big drop from")
    print("train to test means the chosen settings were fitting noise.")


if __name__ == "__main__":
    main()
