"""The service with a fake Schwab client: no network, no schwab-py needed."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from account import SchwabService, SchwabUnavailable
from config import SchwabSettings, Secret

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code} for https://api.schwab.com/accounts/SECRETHASH")
            error.response = self
            raise error


class FakeClient:
    class Account:
        class Fields:
            POSITIONS = "positions"

    def __init__(self, status=200):
        self.status = status
        self.calls = 0
        self.closed = False

    async def get_accounts(self, fields):
        self.calls += 1
        return FakeResponse(json.loads((FIXTURES / "accounts.json").read_text()), self.status)

    async def get_quotes(self, symbols):
        self.calls += 1
        return FakeResponse({s: {"quote": {"lastPrice": 101.0, "closePrice": 100.0}} for s in symbols}, self.status)

    async def get_orders_for_all_linked_accounts(self):
        return FakeResponse(json.loads((FIXTURES / "orders.json").read_text()), self.status)

    async def close_async_session(self):
        self.closed = True


def settings(tmp_path, login_days_ago=1, keys=True) -> SchwabSettings:
    token = tmp_path / "token.json"
    if login_days_ago is not None:
        created = NOW - timedelta(days=login_days_ago)
        token.write_text(json.dumps({"creation_timestamp": int(created.timestamp()), "token": {}}))
    return SchwabSettings(
        api_key=Secret("k") if keys else None,
        app_secret=Secret("s") if keys else None,
        callback_url="https://127.0.0.1:8182",
        token_path=token,
    )


def service(tmp_path, client=None, **kwargs) -> SchwabService:
    client = client or FakeClient()
    return SchwabService(settings(tmp_path, **kwargs), client_factory=lambda: client, now=lambda: NOW)


def test_accounts_are_fetched_once_then_cached(tmp_path):
    client = FakeClient()
    svc = service(tmp_path, client)

    async def twice():
        return await svc.accounts(), await svc.accounts()

    first, second = asyncio.run(twice())
    assert first == second and len(first) == 2
    assert client.calls == 1


def test_orders_keep_open_ones_and_the_last_day(tmp_path):
    orders = asyncio.run(service(tmp_path).orders())

    # AAPL is open (entered weeks ago), SPY filled today; the old cancelled TSLA is left out
    assert sorted(o.symbol for o in orders) == ["AAPL", "SPY"]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"keys": False}, "no_credentials"),
        ({"login_days_ago": None}, "not_logged_in"),
        ({"login_days_ago": 8}, "login_expired"),
    ],
)
def test_explains_why_schwab_is_unavailable(tmp_path, kwargs, reason):
    with pytest.raises(SchwabUnavailable) as caught:
        asyncio.run(service(tmp_path, **kwargs).accounts())
    assert caught.value.reason == reason


def test_a_401_means_log_in_again_and_errors_hide_urls(tmp_path):
    with pytest.raises(SchwabUnavailable) as caught:
        asyncio.run(service(tmp_path, FakeClient(status=401)).accounts())
    assert caught.value.reason == "login_expired"

    with pytest.raises(SchwabUnavailable) as caught:
        asyncio.run(service(tmp_path, FakeClient(status=500)).accounts())
    assert caught.value.reason == "error"
    assert "SECRETHASH" not in caught.value.message


def test_status_reports_facts_only(tmp_path):
    status = asyncio.run(service(tmp_path).status())

    assert status["connected"] is True
    assert status["accounts"] == ["…0000", "…1234"]
    assert status["login_expires_at"] == (NOW - timedelta(days=1) + timedelta(days=7)).replace(microsecond=0).isoformat()
    text = json.dumps(status)
    assert "99990000" not in text and '"k"' not in text


def test_status_when_logged_out(tmp_path):
    status = asyncio.run(service(tmp_path, login_days_ago=None).status())

    assert status["connected"] is False
    assert status["problem"] == "not_logged_in"


def test_quotes_are_cached_per_symbol_list(tmp_path):
    client = FakeClient()
    svc = service(tmp_path, client)

    async def run():
        first = await svc.quotes(["SPY"])
        await svc.quotes(["SPY"])
        await svc.quotes(["SPY", "QQQ"])
        return first

    assert asyncio.run(run())["SPY"].change_cents == 100
    assert client.calls == 2


def test_portfolio_reuses_the_cached_accounts(tmp_path):
    client = FakeClient()
    svc = service(tmp_path, client)

    async def run():
        await svc.accounts()
        return await svc.portfolio()

    assert asyncio.run(run()).account_count == 2
    assert client.calls == 1
