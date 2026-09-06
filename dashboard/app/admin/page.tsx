"use client";

import { useEffect, useState } from "react";
import { api, AdminUser, AdminDevice, AdminAuditLog, AdminStats, APIError } from "@/lib/api";

type Tab = "users" | "devices" | "logs";

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminGetStats().then(setStats).catch(() => {});
  }, []);

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold mb-1">Admin</h1>
      <p className="text-muted mb-6">Platform-wide user, device, and activity oversight.</p>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard label="Active users" value={stats.active_users} />
          <StatCard label="Suspended" value={stats.suspended_users} accent="danger" />
          <StatCard label="Active devices" value={stats.active_devices} />
          <StatCard label="Actions (24h)" value={stats.audit_log_count_last_24h} />
        </div>
      )}

      {error && (
        <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      <div className="flex gap-2 mb-4 border-b border-border">
        {(["users", "devices", "logs"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize border-b-2 -mb-px ${
              tab === t ? "border-accent text-accent" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "users" && <UsersTab onError={setError} />}
      {tab === "devices" && <DevicesTab onError={setError} />}
      {tab === "logs" && <LogsTab onError={setError} />}
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: "danger" }) {
  return (
    <div className="card">
      <p className="text-muted text-xs mb-1">{label}</p>
      <p className={`text-2xl font-display font-bold ${accent === "danger" && value > 0 ? "text-danger" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function UsersTab({ onError }: { onError: (e: string | null) => void }) {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      setUsers(await api.adminListUsers());
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Failed to load users.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleSuspend(u: AdminUser) {
    setBusyId(u.id);
    onError(null);
    try {
      await api.adminUpdateUser(u.id, { status: u.status === "suspended" ? "active" : "suspended" });
      await load();
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Failed to update user.");
    } finally {
      setBusyId(null);
    }
  }

  if (users === null) return <p className="text-muted text-sm">Loading…</p>;

  return (
    <div className="space-y-2">
      {users.map((u) => (
        <div key={u.id} className="card flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium text-sm truncate">{u.email}</p>
              <span
                className={`text-xs px-2 py-0.5 rounded font-mono uppercase ${
                  u.status === "active" ? "bg-active/15 text-active" : "bg-danger/15 text-danger"
                }`}
              >
                {u.status}
              </span>
              {u.role !== "user" && (
                <span className="text-xs px-2 py-0.5 rounded font-mono uppercase bg-accent/15 text-accent">
                  {u.role}
                </span>
              )}
            </div>
            <p className="text-xs text-muted font-mono mt-0.5">
              {u.device_count} device{u.device_count === 1 ? "" : "s"} · joined {formatDate(u.created_at)}
            </p>
          </div>
          <button
            onClick={() => toggleSuspend(u)}
            disabled={busyId === u.id}
            className={u.status === "suspended" ? "btn-secondary text-sm shrink-0" : "btn-danger text-sm shrink-0"}
          >
            {u.status === "suspended" ? "Reactivate" : "Suspend"}
          </button>
        </div>
      ))}
    </div>
  );
}

function DevicesTab({ onError }: { onError: (e: string | null) => void }) {
  const [devices, setDevices] = useState<AdminDevice[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      setDevices(await api.adminListDevices());
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Failed to load devices.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function revoke(id: string) {
    setBusyId(id);
    onError(null);
    try {
      await api.adminRevokeDevice(id);
      await load();
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Failed to revoke device.");
    } finally {
      setBusyId(null);
    }
  }

  if (devices === null) return <p className="text-muted text-sm">Loading…</p>;

  return (
    <div className="space-y-2">
      {devices.map((d) => (
        <div key={d.id} className="card flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium text-sm truncate">{d.name}</p>
              <span
                className={`text-xs px-2 py-0.5 rounded font-mono uppercase ${
                  d.is_active ? "bg-active/15 text-active" : "bg-danger/15 text-danger"
                }`}
              >
                {d.is_active ? "active" : "revoked"}
              </span>
            </div>
            <p className="text-xs text-muted font-mono mt-0.5">
              {d.user_email} · {d.platform} · last seen {formatDate(d.last_seen_at)}
            </p>
          </div>
          {d.is_active && (
            <button
              onClick={() => revoke(d.id)}
              disabled={busyId === d.id}
              className="btn-danger text-sm shrink-0"
            >
              Revoke
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function LogsTab({ onError }: { onError: (e: string | null) => void }) {
  const [logs, setLogs] = useState<AdminAuditLog[] | null>(null);

  useEffect(() => {
    api
      .adminListAuditLogs()
      .then(setLogs)
      .catch((err) => onError(err instanceof APIError ? err.message : "Failed to load audit logs."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (logs === null) return <p className="text-muted text-sm">Loading…</p>;

  return (
    <div className="space-y-1">
      {logs.map((log) => (
        <div key={log.id} className="card flex items-center justify-between gap-4 py-2">
          <div className="min-w-0 flex items-center gap-3">
            <span
              className={`text-xs px-2 py-0.5 rounded font-mono uppercase shrink-0 ${
                log.result === "SUCCESS"
                  ? "bg-active/15 text-active"
                  : log.result === "DENIED"
                  ? "bg-pending/15 text-pending"
                  : "bg-danger/15 text-danger"
              }`}
            >
              {log.result}
            </span>
            <p className="text-sm font-mono truncate">{log.action}</p>
            <p className="text-xs text-muted truncate">{log.user_email || log.user_id}</p>
          </div>
          <p className="text-xs text-muted font-mono shrink-0">{formatDate(log.created_at)}</p>
        </div>
      ))}
      {logs.length === 0 && <p className="text-muted text-sm">No activity yet.</p>}
    </div>
  );
}
