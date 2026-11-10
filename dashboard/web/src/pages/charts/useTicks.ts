import { useEffect, useRef } from "react";
import type { Tick } from "./bars";

const MIN_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;

/** Calls `onTick` for each live trade of `symbol` (via /ws/ticks), reconnecting if dropped. */
export function useTicks(symbol: string, onTick: (tick: Tick) => void): void {
  // Keep the latest callback without reconnecting every render
  const callback = useRef(onTick);
  callback.current = onTick;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let retryMs = MIN_RETRY_MS;
    let stopped = false;

    function connect() {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/ws/ticks?symbol=${encodeURIComponent(symbol)}`);
      socket.onopen = () => (retryMs = MIN_RETRY_MS);
      socket.onmessage = (event) => callback.current(JSON.parse(event.data) as Tick);
      socket.onclose = () => {
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
  }, [symbol]);
}
