"use client";

import { useEffect, useState } from "react";
import { api, Device, APIError } from "@/lib/api";

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      setDevices(await api.listDevices());
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load devices.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleRevoke(id: string) {
    setBusyId(id);
    try {
      await api.revokeDevice(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to revoke device.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id: string) {
    setBusyId(id);
    try {
      await api.deleteDevice(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to remove device.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Devices</h1>
      <p className="text-muted mb-6">
        Machines running the Nova desktop agent. Revoking a device blocks it immediately, even if
        it&apos;s mid-conversation.
      </p>

      {error && (
        <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      {devices === null ? (
        <p className="text-muted text-sm">Loading…</p>
      ) : devices.length === 0 ? (
        <div className="card">
          <p className="text-muted">
            No devices yet. Install the Nova desktop agent and sign in to connect one.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {devices.map((device) => (
            <div key={device.id} className="card flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="font-medium truncate">{device.name}</p>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-mono uppercase ${
                      device.is_active ? "bg-active/15 text-active" : "bg-danger/15 text-danger"
                    }`}
                  >
                    {device.is_active ? "active" : "revoked"}
                  </span>
                </div>
                <p className="text-xs text-muted font-mono">
                  {device.platform} · id {device.id.slice(0, 8)}
                </p>
                <p className="text-xs text-muted mt-1">Last seen: {formatDate(device.last_seen_at)}</p>
              </div>

              <div className="flex gap-2 shrink-0">
                {device.is_active && (
                  <button
                    onClick={() => handleRevoke(device.id)}
                    disabled={busyId === device.id}
                    className="btn-secondary text-sm"
                  >
                    Revoke
                  </button>
                )}
                <button
                  onClick={() => handleDelete(device.id)}
                  disabled={busyId === device.id}
                  className="btn-danger text-sm"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
