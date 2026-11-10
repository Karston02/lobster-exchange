import type { StatusState } from "./useServerStatus";

export type Tone = "good" | "warn" | "bad" | "unknown";

/** The one-line summary next to the status dot. */
export function summarize(state: StatusState): { label: string; tone: Tone } {
  if (state.kind === "loading") return { label: "Connecting…", tone: "unknown" };
  if (state.kind === "offline") return { label: "Server offline", tone: "bad" };
  const { credentials, token_saved } = state.status.schwab;
  if (!credentials) return { label: "Schwab not set up", tone: "warn" };
  if (!token_saved) return { label: "Schwab needs login", tone: "warn" };
  return { label: "Schwab ready", tone: "good" };
}
