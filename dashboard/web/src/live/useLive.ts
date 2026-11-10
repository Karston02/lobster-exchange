import { useEffect, useState } from "react";
import type { Account, Portfolio, Quote } from "../account/types";

/** What /ws/live pushes: accounts repriced from the quote stream. Mirrors live/feed.py. */
export interface LiveMessage {
  type: "live";
  as_of: string; // when the server sent it
  streaming: boolean; // false while the quote stream is reconnecting
  accounts: Account[];
  portfolio: Portfolio;
  quotes: Record<string, Quote>; // SPY
}

export interface Live {
  message: LiveMessage | null; // the newest update, kept if the connection drops
  connected: boolean;
}

const MIN_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;

/** Connects to /ws/live and reconnects (waiting longer each time) if it drops. */
export function useLive(): Live {
  const [live, setLive] = useState<Live>({ message: null, connected: false });

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryMs = MIN_RETRY_MS;
    let timer: number | undefined;
    let stopped = false;

    function connect() {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/ws/live`);
      socket.onopen = () => {
        retryMs = MIN_RETRY_MS;
        setLive((previous) => ({ ...previous, connected: true }));
      };
      socket.onmessage = (event) => {
        setLive({ message: JSON.parse(event.data) as LiveMessage, connected: true });
      };
      socket.onclose = () => {
        setLive((previous) => ({ ...previous, connected: false }));
        if (stopped) return;
        timer = window.setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, MAX_RETRY_MS);
      };
    }

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, []);

  return live;
}
