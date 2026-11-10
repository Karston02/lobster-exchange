"""Tests for live prices and repricing. Run: pytest dashboard/server/live"""

import json
from pathlib import Path

from account.parse import parse_accounts
from live.prices import LivePrices
from live.revalue import revalue

FIXTURES = Path(__file__).parents[1] / "account" / "fixtures"


def accounts():
    return parse_accounts(json.loads((FIXTURES / "accounts.json").read_text()))


def test_messages_carry_only_changes_and_are_merged():
    prices = LivePrices()

    assert prices.apply([{"key": "SPY", "LAST_PRICE": 600.0, "CLOSE_PRICE": 597.0}]) == {"SPY"}
    assert prices.apply([{"key": "SPY", "BID_PRICE": 599.9}]) == set()  # not a price we use
    assert prices.apply([{"key": "SPY", "LAST_PRICE": 600.5}]) == {"SPY"}

    spy = prices.get("SPY")
    assert spy.last_cents == 60050 and spy.close_cents == 59700
    assert spy.change_cents == 350
    assert round(spy.change_pct, 4) == 0.5863


def test_regular_session_price_wins_over_after_hours():
    prices = LivePrices()
    prices.apply([{"key": "SPY", "LAST_PRICE": 602.0, "REGULAR_MARKET_LAST_PRICE": 600.0}])

    assert prices.get("SPY").last_cents == 60000


def test_unknown_symbols_and_missing_close():
    prices = LivePrices()
    prices.apply([{"key": "X", "MARK": 10.0}, {"BID_PRICE": 1}])

    assert prices.get("NOPE") is None
    assert prices.get("X").change_pct is None


def test_positions_move_by_shares_times_the_price_move():
    margin, cash = accounts()
    prices = LivePrices()
    # SPY: 7.5 shares, snapshot price $516.00 -> $520.00 is +$30.00
    prices.apply([{"key": "SPY", "LAST_PRICE": 520.0}])

    new_margin, new_cash = revalue([margin, cash], prices)

    spy = next(p for p in new_margin.positions if p.symbol == "SPY")
    assert spy.price_cents == 52000
    assert spy.market_value_cents == 387000 + 3000
    assert spy.day_change_cents == -405 + 3000
    assert new_margin.total_value_cents == margin.total_value_cents + 3000
    assert new_margin.day_change_cents == margin.day_change_cents + 3000
    assert new_cash is cash  # nothing it holds moved


def test_options_keep_their_snapshot_value():
    option = {
        "longQuantity": 1,
        "marketValue": 292.5,
        "instrument": {"assetType": "OPTION", "symbol": "NFLX  280121C00100000"},
    }
    (account,) = parse_accounts([{"securitiesAccount": {"positions": [option]}}])
    prices = LivePrices()
    prices.apply([{"key": "NFLX  280121C00100000", "LAST_PRICE": 5.0}])

    assert revalue([account], prices) == [account]
