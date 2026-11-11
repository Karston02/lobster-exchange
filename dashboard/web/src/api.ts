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

export const getJson = <T>(url: string) => request<T>(url);

/** PUT, POST or DELETE, with an optional JSON body. */
export const sendJson = <T>(method: "PUT" | "POST" | "DELETE", url: string, body?: unknown) =>
  request<T>(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
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
