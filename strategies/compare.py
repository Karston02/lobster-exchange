"""Runs every strategy on the same recording and compares them side by side.

    python strategies/compare.py                          # newest recording
    python strategies/compare.py <file>.jsonl --maker-fee-bps 40
    python strategies/compare.py --skew-ticks 2 --max-position-btc 0.005
    python strategies/compare.py --imbalance-threshold 0.5 --imbalance-levels 3

Each strategy gets a fresh backtest of the same data with the same settings.
Prints a table and saves strategies/output/compare.png.
"""

import argparse
from pathlib import Path

import harness
from strats import ImbalanceFilter, InventorySkew, KeepPlace, Naive
from units import lots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recording", nargs="?", type=Path, default=None)
    parser.add_argument("--size-btc", type=float, default=0.001)
    parser.add_argument("--max-position-btc", type=float, default=0.01)
    parser.add_argument("--skew-ticks", type=int, default=1)
    parser.add_argument("--imbalance-threshold", type=float, default=0.6)
    parser.add_argument("--imbalance-levels", type=int, default=1)
    parser.add_argument("--latency-ms", type=float, default=10)
    parser.add_argument("--maker-fee-bps", type=int, default=0)
    parser.add_argument("--taker-fee-bps", type=int, default=0)
    parser.add_argument("--details", action="store_true", help="also print each strategy's full summary")
    args = parser.parse_args()

    path = args.recording or harness.newest_recording()
    size = lots(args.size_btc)
    strategies = [
        Naive(size),
        KeepPlace(size),
        InventorySkew(size, lots(args.max_position_btc), args.skew_ticks),
        ImbalanceFilter(
            size,
            lots(args.max_position_btc),
            args.skew_ticks,
            args.imbalance_threshold,
            args.imbalance_levels,
        ),
    ]
    config = {
        "latency_ms": args.latency_ms,
        "maker_fee_bps": args.maker_fee_bps,
        "taker_fee_bps": args.taker_fee_bps,
    }

    results = []
    for strategy in strategies:
        bt = harness.open_backtest(path, **config)  # Fresh replay for each strategy
        results.append(harness.run(bt, strategy))

    print(f"{path}  ({results[0].metrics['minutes']:.1f} minutes, {config})")
    print()
    harness.print_table(results)
    if args.details:
        for result in results:
            print()
            harness.print_summary(result)
    harness.plot(results, Path("strategies/output/compare.png"), "Strategies compared on the same data")


if __name__ == "__main__":
    main()
