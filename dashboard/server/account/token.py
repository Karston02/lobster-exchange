"""How old the Schwab login is, read from schwab-py's token file.

Only the file's `creation_timestamp` is read: the moment of the last full
login, which token refreshes don't change. Schwab ends a login after 7 days,
then you run `python connectors/schwab/login.py` again.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGIN_LIFETIME = timedelta(days=7)


@dataclass(frozen=True)
class TokenStatus:
    saved: bool
    expires_at: datetime | None  # None when there's no readable token

    def expired(self, now: datetime) -> bool:
        return self.expires_at is None or now >= self.expires_at


def token_status(path: Path) -> TokenStatus:
    try:
        created = json.loads(path.read_text())["creation_timestamp"]
    except (OSError, ValueError, KeyError, TypeError):
        return TokenStatus(saved=path.exists(), expires_at=None)
    return TokenStatus(saved=True, expires_at=datetime.fromtimestamp(created, timezone.utc) + LOGIN_LIFETIME)
