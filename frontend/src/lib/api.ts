// The one place JSON requests are made and a 401 is noticed. Cookies ride along on
// same-origin fetches by default, so nothing here handles tokens; when the server says the
// session is gone, the registered handler flips the app back to sign-in.

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export function notifyUnauthorized(): void {
  unauthorizedHandler?.();
}

/** FastAPI's `detail`, whether a string or a list of validation errors. */
export async function readDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : ""))
        .filter(Boolean)
        .join(" ");
    }
  } catch {
    // Not JSON; fall through to the status text.
  }
  return res.statusText;
}

export interface JsonInit {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
}

/** Fetch JSON, throwing `ApiError` on a non-2xx status. A 204 resolves to `undefined`. */
export async function fetchJson<T>(url: string, init: JsonInit = {}): Promise<T> {
  const res = await fetch(url, {
    method: init.method ?? "GET",
    headers: init.body === undefined ? undefined : { "content-type": "application/json" },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (res.status === 401) notifyUnauthorized();
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
