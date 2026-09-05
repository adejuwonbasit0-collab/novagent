"use client";

import { useEffect, useState } from "react";
import { api, Reminder, APIError } from "@/lib/api";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default function RemindersPage() {
  const [reminders, setReminders] = useState<Reminder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    try {
      setReminders(await api.listReminders());
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load reminders.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !dueAt) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createReminder(title.trim(), new Date(dueAt).toISOString());
      setTitle("");
      setDueAt("");
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to create reminder.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleComplete(id: string) {
    try {
      await api.completeReminder(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to update reminder.");
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteReminder(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to delete reminder.");
    }
  }

  const pending = reminders?.filter((r) => r.status === "pending") ?? [];
  const other = reminders?.filter((r) => r.status !== "pending") ?? [];

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Reminders</h1>
      <p className="text-muted mb-6">Ordered by when they&apos;re due.</p>

      {error && (
        <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      <form onSubmit={handleCreate} className="card flex flex-wrap gap-3 items-end mb-6">
        <div className="flex-1 min-w-[200px] space-y-1">
          <label htmlFor="title" className="text-sm text-muted">
            Title
          </label>
          <input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="input-field w-full"
            placeholder="Submit thesis draft"
            required
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="dueAt" className="text-sm text-muted">
            Due
          </label>
          <input
            id="dueAt"
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            className="input-field"
            required
          />
        </div>
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? "Adding…" : "Add reminder"}
        </button>
      </form>

      {reminders === null ? (
        <p className="text-muted text-sm">Loading…</p>
      ) : (
        <div className="space-y-6">
          <section>
            <h2 className="text-sm text-muted uppercase tracking-wide mb-2">Pending</h2>
            {pending.length === 0 ? (
              <p className="text-muted text-sm">Nothing pending.</p>
            ) : (
              <div className="space-y-2">
                {pending.map((r) => (
                  <div key={r.id} className="card flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{r.title}</p>
                      <p className="text-xs text-muted font-mono">{formatDate(r.due_at)}</p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button onClick={() => handleComplete(r.id)} className="btn-secondary text-sm">
                        Complete
                      </button>
                      <button onClick={() => handleDelete(r.id)} className="btn-danger text-sm">
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {other.length > 0 && (
            <section>
              <h2 className="text-sm text-muted uppercase tracking-wide mb-2">Past</h2>
              <div className="space-y-2">
                {other.map((r) => (
                  <div key={r.id} className="card flex items-center justify-between gap-4 opacity-60">
                    <div className="min-w-0">
                      <p className="font-medium truncate line-through">{r.title}</p>
                      <p className="text-xs text-muted font-mono">
                        {formatDate(r.due_at)} · {r.status}
                      </p>
                    </div>
                    <button onClick={() => handleDelete(r.id)} className="btn-danger text-sm shrink-0">
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
