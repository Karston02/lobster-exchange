"""Shared Schwab setup: credentials and an authenticated async client.

Credentials come from environment variables, or from a `.env` file at the
repo root (gitignored), never from the code:

    SCHWAB_API_KEY=...
    SCHWAB_APP_SECRET=...
    SCHWAB_CALLBACK_URL=https://127.0.0.1:8182      # must match your app exactly
    SCHWAB_TOKEN_PATH=~/.lobster/schwab_token.json  # optional; outside the repo

The token file is created by schwab-py the first time you log in (a browser
opens) and refreshed automatically. Schwab's refresh tokens last about seven
days; after that, schwab-py asks you to log in again.
"""

import os
from pathlib import Path

from schwab import auth

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOKEN_PATH = Path.home() / ".lobster" / "schwab_token.json"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Reads KEY=VALUE lines from `.env` into the environment (without overriding)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise SystemExit(f"missing {name}: set it in your environment or in {ROOT / '.env'}")
    return value


def token_path() -> Path:
    path = Path(os.path.expanduser(setting("SCHWAB_TOKEN_PATH", str(DEFAULT_TOKEN_PATH))))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def async_client():
    """An authenticated schwab-py client for use with asyncio.

    Opens a browser to log in if there's no valid token yet.
    """
    load_dotenv()
    return auth.easy_client(
        api_key=setting("SCHWAB_API_KEY"),
        app_secret=setting("SCHWAB_APP_SECRET"),
        callback_url=setting("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        token_path=str(token_path()),
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
