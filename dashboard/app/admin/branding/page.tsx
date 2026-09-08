"use client";

import { useEffect, useState } from "react";
import { api, PlatformBranding, APIError } from "@/lib/api";

export default function AdminBrandingPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [formData, setFormData] = useState<PlatformBranding>({
    site_name: "Nova",
    site_description: "Personal AI Operating Assistant Platform",
    logo_url: "/logo.svg",
    favicon_url: "/favicon.ico",
    primary_icon_url: null,
    desktop_icon_url: null,
    mobile_icon_url: null,
    footer_text: "© 2026 Nova Assistant Platform. All rights reserved.",
    seo_title: "Nova — Personal AI Operating Assistant",
    seo_description: "Nova is a unified AI operating assistant across desktop, browser, and mobile.",
    theme: "dark",
    accent_color: "#6366f1",
    assistant_name: "Nova",
    assistant_greeting: "Hello! How can I assist you today?",
    assistant_personality:
      "You are Nova, an efficient, trustworthy, concise, and helpful personal AI operating assistant.",
    default_language: "en-US",
    default_voice: "neutral",
  });

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await api.adminGetPlatformBranding();
        setFormData(data);
      } catch (err) {
        setError(err instanceof APIError ? err.message : "Failed to load platform settings.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const updated = await api.adminUpdatePlatformBranding(formData);
      setFormData(updated);
      setSuccess(
        "Platform branding and assistant settings updated! Live synchronization broadcasted across connected Desktop and Mobile agents."
      );
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to save platform settings.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-muted font-mono text-sm">Loading platform branding…</p>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold font-display tracking-tight text-ink">
          Platform Branding & CMS
        </h1>
        <p className="text-muted text-sm mt-1">
          Customize site branding, SEO metadata, theme accents, assistant personality, and default voice. Changes sync live across the desktop agent and mobile app.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded bg-danger/10 border border-danger/30 text-danger text-sm">
          {error}
        </div>
      )}

      {success && (
        <div className="p-4 rounded bg-active/10 border border-active/30 text-active text-sm">
          {success}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Section 1: Platform & Site Identity */}
        <div className="card p-6 space-y-4">
          <h2 className="text-base font-semibold border-b border-border pb-2">
            General Site Identity & SEO
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">Site / App Name</label>
              <input
                type="text"
                name="site_name"
                value={formData.site_name}
                onChange={handleChange}
                required
                className="input w-full text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Site Description</label>
              <input
                type="text"
                name="site_description"
                value={formData.site_description}
                onChange={handleChange}
                required
                className="input w-full text-sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">SEO Title</label>
              <input
                type="text"
                name="seo_title"
                value={formData.seo_title || ""}
                onChange={handleChange}
                className="input w-full text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">SEO Description</label>
              <input
                type="text"
                name="seo_description"
                value={formData.seo_description || ""}
                onChange={handleChange}
                className="input w-full text-sm font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">Logo URL</label>
              <input
                type="text"
                name="logo_url"
                value={formData.logo_url || ""}
                onChange={handleChange}
                placeholder="/logo.svg"
                className="input w-full text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Favicon URL</label>
              <input
                type="text"
                name="favicon_url"
                value={formData.favicon_url || ""}
                onChange={handleChange}
                placeholder="/favicon.ico"
                className="input w-full text-sm font-mono"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">Footer Copyright Text</label>
            <input
              type="text"
              name="footer_text"
              value={formData.footer_text || ""}
              onChange={handleChange}
              className="input w-full text-sm"
            />
          </div>
        </div>

        {/* Section 2: Assistant Personality & Live Synchronization */}
        <div className="card p-6 space-y-4">
          <h2 className="text-base font-semibold border-b border-border pb-2">
            Assistant Persona & Voice Defaults
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Assistant Name / Wake Word
              </label>
              <input
                type="text"
                name="assistant_name"
                value={formData.assistant_name}
                onChange={handleChange}
                required
                className="input w-full text-sm"
              />
              <p className="text-[11px] text-muted mt-1">
                Trigger name for voice wake and title in desktop agent.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Default Voice ID / Name</label>
              <input
                type="text"
                name="default_voice"
                value={formData.default_voice}
                onChange={handleChange}
                placeholder="neutral or en-US-JennyNeural"
                className="input w-full text-sm font-mono"
              />
              <p className="text-[11px] text-muted mt-1">
                Default TTS voice identifier.
              </p>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">Assistant Greeting</label>
            <input
              type="text"
              name="assistant_greeting"
              value={formData.assistant_greeting}
              onChange={handleChange}
              className="input w-full text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Assistant Personality / System Prompt
            </label>
            <textarea
              name="assistant_personality"
              rows={4}
              value={formData.assistant_personality}
              onChange={handleChange}
              className="input w-full text-sm font-mono leading-relaxed"
            />
          </div>
        </div>

        {/* Section 3: Theme & Visual Accents */}
        <div className="card p-6 space-y-4">
          <h2 className="text-base font-semibold border-b border-border pb-2">
            Theme & Visual Accents
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">Theme</label>
              <select
                name="theme"
                value={formData.theme}
                onChange={handleChange}
                className="input w-full text-sm"
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="system">System Default</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Accent Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  name="accent_color"
                  value={formData.accent_color || "#6366f1"}
                  onChange={handleChange}
                  className="w-8 h-8 rounded border border-border cursor-pointer bg-transparent"
                />
                <input
                  type="text"
                  name="accent_color"
                  value={formData.accent_color || "#6366f1"}
                  onChange={handleChange}
                  className="input w-full text-xs font-mono uppercase"
                />
              </div>
            </div>
          </div>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="btn-primary w-full py-2.5 text-sm font-medium"
        >
          {saving ? "Saving & Syncing with Agents…" : "Save Changes & Broadcast to Agents"}
        </button>
      </form>
    </div>
  );
}
