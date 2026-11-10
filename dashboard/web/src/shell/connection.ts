import type { StatusState } from "./useServerStatus";

export type Tone = "good" | "warn" | "bad" | "unknown";

const HOUR_MS = 3_600_000;
const WARN_BEFORE_MS = 24 * HOUR_MS; // warn when the login has less than a day left

/** "3 days", "5 hours", or "under an hour" until `iso`. */
export function timeLeft(iso: string, now = Date.now()): string {
  const ms = new Date(iso).getTime() - now;
  if (ms < HOUR_MS) return "under an hour";
  if (ms < 2 * 24 * HOUR_MS) return `${Math.floor(ms / HOUR_MS)} hours`;
  return `${Math.floor(ms / (24 * HOUR_MS))} days`;
}

/** The one-line summary next to the status dot. */
export function summarize(
  state: StatusState,
  now = Date.now(),
): { label: string; tone: Tone } {
  if (state.kind === "loading")
    return { label: "Connecting…", tone: "unknown" };
  if (state.kind === "offline") return { label: "Server offline", tone: "bad" };
  const schwab = state.status.schwab;
  switch (schwab.problem) {
    case "no_credentials":
      return { label: "Schwab not set up", tone: "warn" };
    case "not_logged_in":
      return { label: "Schwab needs login", tone: "warn" };
    case "login_expired":
      return { label: "Schwab login expired", tone: "bad" };
    case "error":
      return { label: "Schwab unreachable", tone: "bad" };
  }
  const expires = schwab.login_expires_at;
  if (expires && new Date(expires).getTime() - now < WARN_BEFORE_MS) {
    return {
      label: `Schwab login ends in ${timeLeft(expires, now)}`,
      tone: "warn",
    };
  }
  return { label: "Schwab connected", tone: "good" };
}
