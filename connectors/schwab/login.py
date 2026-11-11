"""Logs in to Schwab and saves the token the Lobster server uses.

Run it yourself, from the repo root with the venv active:

    python connectors/schwab/login.py

A browser opens on Schwab's login page. Sign in and approve the app; the
browser then lands on https://127.0.0.1:8182 (a certificate warning there is
expected: it's this script's own local listener). The token is saved to
SCHWAB_TOKEN_PATH (default ~/.lobster/schwab_token.json), outside the repo.

Schwab ends a login after 7 days. The top bar says when; log in again then,
with this script or the Log in button in the app (which runs this script).

    --no-prompt   open the browser straight away instead of waiting for Enter
                  (how the app runs it). The last line on stderr is then a result
                  the app reads: "LOBSTER-LOGIN: ok", "LOBSTER-LOGIN: timeout" or
                  "LOBSTER-LOGIN: error <ExceptionType>".
"""

import argparse
import sys

from schwab import auth

from connect import get_settings

RESULT = "LOBSTER-LOGIN:"  # the only line the app reads; schwab-py's own output includes the API key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-prompt", action="store_true", help="open the browser without waiting for Enter")
    args = parser.parse_args()

    schwab = get_settings().schwab
    try:
        api_key, app_secret = schwab.credentials()
        schwab.token_path.parent.mkdir(parents=True, exist_ok=True)
        client = auth.client_from_login_flow(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=schwab.callback_url,
            token_path=str(schwab.token_path),
            interactive=not args.no_prompt,
        )
        client.session.close()  # only the saved token is needed
    except auth.RedirectTimeoutError:
        print(f"{RESULT} timeout", file=sys.stderr)
        return 2
    except Exception as error:  # the type only: messages can carry URLs with the API key in them
        print(f"{RESULT} error {type(error).__name__}", file=sys.stderr)
        return 1
    print(f"Logged in. Token saved to {schwab.token_path}; it lasts 7 days.")
    print(f"{RESULT} ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
