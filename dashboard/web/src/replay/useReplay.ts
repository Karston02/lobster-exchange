import { useCallback, useEffect, useRef, useState } from "react";
import type { Done, FillMessage, Hello, ReplaySettings, ServerMessage, Tick } from "./types";

/** How many points of history to keep for the charts (one per second). */
const MAX_POINTS = 3600;
const MAX_FILLS = 200;

export interface History {
  t: number[];
  mid: number[];
  pnl: number[];
  position: number[];
}

export type Status = "idle" | "connecting" | "running" | "paused" | "done" | "error";

const emptyHistory = (): History => ({ t: [], mid: [], pnl: [], position: [] });

/** Keeps the last `max` items of `items` after appending `more`. */
function appendCapped<T>(items: T[], more: T[], max: number): T[] {
  const next = items.concat(more);
  return next.length > max ? next.slice(next.length - max) : next;
}

/** Connects to the replay websocket and turns its messages into React state. */
export function useReplay() {
  const socket = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [hello, setHello] = useState<Hello | null>(null);
  const [tick, setTick] = useState<Tick | null>(null);
  const [history, setHistory] = useState<History>(emptyHistory);
  const [fills, setFills] = useState<FillMessage[]>([]);
  const [done, setDone] = useState<Done | null>(null);

  const stop = useCallback(() => {
    socket.current?.close();
    socket.current = null;
  }, []);

  const start = useCallback(
    (settings: ReplaySettings) => {
      stop();
      setStatus("connecting");
      setError(null);
      setHello(null);
      setTick(null);
      setHistory(emptyHistory());
      setFills([]);
      setDone(null);

      const query = new URLSearchParams(
        Object.entries(settings).map(([key, value]) => [key, String(value)]),
      );
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws/replay?${query}`);
      socket.current = ws;

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data) as ServerMessage;
        switch (message.type) {
          case "hello":
            setHello(message);
            setStatus("running");
            break;
          case "tick":
            setTick(message);
            if (message.mid !== null && message.pnl_usd !== null) {
              const mid = message.mid;
              const pnl = message.pnl_usd;
              setHistory((h) => ({
                t: appendCapped(h.t, [message.t], MAX_POINTS),
                mid: appendCapped(h.mid, [mid], MAX_POINTS),
                pnl: appendCapped(h.pnl, [pnl], MAX_POINTS),
                position: appendCapped(h.position, [message.position], MAX_POINTS),
              }));
            }
            if (message.fills.length > 0) {
              setFills((f) => appendCapped(f, message.fills, MAX_FILLS));
            }
            break;
          case "done":
            setDone(message);
            setStatus("done");
            break;
          case "error":
            setError(message.message);
            setStatus("error");
            break;
        }
      };
      ws.onerror = () => {
        setError("could not reach the server; is dashboard/server/app.py running?");
        setStatus("error");
      };
      ws.onclose = () => {
        if (socket.current === ws) socket.current = null;
        setStatus((s) => (s === "running" || s === "paused" || s === "connecting" ? "idle" : s));
      };
    },
    [stop],
  );

  const send = useCallback((message: object) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify(message));
    }
  }, []);

  const pause = useCallback(() => {
    send({ type: "pause" });
    setStatus("paused");
  }, [send]);

  const resume = useCallback(() => {
    send({ type: "resume" });
    setStatus("running");
  }, [send]);

  const setSpeed = useCallback((value: number) => send({ type: "speed", value }), [send]);

  // Close the connection when the page goes away
  useEffect(() => stop, [stop]);

  return { status, error, hello, tick, history, fills, done, start, stop, pause, resume, setSpeed };
}
