import { useEffect, useState } from "react";
import { getJson, sendJson } from "../api";
import type { LoginStatus, ServerStatus } from "./useServerStatus";

const WATCH_MS = 2_000; // how often to check while a login is in progress

/** Starts Schwab's login (the server runs connectors/schwab/login.py, which opens
 *  Schwab's page in your browser). You sign in there; this follows along. */
export function LoginButton() {
  const [login, setLogin] = useState<LoginStatus | null>(null);
  const running = login?.state === "running";

  // While a login runs, check on it every couple of seconds
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await getJson<ServerStatus>("/api/status");
        setLogin(status.schwab.login);
      } catch {
        // the server restarting mid-login; keep waiting
      }
    }, WATCH_MS);
    return () => window.clearInterval(timer);
  }, [running]);

  async function start() {
    try {
      setLogin(await sendJson<LoginStatus>("POST", "/api/schwab/login", {}));
    } catch (error) {
      setLogin({ state: "failed", message: (error as Error).message, started_at: null });
    }
  }

  return (
    <div className="login">
      <button type="button" className="login-button" onClick={start} disabled={running}>
        {running ? "Waiting for Schwab…" : "Log in to Schwab"}
      </button>
      {login?.message && (
        <p className={`login-note ${login.state === "failed" ? "loss" : "quiet"}`} role="status">
          {login.state === "running" ? "Sign in on the Schwab page that opened, then approve the app." : login.message}
        </p>
      )}
    </div>
  );
}

/** Whether a Schwab problem is one a login fixes. */
export const needsLogin = (reason: string | null | undefined) => reason === "not_logged_in" || reason === "login_expired";
