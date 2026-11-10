"""Every path, key, port and address Lobster needs, in one place.

Nothing in the code may assume Karston's laptop. Anything that would differ on
another machine is read here, from environment variables or from the
gitignored `.env` file at the repo root. Real environment variables win over
`.env`, so a server can set them without a file. See `.env.example`.

Relative paths count from the repo root (not from wherever a script was
started), and `~` means the home folder.

Use `get_settings()`. It reads everything once and reuses the result.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .env_file import read_env_file

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

# Until the app has a real login (build step 8), it only listens on this machine
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class SettingError(RuntimeError):
    """A setting is missing or has a bad value."""


class Secret:
    """A string that prints as stars, so a stray print or log can't leak it."""

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        """The real value. Only hand it to the library that needs it."""
        return self._value

    def __repr__(self) -> str:
        return "Secret('**********')"

    __str__ = __repr__


@dataclass(frozen=True)
class SchwabSettings:
    """Schwab API credentials and the login token's location (`SCHWAB_*`)."""

    api_key: Secret | None
    app_secret: Secret | None
    callback_url: str  # must match the app on developer.schwab.com exactly
    token_path: Path

    def credentials(self) -> tuple[str, str]:
        """The API key and app secret as plain strings, for schwab-py only."""
        if self.api_key is None or self.app_secret is None:
            raise SettingError(f"set SCHWAB_API_KEY and SCHWAB_APP_SECRET in your environment or in {ENV_FILE}")
        return self.api_key.reveal(), self.app_secret.reveal()


@dataclass(frozen=True)
class Settings:
    """The app's own settings (`LOBSTER_*`), plus `schwab`."""

    data_dir: Path  # market data recordings
    state_dir: Path  # login token, later the database; outside the repo
    host: str
    port: int
    schwab: SchwabSettings


def load_settings(env_file: Path | None = ENV_FILE, environ: Mapping[str, str] | None = None) -> Settings:
    """Reads settings from `environ` (default: the real environment), then `env_file`."""
    values = {**read_env_file(env_file), **(os.environ if environ is None else environ)}

    def get(name: str, default: str) -> str:
        return values.get(name) or default

    state_dir = _path(get("LOBSTER_STATE_DIR", "~/.lobster"))
    return Settings(
        data_dir=_path(get("LOBSTER_DATA_DIR", "data")),
        state_dir=state_dir,
        host=_local_host(get("LOBSTER_HOST", "127.0.0.1")),
        port=_port(get("LOBSTER_PORT", "8000")),
        schwab=SchwabSettings(
            api_key=_secret(values.get("SCHWAB_API_KEY")),
            app_secret=_secret(values.get("SCHWAB_APP_SECRET")),
            callback_url=get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
            token_path=_path(get("SCHWAB_TOKEN_PATH", str(state_dir / "schwab_token.json"))),
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """The settings, read once on first use."""
    return load_settings()


def _path(text: str) -> Path:
    path = Path(text).expanduser()
    return path if path.is_absolute() else ROOT / path


def _secret(text: str | None) -> Secret | None:
    return Secret(text) if text else None


def _local_host(host: str) -> str:
    if host not in LOCAL_HOSTS:
        raise SettingError(f"LOBSTER_HOST={host!r} would expose the app; it stays local until it has a login")
    return host


def _port(text: str) -> int:
    if not text.isdigit() or not 0 < int(text) < 65536:
        raise SettingError(f"LOBSTER_PORT={text!r} is not a port number")
    return int(text)
