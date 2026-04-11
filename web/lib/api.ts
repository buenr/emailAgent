const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

export const AUTH_STORAGE_KEY = "graph_enterprise_admin_token";

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(AUTH_STORAGE_KEY);
}

export function setAdminToken(token: string) {
  sessionStorage.setItem(AUTH_STORAGE_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
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

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: { ...authHeaders() },
  });
  if (r.status === 401) {
    onUnauthorized();
    throw new Error("Not authenticated");
  }
  if (!r.ok) throw new Error(await errorMessage(r));
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
    throw new Error("Not authenticated");
  }
  if (!r.ok) throw new Error(await errorMessage(r));
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
  if (!r.ok) throw new Error(await errorMessage(r));
  const text = await r.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export { BASE as apiBaseUrl };
