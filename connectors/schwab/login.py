"""Logs in to Schwab and saves the token the Lobster server uses.

Run it yourself, from the repo root with the venv active:

    python connectors/schwab/login.py

A browser opens on Schwab's login page. Sign in and approve the app; the
browser then lands on https://127.0.0.1:8182 (a certificate warning there is
expected: it's this script's own local listener). The token is saved to
SCHWAB_TOKEN_PATH (default ~/.lobster/schwab_token.json), outside the repo.

Schwab ends a login after 7 days. The top bar says when; run this again then.
"""

from schwab import auth

from connect import get_settings


def main() -> None:
    schwab = get_settings().schwab
    api_key, app_secret = schwab.credentials()
    schwab.token_path.parent.mkdir(parents=True, exist_ok=True)
    auth.client_from_login_flow(
        api_key=api_key,
        app_secret=app_secret,
        callback_url=schwab.callback_url,
        token_path=str(schwab.token_path),
    )
    print(f"Logged in. Token saved to {schwab.token_path}; it lasts 7 days.")


if __name__ == "__main__":
    main()
