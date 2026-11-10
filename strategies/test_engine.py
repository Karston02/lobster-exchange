"""Tests for the Python bindings. Run from the repo root with the venv active:

    pytest strategies

These check the Python side of the bridge (argument conversion, events,
errors); the matching logic itself is tested in Rust.
"""

import pytest

import lobster


def test_resting_order_is_accepted_and_sets_the_best_bid():
    engine = lobster.Engine()
    events = engine.submit_limit(1, "buy", 100, 5)

    assert [e.kind for e in events] == ["accepted"]
    assert events[0].order_id == 1
    assert engine.best_bid() == 100
    assert engine.best_ask() is None
    assert engine.order_count() == 1


def test_crossing_order_trades_at_the_makers_price():
    engine = lobster.Engine()
    engine.submit_limit(1, "sell", 100, 5)
    events = engine.submit_limit(2, "buy", 105, 3)

    assert [e.kind for e in events] == ["accepted", "trade"]
    trade = events[1]
    assert (trade.maker_id, trade.taker_id, trade.price, trade.quantity) == (1, 2, 100, 3)
    assert engine.quantity_at("sell", 100) == 2


def test_market_order_remainder_is_cancelled():
    engine = lobster.Engine()
    engine.submit_limit(1, "sell", 100, 2)
    events = engine.submit_market(2, "buy", 5)

    cancelled = events[-1]
    assert cancelled.kind == "cancelled"
    assert cancelled.remaining == 3
    assert cancelled.reason == "no_liquidity"


def test_ioc_never_rests():
    engine = lobster.Engine()
    events = engine.submit_ioc(1, "buy", 100, 5)

    assert [e.kind for e in events] == ["accepted", "cancelled"]
    assert engine.order_count() == 0


def test_cancel_and_rejections():
    engine = lobster.Engine()
    engine.submit_limit(1, "buy", 100, 5)

    assert engine.cancel(1)[0].reason == "requested"
    assert engine.cancel(1)[0].reason == "unknown_order_id"
    assert engine.submit_limit(2, "buy", 100, 0)[0].reason == "zero_quantity"


def test_bad_side_raises_value_error():
    engine = lobster.Engine()
    with pytest.raises(ValueError, match="buy"):
        engine.submit_limit(1, "long", 100, 5)


def test_events_print_readably():
    engine = lobster.Engine()
    engine.submit_limit(1, "sell", 100, 5)
    events = engine.submit_limit(2, "buy", 100, 5)
    assert repr(events[1]) == "Event(trade: maker 1 / taker 2, 5 @ 100)"
