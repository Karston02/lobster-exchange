"""Tests for turning Schwab JSON into records. Run: pytest dashboard/server/account

The fixtures follow Schwab's documented shapes with made-up numbers.
"""

import json
from pathlib import Path

from account.money import cents, mask, per_unit
from account.parse import parse_accounts, parse_orders

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_cents_rounds_half_up_without_float_noise():
    assert cents(0.1 + 0.2) == 30
    assert cents(12.345) == 1235
    assert cents(-4.05) == -405
    assert cents(None) == 0


def test_per_unit_rounds_halves_up():
    assert per_unit(29250, 100) == 293
    assert per_unit(387000, 7.5) == 51600
    assert per_unit(100, 0) == 0


def test_mask_keeps_only_the_last_four_digits():
    assert mask("99990000") == "…0000"
    assert mask(12345678) == "…5678"


def test_accounts_parse_into_cents_with_masked_numbers():
    margin, cash = parse_accounts(load("accounts.json"))

    assert margin.last4 == "…0000"
    assert margin.type == "MARGIN"
    assert margin.total_value_cents == 660620
    assert margin.cash_cents == 50000
    assert margin.buying_power_cents == 100000
    assert margin.day_change_cents == 1230 - 405
    assert margin.open_pnl_cents == 43120 + 12000
    assert [p.symbol for p in margin.positions] == ["SPY", "AAPL"]  # biggest first
    assert margin.positions[0].quantity == 7.5
    assert margin.positions[0].price_cents == 51600  # $3,870.00 / 7.5 shares


def test_the_full_account_number_never_survives_parsing():
    accounts = parse_accounts(load("accounts.json"))

    assert "99990000" not in repr(accounts)
    assert "88881234" not in repr(accounts)


def test_cash_accounts_use_cash_available_as_buying_power():
    _, cash = parse_accounts(load("accounts.json"))

    assert cash.type == "CASH"
    assert cash.total_value_cents == 34010
    assert cash.cash_cents == 4010
    assert cash.buying_power_cents == 4010  # no buyingPower field on cash accounts


def test_missing_fields_fall_back_instead_of_crashing():
    _, cash = parse_accounts(load("accounts.json"))

    assert cash.positions[0].description == ""  # Schwab omits it for some positions
    empty = parse_accounts([{}])[0]
    assert empty.total_value_cents == 0
    assert empty.positions == []
    assert empty.buying_power_cents is None


def test_orders_parse_newest_first_with_open_flags():
    orders = parse_orders(load("orders.json"))

    assert [o.symbol for o in orders] == ["SPY", "TSLA", "AAPL"]
    working = orders[2]
    assert working.order_id == "9007199254740993"  # too big for a JS number, so a string
    assert working.is_open and working.side == "BUY" and working.price_cents == 17525
    assert orders[0].price_cents is None  # market order
    assert not orders[0].is_open
    assert working.account_last4 == "…0000"


def test_option_prices_are_per_share_like_schwab_quotes_them():
    option = {
        "longQuantity": 1,
        "shortQuantity": 0,
        "averagePrice": 7.06,
        "marketValue": 292.5,
        "instrument": {"assetType": "OPTION", "symbol": "NFLX  280121C00100000"},
    }
    (account,) = parse_accounts([{"securitiesAccount": {"positions": [option]}}])

    assert account.positions[0].price_cents == 293  # $292.50 / (1 contract x 100 shares), rounded
    assert account.positions[0].market_value_cents == 29250
