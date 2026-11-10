"""End-to-end tests for lobster.Backtest: a tiny recording file, written in
the recorder's exact format, replayed with a bot trading in it.

Run from the repo root with the venv active:  pytest strategies
"""

import json

import pytest

import lobster

T0 = "2026-01-01T00:00:00Z"


def at(ms: int) -> str:
    """A Coinbase-style timestamp `ms` milliseconds after T0."""
    return f"2026-01-01T00:00:00.{ms:03d}Z"


def write_recording(path, trades):
    """A book with 10 lots bid at $0.99 and 10 lots offered at $1.01, then trades.

    `trades` is a list of (ms, maker side "BUY"/"SELL", price string, lots).
    """
    snapshot = {
        "channel": "l2_data",
        "timestamp": T0,
        "events": [
            {
                "type": "snapshot",
                "product_id": "BTC-USD",
                "updates": [
                    {"side": "bid", "event_time": T0, "price_level": "0.99", "new_quantity": "0.0000001"},
                    {"side": "offer", "event_time": T0, "price_level": "1.01", "new_quantity": "0.0000001"},
                ],
            }
        ],
    }
    messages = [snapshot]
    for i, (ms, side, price, size_lots) in enumerate(trades):
        messages.append(
            {
                "channel": "market_trades",
                "timestamp": at(ms),
                "events": [
                    {
                        "type": "update",
                        "trades": [
                            {
                                "trade_id": str(i),
                                "product_id": "BTC-USD",
                                "price": price,
                                "size": f"{size_lots / 1e8:.8f}",
                                "side": side,
                                "time": at(ms),
                            }
                        ],
                    }
                ],
            }
        )
    with open(path, "w") as f:
        for sequence, message in enumerate(messages):
            message["sequence_num"] = sequence
            f.write(json.dumps({"recv_ns": sequence + 1, "msg": message}) + "\n")


def test_reads_the_recording_and_sees_the_market(tmp_path):
    path = tmp_path / "rec.jsonl"
    write_recording(path, [])
    bt = lobster.Backtest(str(path))

    assert bt.read_summary()["lines"] == 1
    assert bt.read_summary()["sequence_gaps"] == 0
    assert bt.best_bid() == (99, 10)
    assert bt.best_ask() == (101, 10)
    assert bt.mid() == 100


def test_bot_waits_in_line_then_fills_from_trades(tmp_path):
    path = tmp_path / "rec.jsonl"
    # Sellers hit the 99 bid: 6 lots at 20 ms, 6 more at 30 ms
    write_recording(path, [(20, "BUY", "0.99", 6), (30, "BUY", "0.99", 6)])
    bt = lobster.Backtest(str(path), latency_ms=1)
    start = bt.now_ns

    order_id = bt.submit_limit("buy", 99, 3)
    bt.run_until(start + 10_000_000)
    assert [o.id for o in bt.open_orders()] == [order_id]
    assert bt.queue_ahead(order_id) == 10

    bt.run_until(start + 20_000_000)
    assert bt.queue_ahead(order_id) == 4
    assert bt.take_fills() == []

    bt.run_until(start + 30_000_000)
    [fill] = bt.take_fills()
    assert (fill.side, fill.price, fill.quantity, fill.maker) == ("buy", 99, 2, True)
    assert bt.position == 2
    assert bt.cash == -(99 * 2)


def test_taker_fee_is_charged(tmp_path):
    path = tmp_path / "rec.jsonl"
    write_recording(path, [])
    bt = lobster.Backtest(str(path), latency_ms=0, taker_fee_bps=100)

    bt.submit_ioc("buy", 101, 4)
    bt.run_until(bt.now_ns)
    [fill] = bt.take_fills()
    assert not fill.maker
    assert fill.fee == 5  # 1% of 101 * 4 = 4.04, rounded up
    assert bt.fees_paid == 5


def test_bad_arguments_raise(tmp_path):
    path = tmp_path / "rec.jsonl"
    write_recording(path, [])
    with pytest.raises(ValueError):
        lobster.Backtest(str(path), latency_ms=-1)
    with pytest.raises(OSError):
        lobster.Backtest(str(tmp_path / "missing.jsonl"))
    bt = lobster.Backtest(str(path))
    with pytest.raises(ValueError):
        bt.submit_limit("long", 99, 1)
