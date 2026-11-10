"""Tests for the settings. Run from the repo root: pytest config

They never touch the real environment or `.env`: each test passes its own.
"""

from pathlib import Path

import pytest

from config import ROOT, SettingError, load_settings


def load(environ: dict[str, str] | None = None, env_file: Path | None = None):
    return load_settings(env_file=env_file, environ=environ or {})


def write_env(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_defaults_keep_everything_local_and_outside_the_repo():
    settings = load()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.data_dir == ROOT / "data"
    assert settings.state_dir == Path.home() / ".lobster"
    assert settings.schwab.token_path == Path.home() / ".lobster" / "schwab_token.json"


def test_reads_the_env_file(tmp_path):
    env = write_env(tmp_path, "# comment\nLOBSTER_PORT=9000\nSCHWAB_API_KEY=key\nSCHWAB_APP_SECRET='secret'\n")
    settings = load(env_file=env)

    assert settings.port == 9000
    assert settings.schwab.credentials() == ("key", "secret")


def test_environment_variables_beat_the_env_file(tmp_path):
    env = write_env(tmp_path, "LOBSTER_PORT=9000\n")

    assert load({"LOBSTER_PORT": "9100"}, env_file=env).port == 9100


def test_a_missing_env_file_is_fine(tmp_path):
    assert load(env_file=tmp_path / "nope.env").port == 8000


def test_relative_paths_count_from_the_repo_root_and_tilde_is_home():
    settings = load({"LOBSTER_DATA_DIR": "recordings", "LOBSTER_STATE_DIR": "~/lobster-state"})

    assert settings.data_dir == ROOT / "recordings"
    assert settings.schwab.token_path == Path.home() / "lobster-state" / "schwab_token.json"


def test_an_explicit_token_path_wins():
    settings = load({"SCHWAB_TOKEN_PATH": "/elsewhere/token.json"})

    assert settings.schwab.token_path == Path("/elsewhere/token.json")


def test_secrets_never_show_up_when_printed():
    settings = load({"SCHWAB_API_KEY": "my-real-key", "SCHWAB_APP_SECRET": "my-real-secret"})

    for text in (str(settings), repr(settings), f"{settings.schwab.api_key}"):
        assert "my-real-key" not in text
        assert "my-real-secret" not in text


def test_missing_credentials_fail_only_when_needed():
    settings = load()  # loading works without them

    with pytest.raises(SettingError):
        settings.schwab.credentials()


def test_refuses_to_listen_beyond_this_machine():
    with pytest.raises(SettingError):
        load({"LOBSTER_HOST": "0.0.0.0"})


@pytest.mark.parametrize("port", ["abc", "0", "70000", "-1"])
def test_rejects_bad_ports(port):
    with pytest.raises(SettingError):
        load({"LOBSTER_PORT": port})
