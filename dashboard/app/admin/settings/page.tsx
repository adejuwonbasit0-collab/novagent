"use client";

import { useEffect, useState } from "react";
import { api, APIError } from "@/lib/api";

export default function AdminSettingsPage() {
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.adminGetAssistantName().then((value) => setName(value.assistant_name)).catch((err) => {
      setError(err instanceof APIError ? err.message : "Could not load assistant name.");
    });
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const value = await api.adminUpdateAssistantName(name.trim());
      setName(value.assistant_name);
      setMessage(`Assistant name changed to ${value.assistant_name}. Restart connected desktop agents to update their wake name.`);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Could not save assistant name.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">Assistant identity</h1>
      <p className="text-muted mb-6">Choose the name every user sees and uses to wake the desktop agent.</p>
      {message && <p className="text-active text-sm border border-active/40 bg-active/10 rounded px-3 py-2 mb-4">{message}</p>}
      {error && <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">{error}</p>}
      <form onSubmit={save} className="card space-y-4">
        <label htmlFor="assistant-name" className="text-sm text-muted">Wake name</label>
        <input id="assistant-name" value={name} onChange={(event) => setName(event.target.value)} className="input-field w-full" minLength={1} maxLength={100} required />
        <p className="text-xs text-muted">Example: if you enter Basit, say “Basit, open Notepad”.</p>
        <button type="submit" disabled={saving} className="btn-primary">{saving ? "Saving…" : "Save assistant name"}</button>
      </form>
    </div>
  );
}