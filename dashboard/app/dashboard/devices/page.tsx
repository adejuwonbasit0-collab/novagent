"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Device, APIError } from "@/lib/api";

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pairingModalOpen, setPairingModalOpen] = useState(false);

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
    <div className="max-w-3xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-display tracking-tight text-ink">Connected Devices</h1>
          <p className="text-muted text-sm mt-1">
            Manage authorized desktop computers, mobile devices, and browser extension instances.
          </p>
        </div>

        <button
          onClick={() => setPairingModalOpen(true)}
          className="btn-primary text-xs self-start"
        >
          ＋ Pair New Device
        </button>
      </div>

      {error && (
        <div className="p-4 rounded bg-danger/10 border border-danger/30 text-danger text-sm flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-xs underline hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {devices === null ? (
        <p className="text-muted text-sm font-mono">Querying active device fleet…</p>
      ) : devices.length === 0 ? (
        <div className="card p-8 text-center space-y-3">
          <p className="text-ink font-semibold">No connected devices found</p>
          <p className="text-muted text-xs max-w-md mx-auto">
            Launch the Nova Native Desktop Agent or Mobile App on your device and log in to link your workstation.
          </p>
          <div className="pt-2">
            <Link href="/dashboard/downloads" className="btn-secondary text-xs">
              Go to Downloads →
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {devices.map((device) => (
            <div key={device.id} className="card p-4 flex items-center justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-lg">
                    {device.platform.toLowerCase().includes("win")
                      ? "💻"
                      : device.platform.toLowerCase().includes("ios") ||
                        device.platform.toLowerCase().includes("android")
                      ? "📱"
                      : "🌐"}
                  </span>
                  <p className="font-semibold text-sm truncate text-ink">{device.name}</p>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-mono uppercase font-bold ${
                      device.is_active ? "bg-active/15 text-active" : "bg-danger/15 text-danger"
                    }`}
                  >
                    {device.is_active ? "ONLINE / ACTIVE" : "REVOKED"}
                  </span>
                </div>
                <p className="text-xs text-muted font-mono">
                  Platform: {device.platform} · Device ID: {device.id.slice(0, 12)}…
                </p>
                <p className="text-xs text-muted">Last heartbeat: {formatDate(device.last_seen_at)}</p>
              </div>

              <div className="flex gap-2 shrink-0">
                {device.is_active && (
                  <button
                    onClick={() => handleRevoke(device.id)}
                    disabled={busyId === device.id}
                    className="btn-secondary text-xs"
                  >
                    Revoke Token
                  </button>
                )}
                <button
                  onClick={() => handleDelete(device.id)}
                  disabled={busyId === device.id}
                  className="btn-danger text-xs"
                >
                  Unpair
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pairing Instructions Modal */}
      {pairingModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="card max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold text-ink">Connect a New Device</h3>
            <div className="space-y-3 text-xs text-muted leading-relaxed">
              <div className="p-3 bg-panel rounded border border-border">
                <p className="font-semibold text-ink mb-1">🖥️ Desktop Agent (Windows / macOS / Linux)</p>
                <p>
                  Launch <code className="text-accent font-mono">python main.py</code> in the <code className="font-mono">desktop-agent/</code> directory or start via <code className="font-mono">start-nova.ps1</code>. Sign in with your dashboard account credentials. The agent will securely store its device token in the OS Keyring.
                </p>
              </div>

              <div className="p-3 bg-panel rounded border border-border">
                <p className="font-semibold text-ink mb-1">🌐 Browser Extension (Chrome / Edge / Brave)</p>
                <p>
                  Load the unpacked extension from <code className="text-accent font-mono">browser-extension/</code> into Chrome Extensions. Click the Nova icon to connect.
                </p>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setPairingModalOpen(false)}
                className="btn-secondary text-sm"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
