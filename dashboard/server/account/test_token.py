import json
from datetime import datetime, timedelta, timezone

from account.token import token_status

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def test_no_token_file(tmp_path):
    status = token_status(tmp_path / "missing.json")

    assert not status.saved
    assert status.expired(NOW)


def test_login_lasts_seven_days_from_creation(tmp_path):
    path = tmp_path / "token.json"
    created = NOW - timedelta(days=2)
    path.write_text(json.dumps({"creation_timestamp": int(created.timestamp()), "token": {"secret": "x"}}))

    status = token_status(path)

    assert status.saved
    assert status.expires_at == created + timedelta(days=7)
    assert not status.expired(NOW)
    assert status.expired(NOW + timedelta(days=5))


def test_an_unreadable_token_counts_as_expired(tmp_path):
    path = tmp_path / "token.json"
    path.write_text("not json")

    status = token_status(path)

    assert status.saved and status.expires_at is None and status.expired(NOW)
