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
      setMessage("AI provider settings saved.");
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