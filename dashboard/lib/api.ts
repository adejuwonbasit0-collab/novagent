// The browser never holds an access or refresh token. Every authenticated
// call goes to this app's own /api/proxy/* route, which reads the token
// from an httpOnly cookie server-side and forwards it — see
// app/api/proxy/[...path]/route.ts and lib/server-auth.ts. Login/register/
// logout go through their own small routes under /api/auth/* for the same
// reason (login needs to SET the httpOnly cookie, which only a server
// response can do).

export class APIError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

// Same helper as browser-extension/api.js's localIsoWithOffset() -- JS's
// Date.toISOString() always renders UTC, no built-in for "local wall-clock
// time with its own offset" the way Python's datetime.now().astimezone()
// gives for free. Shared shape, kept duplicated rather than as a shared
// package since this is a Next.js app and the extension is a separate
// unbundled target.
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

async function request<T>(method: string, path: string, json?: unknown): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });

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

// ---- Types mirroring backend Pydantic schemas ----

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  assistant_name: string;
  is_email_verified: boolean;
  role: string;
}

export interface Device {
  id: string;
  name: string;
  platform: string;
  app_version: string | null;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string;
}

export interface Permission {
  scope: string;
  granted: boolean;
  risk_level: "low" | "medium" | "high";
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  source_filename: string | null;
  status: "processing" | "ready" | "failed";
  error: string | null;
  char_count: number;
  chunk_count: number;
  created_at: string;
}

export interface Reminder {
  id: string;
  title: string;
  notes: string | null;
  due_at: string;
  timezone: string;
  recurrence_type: string;
  status: string;
  snoozed_until: string | null;
  completed_at: string | null;
  notify_desktop: boolean;
  notify_sound: boolean;
  created_at: string;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  status: string;
  role: string;
  is_email_verified: boolean;
  created_at: string;
  device_count: number;
}

export interface AdminDevice {
  id: string;
  user_id: string;
  user_email: string;
  name: string;
  platform: string;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string;
}

export interface AdminAuditLog {
  id: string;
  user_id: string;
  user_email: string | null;
  device_id: string | null;
  action: string;
  resource: string | null;
  result: string;
  created_at: string;
}

export interface AdminStats {
  total_users: number;
  active_users: number;
  suspended_users: number;
  total_devices: number;
  active_devices: number;
  total_reminders: number;
  audit_log_count_last_24h: number;
}

export interface AIProviderSettings {
  provider: "anthropic" | "openai" | "openrouter" | "groq" | "gemini" | "custom";
  model: string;
  base_url: string | null;
  has_api_key: boolean;
  enabled: boolean;
}

export interface AssistantNameSettings {
  assistant_name: string;
}

export interface VoiceSample {
  id: string;
  original_filename: string;
  duration_seconds: number | null;
  size_bytes: number;
  status: string;
  created_at: string;
}

export interface VoiceProfile {
  id: string;
  name: string;
  provider: string;
  status: string;
  failure_reason: string | null;
  tone_preset: string;
  custom_stability: number;
  custom_similarity: number;
  custom_style: number;
  consent_given: boolean;
  created_at: string;
}

export interface ToolCall {
  tool_name: string;
  result: string;
  data: Record<string, unknown>;
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
  async register(email: string, password: string, fullName?: string) {
    return request<User>("POST", "/api/auth/register", { email, password, full_name: fullName || null });
  },

  async login(email: string, password: string) {
    // Sets the httpOnly cookies server-side; returns no token to us.
    await request<{ ok: true }>("POST", "/api/auth/login", { email, password });
  },

  async logout() {
    await request<{ ok: true }>("POST", "/api/auth/logout");
  },

  async me() {
    return request<User>("GET", "/api/proxy/auth/me");
  },

  async listDevices() {
    return request<Device[]>("GET", "/api/proxy/devices");
  },

  async renameDevice(id: string, name: string) {
    return request<Device>("PATCH", `/api/proxy/devices/${id}`, { name });
  },

  async revokeDevice(id: string) {
    return request<Device>("POST", `/api/proxy/devices/${id}/revoke`);
  },

  async deleteDevice(id: string) {
    return request<void>("DELETE", `/api/proxy/devices/${id}`);
  },

  async listPermissions() {
    return request<Permission[]>("GET", "/api/proxy/permissions");
  },

  async setPermission(scope: string, granted: boolean) {
    return request<Permission>("PUT", `/api/proxy/permissions/${scope}`, { granted });
  },

  async listReminders() {
    return request<Reminder[]>("GET", "/api/proxy/reminders");
  },

  async createReminder(title: string, dueAt: string, notes?: string) {
    return request<Reminder>("POST", "/api/proxy/reminders", { title, due_at: dueAt, notes: notes || null });
  },

  async completeReminder(id: string) {
    return request<Reminder>("PATCH", `/api/proxy/reminders/${id}`, { status: "completed" });
  },

