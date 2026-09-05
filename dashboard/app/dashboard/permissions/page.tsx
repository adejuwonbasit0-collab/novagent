"use client";

import { useEffect, useState } from "react";
import { api, Permission, APIError } from "@/lib/api";

const RISK_COLOR: Record<string, string> = {
  low: "text-active",
  medium: "text-pending",
  high: "text-danger",
};

const SCOPE_DESCRIPTIONS: Record<string, string> = {
  FILES_READ: "Read files on connected devices",
  FILES_WRITE: "Create or modify files on connected devices",
  APP_OPEN: "Open applications",
  APP_CLOSE: "Close applications",
  BROWSER_READ: "Read the content of open browser tabs",
  BROWSER_CONTROL: "Navigate, click, and type in the browser",
  EMAIL_SEND: "Send email on your behalf",
  CALENDAR_READ: "Read your calendar",
  CALENDAR_WRITE: "Create or modify calendar events",
  CONTACTS_READ: "Read your contacts",
  CALL_INITIATE: "Start phone calls",
  SYSTEM_LOCK: "Lock a connected device's screen",
  SYSTEM_SHUTDOWN: "Shut down a connected device",
  SCREEN_READ: "See what's on a connected device's screen",
  AUTOMATION_EXECUTE: "Run automations you've created",
  REMINDERS_MANAGE: "Create and manage reminders",
};

export default function PermissionsPage() {
  const [permissions, setPermissions] = useState<Permission[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyScope, setBusyScope] = useState<string | null>(null);

  async function load() {
    try {
      setPermissions(await api.listPermissions());
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load permissions.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function toggle(scope: string, current: boolean) {
    setBusyScope(scope);
    setError(null);
    try {
      const updated = await api.setPermission(scope, !current);
      setPermissions((prev) => prev?.map((p) => (p.scope === scope ? updated : p)) ?? null);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to update permission.");
    } finally {
      setBusyScope(null);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">Permissions</h1>
      <p className="text-muted mb-6">
        What Nova is allowed to do. High-risk actions still ask you to confirm each time, even when
        granted here.
      </p>

      {error && (
        <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      {permissions === null ? (
        <p className="text-muted text-sm">Loading…</p>
      ) : (
        <div className="space-y-2">
          {permissions.map((p) => (
            <div key={p.scope} className="card flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-sm">{SCOPE_DESCRIPTIONS[p.scope] || p.scope}</p>
                  <span className={`text-xs font-mono uppercase ${RISK_COLOR[p.risk_level]}`}>
                    {p.risk_level}
                  </span>
                </div>
                <p className="text-xs text-muted font-mono mt-0.5">{p.scope}</p>
              </div>

              <button
                onClick={() => toggle(p.scope, p.granted)}
                disabled={busyScope === p.scope}
                role="switch"
                aria-checked={p.granted}
                aria-label={`${p.granted ? "Revoke" : "Grant"} ${SCOPE_DESCRIPTIONS[p.scope] || p.scope}`}
                className={`shrink-0 w-11 h-6 rounded-full relative transition-colors disabled:opacity-50 ${
                  p.granted ? "bg-accent" : "bg-border"
                }`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-ink transition-transform ${
                    p.granted ? "translate-x-5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
