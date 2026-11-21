// Thin fetch wrapper. All paths are relative (/api/...): Vite proxies them in development and
// nginx in Docker, so signed file URLs, images and GLBs share the page's origin.

const TOKEN_KEY = "naqshkaar.token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null): void {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(ApiError.describe(detail) || `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
  static describe(detail: unknown): string {
    if (!detail) return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d: { loc?: unknown[]; msg?: string }) =>
        `${(d.loc || []).filter((x) => x !== "body").join(".")}: ${d.msg}`).join("; ");
    }
    const d = detail as { message?: string; failed?: { label: string; detail: string }[]; problems?: string[] };
    const parts = [d.message];
    if (d.failed) parts.push(d.failed.map((f) => `${f.label}: ${f.detail}`).join("; "));
    if (d.problems) parts.push(d.problems.join("; "));
    return parts.filter(Boolean).join(" — ");
  }
}

let onUnauthorised: () => void = () => {};
export function setUnauthorisedHandler(fn: () => void) { onUnauthorised = fn; }

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? (() => { try { return JSON.parse(text); } catch { return text; } })() : undefined;
  if (!res.ok) {
    if (res.status === 401 && !path.endsWith("/auth/login")) onUnauthorised();
    throw new ApiError(res.status, data && typeof data === "object" && "detail" in data ? data.detail : data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, form),
};

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") s.set(k, String(v)); });
  const out = s.toString();
  return out ? `?${out}` : "";
}
