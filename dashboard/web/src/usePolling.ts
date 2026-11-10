import { useEffect, useState } from "react";
import { ApiError, getJson } from "./api";

export interface Polled<T> {
  data: T | null; // the latest good answer, kept while a later request fails
  error: ApiError | null;
  loading: boolean; // true until the first answer or error
}

/** GETs `url` now and every `everyMs`, skipping while the tab is hidden.
 *  With `enabled` false it stops asking (e.g. while live updates are flowing). */
export function usePolling<T>(url: string, everyMs: number, enabled = true): Polled<T> {
  const [state, setState] = useState<Polled<T>>({ data: null, error: null, loading: true });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    async function load() {
      if (document.hidden) return;
      try {
        const data = await getJson<T>(url);
        if (!cancelled) setState({ data, error: null, loading: false });
      } catch (caught) {
        const error = caught instanceof ApiError ? caught : new ApiError(0, String(caught));
        if (!cancelled) setState((previous) => ({ ...previous, error, loading: false }));
      }
    }
    load();
    const timer = window.setInterval(load, everyMs);
    document.addEventListener("visibilitychange", load); // refresh as soon as the tab comes back
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, [url, everyMs, enabled]);

  return state;
}
