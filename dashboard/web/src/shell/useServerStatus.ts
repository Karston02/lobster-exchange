import { useEffect, useState } from "react";

/** Why Schwab can't be reached, as the server explains it. */
export type SchwabProblem = "no_credentials" | "not_logged_in" | "login_expired" | "error";

/** What GET /api/status reports. Facts only: never keys, tokens or full account numbers. */
export interface ServerStatus {
  schwab: {
    credentials: boolean; // SCHWAB_API_KEY and SCHWAB_APP_SECRET are set
    token_saved: boolean; // a login token file exists
    login_expires_at: string | null; // ISO time; Schwab logins last 7 days
    connected: boolean; // the last account request worked
    problem: SchwabProblem | null;
    message: string | null; // what to do about the problem
    accounts: string[]; // masked, e.g. "…1234"
  };
}

export type StatusState = { kind: "loading" } | { kind: "offline" } | { kind: "online"; status: ServerStatus };

const POLL_MS = 30_000;

/** Asks the server how it's doing now and every 30 seconds. */
export function useServerStatus(): StatusState {
  const [state, setState] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const response = await fetch("/api/status");
        if (!response.ok) throw new Error(`status ${response.status}`);
        const status = (await response.json()) as ServerStatus;
        if (!cancelled) setState({ kind: "online", status });
      } catch {
        if (!cancelled) setState({ kind: "offline" });
      }
    }
    check();
    const timer = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return state;
}
