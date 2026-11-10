"""Talks to Schwab for the rest of the server: one client, short caching, clear errors.

The server never opens a browser to log in. It only uses an existing token
file; logging in is `python connectors/schwab/login.py`, run by you.
"""

import asyncio
import dataclasses
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from config import SchwabSettings

from .models import Account, Order
from .parse import parse_accounts, parse_orders
from .portfolio import Portfolio, summarize
from .quotes import Quote, parse_quotes
from .token import TokenStatus, token_status

CACHE_SECONDS = 10.0  # Schwab allows ~120 requests a minute; pages poll far less than that
RECENT_ORDERS = timedelta(days=1)  # closed orders older than this are left out


class SchwabUnavailable(Exception):
    """Schwab can't be reached right now, and why. `reason` is one of
    no_credentials, not_logged_in, login_expired, error."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


class SchwabService:
    def __init__(
        self,
        settings: SchwabSettings,
        client_factory: Callable[[], Any] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        account_names: dict[str, str] | None = None,
    ):
        self._settings = settings
        self._names = account_names or {}
        self._factory = client_factory or self._client_from_token_file
        self._now = now
        self._client: Any = None
        self._client_login: datetime | None = None  # which login the client was made from
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._fetched_at: dict[str, datetime] = {}  # when each cached answer came from Schwab

    # --- what the routes call ---

    def token(self) -> TokenStatus:
        return token_status(self._settings.token_path)

    async def accounts(self) -> list[Account]:
        return await self._cached("accounts", self._fetch_accounts)

    def accounts_fetched_at(self) -> datetime | None:
        """When the account data now being served came from Schwab."""
        return self._fetched_at.get("accounts")

    async def portfolio(self) -> Portfolio:
        """Every account added together (uses the same cached account data)."""
        return summarize(await self.accounts())

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Today's price and change for each symbol, e.g. ["SPY"]."""
        key = "quotes:" + ",".join(sorted(symbols))
        return await self._cached(key, lambda client: self._fetch_quotes(client, symbols))

    async def orders(self) -> list[Order]:
        """Orders still waiting to fill, plus any from the last day."""
        return await self._cached("orders", self._fetch_orders)

    async def status(self) -> dict:
        """For the top bar. Facts only: never keys, tokens or full account numbers."""
        token = self.token()
        out = {
            "credentials": self._settings.api_key is not None and self._settings.app_secret is not None,
            "token_saved": token.saved,
            "login_expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "connected": False,
            "problem": None,
            "message": None,
            "accounts": [],
        }
        try:
            out["accounts"] = [account.name for account in await self.accounts()]
            out["connected"] = True
        except SchwabUnavailable as error:
            out["problem"], out["message"] = error.reason, error.message
        return out

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close_async_session()
            self._client = None

    # --- internals ---

    async def _cached(self, key: str, fetch: Callable[[Any], Awaitable[Any]]) -> Any:
        async with self._lock:  # one Schwab call at a time; later callers get the cached answer
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            value = await self._call(fetch)
            self._cache[key] = (time.monotonic(), value)
            self._fetched_at[key] = self._now()
            return value

    async def _call(self, fetch: Callable[[Any], Awaitable[Any]]) -> Any:
        token = self._check_ready()
        try:
            if self._client is None or self._client_login != token.expires_at:
                await self.close()  # a new login happened: start a client from the new token
                self._client = self._factory()
                self._client_login = token.expires_at
            return await fetch(self._client)
        except Exception as error:
            await self._forget_client()
            raise self._explain(error) from error

    def _check_ready(self) -> TokenStatus:
        if self._settings.api_key is None or self._settings.app_secret is None:
            raise SchwabUnavailable("no_credentials", "Add SCHWAB_API_KEY and SCHWAB_APP_SECRET to .env")
        token = self.token()
        if not token.saved:
            raise SchwabUnavailable("not_logged_in", "Log in with: python connectors/schwab/login.py")
        if token.expired(self._now()):
            raise SchwabUnavailable("login_expired", "Schwab logins last 7 days. Log in again: python connectors/schwab/login.py")
        return token

    def _explain(self, error: Exception) -> SchwabUnavailable:
        # Error text from the HTTP layer can contain URLs with account hashes, so
        # only the error's type and HTTP status are passed on.
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status == 401:
            return SchwabUnavailable("login_expired", "Schwab refused the login. Log in again: python connectors/schwab/login.py")
        detail = f"HTTP {status}" if status else type(error).__name__
        return SchwabUnavailable("error", f"Schwab request failed ({detail})")

    async def _forget_client(self) -> None:
        try:
            await self.close()
        except Exception:
            self._client = None

    def _client_from_token_file(self) -> Any:
        from schwab import auth  # imported here so the server starts even without schwab-py installed

        api_key, app_secret = self._settings.credentials()
        return auth.client_from_token_file(str(self._settings.token_path), api_key, app_secret, asyncio=True)

    async def _fetch_accounts(self, client: Any) -> list[Account]:
        response = await client.get_accounts(fields=[client.Account.Fields.POSITIONS])
        response.raise_for_status()
        return [dataclasses.replace(a, name=self._name(a.last4)) for a in parse_accounts(response.json())]

    def _name(self, last4: str) -> str:
        """Your name for an account: by its digits, else the "*" name, else the digits."""
        return self._names.get(last4.lstrip("…")) or self._names.get("*") or last4

    async def _fetch_quotes(self, client: Any, symbols: list[str]) -> dict[str, Quote]:
        response = await client.get_quotes(symbols)
        response.raise_for_status()
        return parse_quotes(response.json())

    async def _fetch_orders(self, client: Any) -> list[Order]:
        response = await client.get_orders_for_all_linked_accounts()  # the last 60 days
        response.raise_for_status()
        cutoff = self._now() - RECENT_ORDERS
        return [order for order in parse_orders(response.json()) if order.is_open or _entered_after(order, cutoff)]


def _entered_after(order: Order, cutoff: datetime) -> bool:
    try:
        return datetime.fromisoformat(order.entered_time) >= cutoff
    except ValueError:
        return False
