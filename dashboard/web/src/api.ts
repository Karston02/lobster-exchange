// Fetching JSON from the Lobster server, with errors the page can explain.

/** A failed request. `reason` and `message` come from the server when it gave them. */
export class ApiError extends Error {
  constructor(
    readonly status: number, // 0 when the server couldn't be reached at all
    message: string,
    readonly reason?: string,
  ) {
    super(message);
  }
}

export async function getJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ApiError(0, "The Lobster server isn't running. Start it with: python dashboard/server/app.py");
  }
  if (!response.ok) {
    // FastAPI puts error details under "detail": a string, or {reason, message} for Schwab
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === "object") throw new ApiError(response.status, detail.message, detail.reason);
    throw new ApiError(response.status, typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}
