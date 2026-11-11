"""The Log in button's runner, with tiny stand-in scripts instead of Schwab."""

import asyncio
import sys

from account.login_runner import LoginRunner


def run(script: str, timeout_s: float = 10) -> dict:
    """Starts a runner on `script` (Python code) and returns its status once it's done."""

    async def scenario():
        runner = LoginRunner(command=[sys.executable, "-c", script], timeout_s=timeout_s)
        first = runner.start()
        assert first["state"] == "running"
        assert runner.start()["started_at"] == first["started_at"]  # a second click doesn't start another
        for _ in range(500):
            if runner.status()["state"] != "running":
                break
            await asyncio.sleep(0.02)
        return runner.status()

    return asyncio.run(scenario())


OUT = "import sys; print('banner with https://api.schwabapi.com/?client_id=MY-SECRET-KEY')"


def test_success():
    status = run(OUT + "; print('LOBSTER-LOGIN: ok', file=sys.stderr)")

    assert status["state"] == "succeeded"


def test_timeout_and_errors_are_explained():
    timeout = run(OUT + "; print('LOBSTER-LOGIN: timeout', file=sys.stderr); sys.exit(2)")
    error = run(OUT + "; print('LOBSTER-LOGIN: error ValueError', file=sys.stderr); sys.exit(1)")
    crashed = run("raise SystemExit(3)")

    assert timeout["state"] == "failed" and "5 minutes" in timeout["message"]
    assert error["state"] == "failed" and "ValueError" in error["message"]
    assert crashed["state"] == "failed" and "exit code 3" in crashed["message"]


def test_the_scripts_output_never_reaches_the_status():
    status = run(OUT + "; print('traceback ... client_id=MY-SECRET-KEY', file=sys.stderr); sys.exit(1)")

    assert "MY-SECRET-KEY" not in str(status)


def test_a_login_left_open_too_long_is_stopped():
    status = run("import time; time.sleep(30)", timeout_s=0.5)

    assert status["state"] == "failed" and "5 minutes" in status["message"]
