"""Shared Schwab setup: an authenticated async client.

Credentials and the token's location come from the app's settings
(`config/settings.py`), which read the environment or the gitignored `.env`
at the repo root. See `.env.example` for the names.

The token file is created by schwab-py the first time you log in (a browser
opens) and refreshed automatically. Schwab's refresh tokens last about seven
days; after that, schwab-py asks you to log in again.
"""

import sys
from pathlib import Path

from schwab import auth

# The settings package lives at the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import get_settings  # noqa: E402


def async_client():
    """An authenticated schwab-py client for use with asyncio.

    Opens a browser to log in if there's no valid token yet.
    """
    schwab = get_settings().schwab
    api_key, app_secret = schwab.credentials()
    schwab.token_path.parent.mkdir(parents=True, exist_ok=True)
    return auth.easy_client(
        api_key=api_key,
        app_secret=app_secret,
        callback_url=schwab.callback_url,
        token_path=str(schwab.token_path),
        asyncio=True,
    )


async def first_account_number(client) -> int:
    """The first linked account's number (needed to start the streaming client).

    Treat it as private: it's never printed or written to recordings.
    """
    response = await client.get_account_numbers()
    response.raise_for_status()
    accounts = response.json()
    if not accounts:
        raise SystemExit("no accounts are linked to this Schwab login")
    return int(accounts[0]["accountNumber"])
