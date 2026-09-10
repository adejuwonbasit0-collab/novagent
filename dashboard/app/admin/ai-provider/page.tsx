"use client";

import { useEffect, useState } from "react";
import { api, AIProviderSettings, APIError } from "@/lib/api";

const PROVIDERS: { value: AIProviderSettings["provider"]; label: string; defaultModel: string; defaultUrl: string }[] = [
  { value: "anthropic", label: "Anthropic Claude", defaultModel: "claude-sonnet-4-20250514", defaultUrl: "https://api.anthropic.com" },
  { value: "openai", label: "OpenAI", defaultModel: "gpt-4o-mini", defaultUrl: "https://api.openai.com/v1" },
  { value: "openrouter", label: "OpenRouter", defaultModel: "openai/gpt-4o-mini", defaultUrl: "https://openrouter.ai/api/v1" },
  { value: "groq", label: "Groq", defaultModel: "llama-3.3-70b-versatile", defaultUrl: "https://api.groq.com/openai/v1" },
  { value: "gemini", label: "Google Gemini", defaultModel: "gemini-2.0-flash", defaultUrl: "https://generativelanguage.googleapis.com" },
  { value: "custom", label: "Custom OpenAI-compatible", defaultModel: "", defaultUrl: "" },
];

const MODELS: Record<AIProviderSettings["provider"], string[]> = {
  anthropic: ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
  openai: ["gpt-4o-mini", "gpt-4o"],
  openrouter: ["openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct:free"],
  groq: ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
  gemini: ["gemini-2.0-flash", "gemini-2.5-flash"],
  custom: [],
};

// BUG FIX / root cause of the recurring "502: AI provider error 401:
// invalid_api_key" report: this page lets you pick a Provider and paste a
// key with nothing checking the two actually match. The backend always
// sends whatever key is saved to whatever provider is selected -- paste
// an Anthropic key (sk-ant-...) while "OpenAI" is still selected (e.g.
// the dropdown reverted after a reload, or you only meant to update the
// key and didn't notice the provider) and it gets sent, unmodified, to
// OpenAI's endpoint. OpenAI correctly rejects it -- the exact error
// being reported -- and nothing on this page ever said why. This is a
// warning, not a hard block: some providers (custom, some OpenRouter
// setups) don't have a fixed prefix, so refusing to save on a guess
// would be worse than a wrong guess here and there.
const KEY_PREFIX_HINTS: Partial<Record<AIProviderSettings["provider"], { prefix: string; label: string }>> = {
  anthropic: { prefix: "sk-ant-", label: "Anthropic" },
  openai: { prefix: "sk-", label: "OpenAI" },
  openrouter: { prefix: "sk-or-", label: "OpenRouter" },
  groq: { prefix: "gsk_", label: "Groq" },
  gemini: { prefix: "AIza", label: "Google Gemini" },
};

function detectMismatch(provider: AIProviderSettings["provider"], key: string): string | null {
  const trimmed = key.trim();
  if (!trimmed) return null;
  // Rank by prefix length (most specific first): an Anthropic key
  // ("sk-ant-...") also starts with OpenAI's generic "sk-" prefix, so a
  // plain "does it start with this" check would match both and this
  // would never fire for the exact case it exists to catch.
  let best: { provider: AIProviderSettings["provider"]; prefix: string; label: string } | null = null;
  for (const [otherProvider, hint] of Object.entries(KEY_PREFIX_HINTS)) {
    if (trimmed.startsWith(hint.prefix) && (!best || hint.prefix.length > best.prefix.length)) {
      best = { provider: otherProvider as AIProviderSettings["provider"], prefix: hint.prefix, label: hint.label };
    }
  }
  if (best && best.provider !== provider) {
    return `This looks like a ${best.label} key, but Provider is set to ${PROVIDERS.find((p) => p.value === provider)?.label}. Switch the provider above, or double-check you copied the right key.`;
  }
  return null;
}

export default function AIProviderPage() {
  const [settings, setSettings] = useState<AIProviderSettings | null>(null);
  const [provider, setProvider] = useState<AIProviderSettings["provider"]>("anthropic");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const keyMismatch = detectMismatch(provider, apiKey);

  useEffect(() => {
    api.adminGetAIProvider().then((value) => {
      setSettings(value);
      setProvider(value.provider);
      setModel(value.model);
      setBaseUrl(value.base_url || "");
      setEnabled(value.enabled);
    }).catch((err) => setError(err instanceof APIError ? err.message : "Could not load AI settings."));
  }, []);

  function chooseProvider(value: AIProviderSettings["provider"]) {
    const option = PROVIDERS.find((item) => item.value === value)!;
    setProvider(value);
    setModel(option.defaultModel);
    setBaseUrl(option.defaultUrl);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const value = await api.adminUpdateAIProvider({
        provider,
        model,
        base_url: baseUrl || null,
        api_key: apiKey || undefined,
        enabled,
      });
      setSettings(value);
      setApiKey("");
      setMessage(
        keyMismatch
          ? "Saved — but double check the provider/key mismatch warning above before testing chat."
          : "AI provider settings saved."
      );
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Could not save AI settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">AI Provider</h1>
      <p className="text-muted mb-6">Choose which model powers Nova&apos;s assistant. Keys are encrypted on the server and never returned to the browser.</p>
      <p className="text-muted text-sm mb-6 border border-white/10 rounded px-3 py-2">
        Once a key is saved here, it&apos;s the only key that gets used — a backend <code>.env</code> key is only a fallback for
        before any key has ever been saved through this page.
      </p>

      {message && <p className="text-active text-sm border border-active/40 bg-active/10 rounded px-3 py-2 mb-4">{message}</p>}
      {error && <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">{error}</p>}

      <form onSubmit={save} className="card space-y-5">
        <div className="space-y-1">
          <label htmlFor="provider" className="text-sm text-muted">Provider</label>
          <select id="provider" value={provider} onChange={(event) => chooseProvider(event.target.value as AIProviderSettings["provider"])} className="input-field w-full">
            {PROVIDERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="model" className="text-sm text-muted">Model</label>
          <select id="model" value={MODELS[provider].includes(model) ? model : "__custom__"} onChange={(event) => setModel(event.target.value === "__custom__" ? "" : event.target.value)} className="input-field w-full">
            {MODELS[provider].map((option) => <option key={option} value={option}>{option}</option>)}
            <option value="__custom__">Custom model name…</option>
          </select>
          {(!MODELS[provider].includes(model) || provider === "custom") && (
            <input value={model} onChange={(event) => setModel(event.target.value)} className="input-field w-full mt-2" placeholder="Enter exact model ID" required />
          )}
        </div>
        <div className="space-y-1">
          <label htmlFor="base-url" className="text-sm text-muted">Base URL</label>
          <input id="base-url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="input-field w-full" placeholder="Provider API URL" />
        </div>
        <div className="space-y-1">
          <label htmlFor="api-key" className="text-sm text-muted">API key</label>
          <input id="api-key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="input-field w-full" placeholder={settings?.has_api_key ? "Key saved, enter a new key to replace it" : "Paste provider key"} autoComplete="new-password" />
          {keyMismatch && (
            <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mt-2">{keyMismatch}</p>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Enable this provider for assistant chat
        </label>
        <button type="submit" disabled={saving} className="btn-primary">{saving ? "Saving…" : "Save provider settings"}</button>
      </form>
    </div>
  );
}