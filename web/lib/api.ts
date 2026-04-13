// In production, the Next.js rewrite (next.config.mjs) proxies /api/* to the
// backend, so NEXT_PUBLIC_API_URL can be omitted. In dev, direct fetch is used.
const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

export const AUTH_STORAGE_KEY = "graph_enterprise_admin_token";
export const AUTH_COOKIE_KEY = "admin_token";
export const AUTH_COOKIE_MAX_AGE_SEC = 60 * 60 * 24;

/** Custom error that preserves the HTTP status code from the API response. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(AUTH_STORAGE_KEY);
}

export function setAdminToken(token: string) {
  sessionStorage.setItem(AUTH_STORAGE_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  clearAdminCookie();
}

function secureCookieFlag(): string {
  if (typeof window === "undefined") return "";
  return window.location.protocol === "https:" ? "; Secure" : "";
}

export function setAdminCookie(token: string) {
  if (typeof document === "undefined") return;
  document.cookie =
    `${AUTH_COOKIE_KEY}=${token}; path=/; SameSite=Strict; Max-Age=${AUTH_COOKIE_MAX_AGE_SEC}` +
    secureCookieFlag();
}

export function clearAdminCookie() {
  if (typeof document === "undefined") return;
  document.cookie = `${AUTH_COOKIE_KEY}=; path=/; SameSite=Strict; Max-Age=0` + secureCookieFlag();
}

function authHeaders(): Record<string, string> {
  const t = typeof window !== "undefined" ? getAdminToken() : null;
  if (t) return { Authorization: `Bearer ${t}` };
  return {};
}

function onUnauthorized() {
  clearAdminToken();
  if (typeof window !== "undefined") window.location.href = "/login";
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const j = await res.json();
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      return j.detail
        .map((x: { msg?: string }) => x.msg)
        .filter(Boolean)
        .join("; ");
    }
    return res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function apiGet<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: { ...authHeaders() },
    ...opts,
  });
  if (r.status === 401) {
    onUnauthorized();
    throw new ApiError("Not authenticated", 401);
  }
  if (!r.ok) throw new ApiError(await errorMessage(r), r.status);
  return r.json() as Promise<T>;
}

export async function apiSend<T>(
  path: string,
  method: string,
  body?: unknown
): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) {
    onUnauthorized();
    throw new ApiError("Not authenticated", 401);
  }
  if (!r.ok) throw new ApiError(await errorMessage(r), r.status);
  if (r.status === 204 || r.headers.get("content-length") === "0") {
    return undefined as T;
  }
  const text = await r.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

/** Public API calls (no Bearer), for login flow. */
export async function apiPublicPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(await errorMessage(r), r.status);
  const text = await r.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export { BASE as apiBaseUrl };
