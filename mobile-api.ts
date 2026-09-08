import * as SecureStore from "expo-secure-store";

// SecureStore is backed by iOS Keychain / Android Keystore — the correct
// primitive for a native app (not the browser-XSS-exposed localStorage
// concern the dashboard's httpOnly-cookie migration addressed; native
// apps don't have that injected-script attack surface in the same way).

const BACKEND_URL_KEY = "nova_backend_url";
const ACCESS_TOKEN_KEY = "nova_access_token";
const REFRESH_TOKEN_KEY = "nova_refresh_token";

const DEFAULT_BACKEND_URL = "http://localhost:8000";

export class APIError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

// Same fix as dashboard/lib/api.ts and browser-extension/api.js -- JS's
// Date.toISOString() always renders UTC, no built-in for "local wall-clock
// time with its own offset". React Native's JS engine (Hermes/JSC) both
// support the same standard Date getters this relies on, so this is
// identical to the other two, not RN-specific.
function localIsoWithOffset(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const offsetMin = -d.getTimezoneOffset();
  const sign = offsetMin >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMin);
  const offset = `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${offset}`
  );
}

async function getBackendUrl(): Promise<string> {
  return (await SecureStore.getItemAsync(BACKEND_URL_KEY)) || DEFAULT_BACKEND_URL;
}

export async function setBackendUrl(url: string): Promise<void> {
  await SecureStore.setItemAsync(BACKEND_URL_KEY, url);
}

async function getTokens(): Promise<{ access: string | null; refresh: string | null }> {
  const [access, refresh] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  ]);
  return { access, refresh };
}

async function setTokens(access: string, refresh: string): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, access),
    SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refresh),
  ]);
}

async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}

export async function isLoggedIn(): Promise<boolean> {
  const { access } = await getTokens();
  return !!access;
}

async function request<T>(
  method: string,
  path: string,
  { json, auth = true }: { json?: unknown; auth?: boolean } = {}
): Promise<T> {
  const backendUrl = await getBackendUrl();
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (auth) {
    const { access } = await getTokens();
    if (access) headers["Authorization"] = `Bearer ${access}`;
  }

  let resp = await fetch(`${backendUrl}${path}`, {
    method,
    headers,
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });

  if (resp.status === 401 && auth) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      const { access } = await getTokens();
      headers["Authorization"] = `Bearer ${access}`;
      resp = await fetch(`${backendUrl}${path}`, {
        method,
        headers,
        body: json !== undefined ? JSON.stringify(json) : undefined,
      });
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      /* not JSON */
    }
    throw new APIError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

async function tryRefresh(): Promise<boolean> {
  try {
    const { refresh } = await getTokens();
    if (!refresh) return false;
    const data = await request<{ access_token: string; refresh_token: string }>(
      "POST",
      "/api/v1/auth/refresh",
      { json: { refresh_token: refresh }, auth: false }
    );
    await setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    await clearTokens();
    return false;
  }
}

// ---- Types mirroring backend Pydantic schemas ----

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  assistant_name: string;
  is_email_verified: boolean;
}

export interface Reminder {
  id: string;
  title: string;
  notes: string | null;
  due_at: string;
  status: string;
}

export interface ToolCall {
  tool_name: string;
  result: string;
  message: string | null;
  error: string | null;
  pending_id: string | null;
}

export interface ChatResponse {
  reply: string;
  tool_calls: ToolCall[];
}

// ---- API surface ----

export const api = {
  async login(email: string, password: string): Promise<void> {
    const data = await request<{ access_token: string; refresh_token: string }>(
      "POST",
      "/api/v1/auth/login",
      { json: { email, password }, auth: false }
    );
    await setTokens(data.access_token, data.refresh_token);
  },

  async logout(): Promise<void> {
    await clearTokens();
  },

  me: () => request<User>("GET", "/api/v1/auth/me"),

  listReminders: () => request<Reminder[]>("GET", "/api/v1/reminders"),

  createReminder: (title: string, dueAt: string) =>
    request<Reminder>("POST", "/api/v1/reminders", { json: { title, due_at: dueAt, notes: null } }),

  completeReminder: (id: string) =>
    request<Reminder>("PATCH", `/api/v1/reminders/${id}`, { json: { status: "completed" } }),

  // BUG FOUND during audit: this was the fourth and last call site missing
  // client_local_time -- desktop agent, browser extension, and dashboard
  // all had this fixed already; the mobile app was the one left over.
  // Without it, anything time-relative asked from the phone ("remind me
  // in 20 minutes") hits the same "model has to guess what time it is" gap
  // documented in backend/app/services/orchestrator.py.
  chat: (message: string) =>
    request<ChatResponse>("POST", "/api/v1/assistant/chat", {
      json: { message, client_local_time: localIsoWithOffset() },
    }),

  confirmPending: (pendingId: string) => request<ToolCall>("POST", `/api/v1/assistant/confirm/${pendingId}`),
};
