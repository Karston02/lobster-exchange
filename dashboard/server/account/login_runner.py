"""Runs connectors/schwab/login.py from the server, for the page's Log in button.

The script opens Schwab's login page in the browser on this machine and waits
(up to 5 minutes) for you to sign in. It runs as its own process, because
schwab-py starts a temporary web server on 127.0.0.1:8182 to catch Schwab's
redirect, and that shouldn't live inside the app server.

schwab-py prints the full login URL, which contains the API key, so the
script's output is thrown away; the runner reads only its "LOBSTER-LOGIN:"
result line. Once the token file changes, SchwabService notices on its next
request and connects with it; nothing else needs restarting.

This relies on the browser and the server being the same machine. When the app
moves to an always-on server (step 8), the login needs a callback URL on that
server instead (roadmap).
"""

import asyncio
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from config import ROOT

SCRIPT = ROOT / "connectors" / "schwab" / "login.py"
RESULT = "LOBSTER-LOGIN:"
TIMEOUT_S = 330  # the script itself gives up after 300 s

MESSAGES = {
    "timeout": "Schwab's login wasn't finished within 5 minutes. Try again.",
}


@dataclass
class LoginStatus:
    state: str = "idle"  # idle, running, succeeded, failed
    message: str | None = None
    started_at: float | None = None  # Unix seconds


class LoginRunner:
    def __init__(self, command: list[str] | None = None, timeout_s: float = TIMEOUT_S, cwd: Path = ROOT):
        self._command = command or [sys.executable, str(SCRIPT), "--no-prompt"]
        self._timeout_s = timeout_s
        self._cwd = cwd
        self._status = LoginStatus()
        self._task: asyncio.Task | None = None

    def status(self) -> dict:
        return asdict(self._status)

    def start(self) -> dict:
        """Starts a login, unless one is already running (then it just reports on that one)."""
        if self._status.state != "running":
            self._status = LoginStatus(state="running", message="Opening Schwab's login in your browser…", started_at=time.time())
            self._task = asyncio.create_task(self._run())
        return self.status()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                *self._command,
                cwd=self._cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,  # includes the login URL with the API key
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            self._status = LoginStatus("failed", f"Couldn't start the login script ({type(error).__name__}).")
            return
        try:
            _, err = await asyncio.wait_for(process.communicate(), self._timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            self._status = LoginStatus("failed", MESSAGES["timeout"])
            return
        self._status = _result(process.returncode, err.decode(errors="replace"))


def _result(code: int | None, stderr: str) -> LoginStatus:
    lines = [line[len(RESULT) :].strip() for line in stderr.splitlines() if line.startswith(RESULT)]
    result = lines[-1] if lines else None
    if code == 0 and result == "ok":
        return LoginStatus("succeeded", "Logged in. Connecting to Schwab…")
    if result in MESSAGES:
        return LoginStatus("failed", MESSAGES[result])
    if result and result.startswith("error "):
        return LoginStatus("failed", f"Login failed ({result[6:]}). Try again, or run python connectors/schwab/login.py to see more.")
    # No result line: the script didn't get that far (e.g. schwab-py isn't installed)
    return LoginStatus("failed", f"The login script stopped early (exit code {code}). Run python connectors/schwab/login.py to see why.")
