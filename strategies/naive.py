"""Strategy v1 on its own: the simplest possible market maker.

Every second: cancel whatever is resting, then quote one bid at Coinbase's best
bid and one ask at the best ask. See strats.py for the strategy and harness.py
for the metrics.

    python strategies/naive.py                       # newest recording
    python strategies/naive.py data/coinbase/BTC-USD/<file>.jsonl --maker-fee-bps 40
"""

import argparse
from pathlib import Path

import harness
from strats import Naive
from units import lots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recording", nargs="?", type=Path, default=None)
    parser.add_argument("--size-btc", type=float, default=0.001)
    parser.add_argument("--latency-ms", type=float, default=10)
    parser.add_argument("--maker-fee-bps", type=int, default=0)
    parser.add_argument("--taker-fee-bps", type=int, default=0)
    args = parser.parse_args()

    path = args.recording or harness.newest_recording()
    bt = harness.open_backtest(
        path,
        latency_ms=args.latency_ms,
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
    )
    result = harness.run(bt, Naive(lots(args.size_btc)))
    print(path)
    harness.print_summary(result)
    harness.plot([result], Path("strategies/output/naive.png"), "Strategy v1: join the best bid and ask every second")


if __name__ == "__main__":
    main()
