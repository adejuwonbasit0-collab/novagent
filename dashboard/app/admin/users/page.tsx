"use client";

import { useEffect, useState } from "react";
import { api, AdminUser, APIError } from "@/lib/api";

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Confirmation modal for user deletion
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const data = await api.adminListUsers();
      setUsers(data);
      setError(null);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load user list.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const toggleStatus = async (user: AdminUser) => {
    setBusyId(user.id);
    setError(null);
    try {
      const newStatus = user.status === "suspended" ? "active" : "suspended";
      await api.adminUpdateUser(user.id, { status: newStatus });
      await loadUsers();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to update user status.");
    } finally {
      setBusyId(null);
    }
  };

  const toggleRole = async (user: AdminUser) => {
    setBusyId(user.id);
    setError(null);
    try {
      const newRole = user.role === "admin" ? "user" : "admin";
      await api.adminUpdateUser(user.id, { role: newRole });
      await loadUsers();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to change user role.");
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setBusyId(deleteTarget.id);
    setError(null);
    try {
      await api.adminDeleteUser(deleteTarget.id);
      setDeleteTarget(null);
      await loadUsers();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to delete user.");
    } finally {
      setBusyId(null);
    }
  };

  const filteredUsers = (users || []).filter((u) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      u.email.toLowerCase().includes(q) ||
      (u.full_name && u.full_name.toLowerCase().includes(q)) ||
      u.role.toLowerCase().includes(q) ||
      u.status.toLowerCase().includes(q)
    );
  });

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-display tracking-tight text-ink">
            User Management
          </h1>
          <p className="text-muted text-sm mt-1">
            Manage platform accounts, roles, access suspension, and account removal.
          </p>
        </div>

        <button onClick={loadUsers} className="btn-secondary text-xs self-start">
          Refresh Users
        </button>
      </div>

      {error && (
        <div className="p-4 rounded bg-danger/10 border border-danger/30 text-danger text-sm">
          {error}
        </div>
      )}

      {/* Search Bar */}
      <div>
        <input
          type="text"
          placeholder="Filter by email, name, role or status…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="input w-full text-sm font-mono"
        />
      </div>

      {/* User Table / Cards */}
      {loading ? (
        <p className="text-muted font-mono text-sm">Loading users…</p>
      ) : filteredUsers.length === 0 ? (
        <div className="card p-8 text-center text-muted text-sm">No users found.</div>
      ) : (
        <div className="space-y-3">
          {filteredUsers.map((user) => (
            <div key={user.id} className="card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-sm text-ink">{user.email}</p>
                  {user.full_name && (
                    <span className="text-xs text-muted">({user.full_name})</span>
                  )}
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-mono uppercase font-bold ${
                      user.status === "active" ? "bg-active/15 text-active" : "bg-danger/15 text-danger"
                    }`}
                  >
                    {user.status}
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-mono uppercase ${
                      user.role === "admin" || user.role === "super_admin"
                        ? "bg-red-500/20 text-red-400 font-bold"
                        : "bg-panel text-muted border border-border"
                    }`}
                  >
                    {user.role}
                  </span>
                </div>
                <p className="text-xs text-muted font-mono">
                  {user.device_count} registered device{user.device_count === 1 ? "" : "s"} · Joined {formatDate(user.created_at)}
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => toggleRole(user)}
                  disabled={busyId === user.id}
                  className="btn-secondary text-xs px-2.5 py-1.5"
                  title="Toggle Admin / User"
                >
                  {user.role === "admin" ? "Demote to User" : "Make Admin"}
                </button>

                <button
                  onClick={() => toggleStatus(user)}
                  disabled={busyId === user.id}
                  className={`text-xs px-2.5 py-1.5 rounded transition-colors ${
                    user.status === "suspended"
                      ? "bg-active/20 text-active hover:bg-active/30"
                      : "bg-warning/20 text-warning hover:bg-warning/30"
                  }`}
                >
                  {user.status === "suspended" ? "Reactivate" : "Suspend"}
                </button>

                <button
                  onClick={() => setDeleteTarget(user)}
                  disabled={busyId === user.id}
                  className="btn-danger text-xs px-2.5 py-1.5"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="card max-w-md w-full p-6 space-y-4 border-danger/40">
            <h3 className="text-lg font-bold text-danger">Confirm User Deletion</h3>
            <p className="text-sm text-ink">
              Are you sure you want to permanently delete user{" "}
              <strong className="text-ink font-mono">{deleteTarget.email}</strong>?
            </p>
            <p className="text-xs text-muted">
              This action will purge all associated devices, conversation history, and security events. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="btn-secondary text-sm"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={busyId === deleteTarget.id}
                className="btn-danger text-sm"
              >
                {busyId === deleteTarget.id ? "Deleting…" : "Permanently Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
