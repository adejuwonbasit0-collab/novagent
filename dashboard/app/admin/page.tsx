"use client";

import { useEffect, useState } from "react";
import { api, AdminUser, AdminDevice, AdminAuditLog, AdminStats, APIError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Tab = "users" | "devices" | "logs";

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

export default function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("users");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminGetStats().then(setStats).catch(() => {});
  }, []);

  // The /admin layout's useRequireAdmin already redirects non-admins away,
  // and the server independently 403s any non-admin call — this is just a
  // friendlier message in the brief window before that redirect fires.
  if (user && user.role !== "admin" && user.role !== "super_admin") {
    return (
      <div className="max-w-2xl">
        <h1 className="text-2xl font-bold mb-2">Admin</h1>
        <p className="text-muted">You don&apos;t have access to this section.</p>
      </div>
    );
  }

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
    <div className="card py-3">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className={`text-2xl font-display font-bold ${accent === "danger" ? "text-danger" : ""}`}>{value}</p>
    </div>
  );
}

function UsersTab({ onError }: { onError: (message: string | null) => void }) {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      setUsers(await api.adminListUsers());
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Could not load users.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function update(id: string, patch: { status?: string; role?: string }) {
    setBusyId(id);
    onError(null);
    try {
      const updated = await api.adminUpdateUser(id, patch);
      setUsers((prev) => (prev ? prev.map((u) => (u.id === id ? updated : u)) : prev));
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Could not update user.");
    } finally {
      setBusyId(null);
    }
  }

  if (!users) return <p className="text-muted text-sm">Loading…</p>;

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted border-b border-border">
            <th className="py-2 pr-4">Email</th>
            <th className="py-2 pr-4">Role</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pr-4">Joined</th>
            <th className="py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => {
            const isSelf = currentUser?.id === u.id;
            return (
              <tr key={u.id} className="border-b border-border last:border-0">
                <td className="py-2 pr-4">{u.email}</td>
                <td className="py-2 pr-4 capitalize">{u.role.replace("_", " ")}</td>
                <td className="py-2 pr-4 capitalize">{u.status}</td>
                <td className="py-2 pr-4">{formatDate(u.created_at)}</td>
                <td className="py-2 space-x-2">
                  {u.status === "active" ? (
                    <button
                      disabled={isSelf || busyId === u.id}
                      onClick={() => update(u.id, { status: "suspended" })}
                      className="text-danger text-xs disabled:opacity-40"
                    >
                      Suspend
                    </button>
                  ) : (
                    <button
                      disabled={busyId === u.id}
                      onClick={() => update(u.id, { status: "active" })}
                      className="text-active text-xs disabled:opacity-40"
                    >
                      Reactivate
                    </button>
                  )}
                  {u.role === "user" ? (
                    <button
                      disabled={isSelf || busyId === u.id}
                      onClick={() => update(u.id, { role: "admin" })}
                      className="text-accent text-xs disabled:opacity-40"
                    >
                      Make admin
                    </button>
                  ) : u.role === "admin" ? (
                    <button
                      disabled={isSelf || busyId === u.id}
                      onClick={() => update(u.id, { role: "user" })}
                      className="text-muted text-xs disabled:opacity-40"
                    >
                      Remove admin
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DevicesTab({ onError }: { onError: (message: string | null) => void }) {
  const [devices, setDevices] = useState<AdminDevice[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      setDevices(await api.adminListDevices());
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Could not load devices.");
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
      // The revoke endpoint returns no body — reflect the change locally
      // rather than treating a void response as an updated device.
      await api.adminRevokeDevice(id);
      setDevices((prev) => (prev ? prev.map((d) => (d.id === id ? { ...d, is_active: false } : d)) : prev));
    } catch (err) {
      onError(err instanceof APIError ? err.message : "Could not revoke device.");
    } finally {
      setBusyId(null);
    }
  }

  if (!devices) return <p className="text-muted text-sm">Loading…</p>;

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted border-b border-border">
            <th className="py-2 pr-4">Name</th>
            <th className="py-2 pr-4">Owner</th>
            <th className="py-2 pr-4">Platform</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pr-4">Last seen</th>
            <th className="py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((d) => (
            <tr key={d.id} className="border-b border-border last:border-0">
              <td className="py-2 pr-4">{d.name}</td>
              <td className="py-2 pr-4">{d.user_email}</td>
              <td className="py-2 pr-4">{d.platform}</td>
              <td className="py-2 pr-4 capitalize">{d.is_active ? "Active" : "Revoked"}</td>
              <td className="py-2 pr-4">{formatDate(d.last_seen_at)}</td>
              <td className="py-2">
                {d.is_active && (
                  <button
                    disabled={busyId === d.id}
                    onClick={() => revoke(d.id)}
                    className="text-danger text-xs disabled:opacity-40"
                  >
                    Revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LogsTab({ onError }: { onError: (message: string | null) => void }) {
  const [logs, setLogs] = useState<AdminAuditLog[] | null>(null);

  useEffect(() => {
    api.adminListAuditLogs().then(setLogs).catch((err) => {
      onError(err instanceof APIError ? err.message : "Could not load audit logs.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!logs) return <p className="text-muted text-sm">Loading…</p>;

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted border-b border-border">
            <th className="py-2 pr-4">When</th>
            <th className="py-2 pr-4">Actor</th>
            <th className="py-2 pr-4">Action</th>
            <th className="py-2">Result</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id} className="border-b border-border last:border-0">
              <td className="py-2 pr-4 whitespace-nowrap">{formatDate(l.created_at)}</td>
              <td className="py-2 pr-4">{l.user_email ?? "—"}</td>
              <td className="py-2 pr-4">{l.action}{l.resource ? ` · ${l.resource}` : ""}</td>
              <td className="py-2 text-muted capitalize">{l.result}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