  async deleteReminder(id: string) {
    return request<void>("DELETE", `/api/proxy/reminders/${id}`);
  },

  async adminGetStats() {
    return request<AdminStats>("GET", "/api/proxy/admin/stats");
  },

  async adminListUsers() {
    return request<AdminUser[]>("GET", "/api/proxy/admin/users");
  },

  async adminUpdateUser(id: string, update: { status?: string; role?: string }) {
    return request<AdminUser>("PATCH", `/api/proxy/admin/users/${id}`, update);
  },

  async adminListDevices() {
    return request<AdminDevice[]>("GET", "/api/proxy/admin/devices");
  },

  async adminRevokeDevice(id: string) {
    return request<void>("POST", `/api/proxy/admin/devices/${id}/revoke`);
  },

  async adminListAuditLogs() {
    return request<AdminAuditLog[]>("GET", "/api/proxy/admin/audit-logs");
  },

  async adminGetAIProvider() {
    return request<AIProviderSettings>("GET", "/api/proxy/admin/ai-provider");
  },

  async adminUpdateAIProvider(update: {
    provider: AIProviderSettings["provider"];
    model: string;
    base_url: string | null;
    api_key?: string;
    enabled: boolean;
  }) {
    return request<AIProviderSettings>("PUT", "/api/proxy/admin/ai-provider", update);
  },

  async adminGetAssistantName() {
    return request<AssistantNameSettings>("GET", "/api/proxy/admin/assistant-name");
  },

  async adminUpdateAssistantName(assistant_name: string) {
    return request<AssistantNameSettings>("PUT", "/api/proxy/admin/assistant-name", { assistant_name });
  },

  async uploadVoiceSample(file: File): Promise<VoiceSample> {
    const formData = new FormData();
    formData.append("file", file);
    // No Content-Type set here on purpose — the browser sets it itself
    // with the correct multipart boundary, which the proxy route then
    // passes straight through to the backend.
    const resp = await fetch("/api/proxy/voice/samples", { method: "POST", body: formData });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new APIError(resp.status, err.detail || "Upload failed");
    }
    return resp.json();
  },

  async listVoiceSamples() {
    return request<VoiceSample[]>("GET", "/api/proxy/voice/samples");
  },

  async deleteVoiceSample(id: string) {
    return request<void>("DELETE", `/api/proxy/voice/samples/${id}`);
  },

  async getVoiceProfile() {
    return request<VoiceProfile>("GET", "/api/proxy/voice/profile");
  },

  async trainVoice(voiceName: string, consentGiven: boolean) {
    return request<VoiceProfile>("POST", "/api/proxy/voice/profile/train", {
      voice_name: voiceName,
      consent_given: consentGiven,
    });
  },

  async updateVoiceTone(tonePreset: string, custom?: { stability?: number; similarity?: number; style?: number }) {
    return request<VoiceProfile>("PATCH", "/api/proxy/voice/profile", {
      tone_preset: tonePreset,
      custom_stability: custom?.stability,
      custom_similarity: custom?.similarity,
      custom_style: custom?.style,
    });
  },

  async synthesizeSpeech(text: string, tonePresetOverride?: string): Promise<Blob> {
    const resp = await fetch("/api/proxy/voice/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, tone_preset_override: tonePresetOverride || null }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new APIError(resp.status, err.detail || "Synthesis failed");
    }
    return resp.blob();
  },

  async chat(message: string) {
    // BUG FOUND while adding the knowledge feature: this was the one
    // remaining call site that didn't send client_local_time -- the same
    // fix already applied to the desktop agent (core/api_client.py) and
    // browser extension (api.js). Without it, anything time-relative
    // asked from the dashboard's own chat ("remind me in 20 minutes")
    // would hit the same "model has to guess what time it is" gap.
    return request<ChatResponse>("POST", "/api/proxy/assistant/chat", {
      message,
      client_local_time: localIsoWithOffset(),
    });
  },

  async confirmPending(pendingId: string) {
    return request<ToolCall>("POST", `/api/proxy/assistant/confirm/${pendingId}`);
  },

  async listKnowledgeDocuments() {
    return request<KnowledgeDocument[]>("GET", "/api/proxy/knowledge/documents");
  },

  async createKnowledgeTextDocument(title: string, content: string) {
    return request<KnowledgeDocument>("POST", "/api/proxy/knowledge/documents/text", { title, content });
  },

  async uploadKnowledgeDocument(file: File): Promise<KnowledgeDocument> {
    const formData = new FormData();
    formData.append("file", file);
    // Same pattern as uploadVoiceSample above -- no Content-Type set on
    // purpose, the browser sets the multipart boundary itself.
    const resp = await fetch("/api/proxy/knowledge/documents", { method: "POST", body: formData });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new APIError(resp.status, err.detail || "Upload failed");
    }
    return resp.json();
  },

  async deleteKnowledgeDocument(id: string) {
    return request<void>("DELETE", `/api/proxy/knowledge/documents/${id}`);
  },
};
