import json
from pathlib import Path

from account.parse import parse_accounts
from account.portfolio import summarize
from account.quotes import parse_quotes

FIXTURES = Path(__file__).parent / "fixtures"


def accounts():
    return parse_accounts(json.loads((FIXTURES / "accounts.json").read_text()))


def test_portfolio_adds_up_every_account():
    portfolio = summarize(accounts())

    assert portfolio.account_count == 2
    assert portfolio.total_value_cents == 660620 + 34010
    assert portfolio.day_change_cents == (1230 - 405) + 150
    assert portfolio.previous_value_cents == portfolio.total_value_cents - portfolio.day_change_cents
    assert portfolio.cash_cents == 50000 + 4010
    assert [h.symbol for h in portfolio.holdings] == ["SPY", "AAPL", "VTI"]


def test_the_same_symbol_in_two_accounts_becomes_one_holding():
    first, second = accounts()
    both = summarize([first, first])

    spy = both.holdings[0]
    assert spy.symbol == "SPY"
    assert spy.quantity == 15
    assert spy.market_value_cents == 2 * 387000


def test_no_accounts_is_an_empty_portfolio():
    portfolio = summarize([])

    assert portfolio.total_value_cents == 0 and portfolio.holdings == []


def test_quotes_use_schwabs_change_fields():
    quotes = parse_quotes(
        {"SPY": {"symbol": "SPY", "quote": {"lastPrice": 600.5, "closePrice": 597.0, "netChange": 3.5, "netPercentChange": 0.5863}}}
    )

    spy = quotes["SPY"]
    assert spy.last_cents == 60050 and spy.change_cents == 350
    assert spy.change_pct == 0.5863


def test_quotes_prefer_the_regular_session_over_after_hours():
    spy = parse_quotes(
        {
            "SPY": {
                "quote": {"lastPrice": 602.0, "closePrice": 597.0, "netChange": 5.0, "netPercentChange": 0.8375},
                "regular": {"regularMarketLastPrice": 600.5, "regularMarketNetChange": 3.5, "regularMarketPercentChange": 0.5863},
            }
        }
    )["SPY"]

    assert spy.last_cents == 60050
    assert spy.change_cents == 350
    assert spy.change_pct == 0.5863
    assert spy.previous_close_cents == 59700


def test_quotes_work_out_the_change_when_its_missing():
    spy = parse_quotes({"SPY": {"quote": {"lastPrice": 99.0, "closePrice": 100.0}}})["SPY"]

    assert spy.change_cents == -100
    assert spy.change_pct == -1.0
    assert parse_quotes({"X": {"quote": {"lastPrice": 1}}})["X"].change_pct is None
