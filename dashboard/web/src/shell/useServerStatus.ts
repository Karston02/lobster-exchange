import { useEffect, useState } from "react";

/** What GET /api/status reports. Never contains secrets, only yes/no facts. */
export interface ServerStatus {
  schwab: {
    credentials: boolean; // SCHWAB_API_KEY and SCHWAB_APP_SECRET are set
    token_saved: boolean; // a login token file exists (it may still be expired)
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
