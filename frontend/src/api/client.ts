/**
 * The only module that talks to the network.
 *
 * Tokens: the short-lived ACCESS token lives in memory only. The REFRESH token is kept in
 * localStorage so a reload keeps you signed in. That is a deliberate trade-off: localStorage can
 * be read by any script running on the page (XSS). A production system would move the refresh
 * token into an httpOnly cookie, which needs a small backend change. See "Open risks" in the guide.
 */

const REFRESH_KEY = "sk.refresh";

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
let sessionExpiredHandler: (() => void) | null = null;

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  sessionExpiredHandler = handler;
}

export function storeTokens(access: string, refresh?: string): void {
  accessToken = access;
  if (refresh) {
    try {
      localStorage.setItem(REFRESH_KEY, refresh);
    } catch {
      /* private mode: the session simply will not survive a reload */
    }
  }
}

export function clearTokens(): void {
  accessToken = null;
  try {
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* nothing to clear */
  }
}

export const hasRefreshToken = (): boolean => readRefresh() !== null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly fields: Record<string, string[]>;

  constructor(status: number, message: string, code?: string, fields: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

/**
 * Exchange the refresh token for a new access token. Concurrent callers share ONE request:
 * when a page fires five queries and the token has just expired, all five get a 401 at once, and
 * five refresh calls would race each other.
 */
export function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refresh = readRefresh();
    if (!refresh) return false;
    try {
      const response = await fetch("/api/auth/token/refresh/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (!response.ok) {
        clearTokens();
        return false;
      }
      const data = (await response.json()) as { access: string; refresh?: string };
      storeTokens(data.access, data.refresh);
      return true;
    } catch {
      return false; // network trouble is not proof the session is dead; keep the refresh token
    }
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function toError(response: Response): Promise<ApiError> {
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    /* not JSON (a proxy error page, for example) */
  }
  const body = data !== null && typeof data === "object" ? (data as Record<string, unknown>) : {};
  const detail = typeof body.detail === "string" ? body.detail : undefined;
  const code = typeof body.code === "string" ? body.code : undefined;
  const fields: Record<string, string[]> = {};
  for (const [key, value] of Object.entries(body)) {
    if (key !== "detail" && key !== "code" && Array.isArray(value)) fields[key] = value.map(String);
  }
  const firstField = Object.values(fields)[0]?.[0];
  return new ApiError(response.status, detail ?? firstField ?? `Request failed (${response.status})`, code, fields);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  /** false for login/register, which must not trigger the refresh dance. */
  auth?: boolean;
}

function queryString(query: RequestOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, auth = true } = options;
  const url = `/api${path}${queryString(query)}`;

  const send = (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  };

  let response: Response;
  try {
    response = await send();
    if (response.status === 401 && auth && (await refreshAccessToken())) {
      response = await send(); // retry exactly once with the new token
    }
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.", "network_error");
  }

  if (response.status === 401 && auth) sessionExpiredHandler?.();
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
