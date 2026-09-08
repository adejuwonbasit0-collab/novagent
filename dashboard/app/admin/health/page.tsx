"use client";

import { useEffect, useState } from "react";
import { api, SystemHealthResponse, APIError } from "@/lib/api";

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / (3600 * 24));
  const h = Math.floor((seconds % (3600 * 24)) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(" ");
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

export default function AdminHealthPage() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchHealth = async () => {
    try {
      const data = await api.getHealth();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to retrieve health metrics.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(() => {
      if (autoRefresh) {
        fetchHealth();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "healthy":
      case "operational":
      case "ready":
      case "connected":
        return <span className="text-xs px-2 py-0.5 rounded font-mono uppercase bg-active/20 text-active font-bold">HEALTHY</span>;
      case "degraded":
      case "warning":
        return <span className="text-xs px-2 py-0.5 rounded font-mono uppercase bg-warning/20 text-warning font-bold">DEGRADED</span>;
      default:
        return <span className="text-xs px-2 py-0.5 rounded font-mono uppercase bg-danger/20 text-danger font-bold">{status}</span>;
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-display tracking-tight text-ink">
            System Health & Telemetry
          </h1>
          <p className="text-muted text-sm mt-1">
            Real-time status diagnostics for database, AI model inference, WebSockets, and storage.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-3.5 h-3.5 rounded"
            />
            Auto-refresh (5s)
          </label>
          <button onClick={fetchHealth} className="btn-secondary text-xs">
            Run Health Probe
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded bg-danger/10 border border-danger/30 text-danger text-sm">
          {error}
        </div>
      )}

      {loading && !health ? (
        <p className="text-muted font-mono text-sm">Gathering platform diagnostics…</p>
      ) : health ? (
        <div className="space-y-6">
          {/* Main Status Banner */}
          <div className="card p-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div
                className={`w-4 h-4 rounded-full ${
                  health.status === "healthy" ? "bg-active animate-pulse" : "bg-danger animate-ping"
                }`}
              />
              <div>
                <p className="text-lg font-bold capitalize">Platform Status: {health.status}</p>
                <p className="text-xs text-muted font-mono mt-0.5">
                  Nova Core Version: {health.version || "1.0.0"} · Uptime: {formatUptime(health.uptime_seconds)}
                </p>
              </div>
            </div>
            <div>{getStatusBadge(health.status)}</div>
          </div>

          {/* Component Diagnostics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Database Card */}
            <div className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <span>🗄️</span> SQLite / PostgreSQL
                </h3>
                {getStatusBadge(health.database.status)}
              </div>
              <div className="bg-panel p-3 rounded text-xs font-mono space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted">Driver Engine:</span>
                  <span className="text-ink">{health.database.driver}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Query Latency:</span>
                  <span className="text-active">{health.database.latency_ms.toFixed(2)} ms</span>
                </div>
              </div>
            </div>

            {/* AI Provider Card */}
            <div className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <span>🧠</span> AI Inference Provider
                </h3>
                {getStatusBadge(health.ai_provider.status)}
              </div>
              <div className="bg-panel p-3 rounded text-xs font-mono space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted">Provider:</span>
                  <span className="text-ink uppercase">{health.ai_provider.provider}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Active Model:</span>
                  <span className="text-ink">{health.ai_provider.model}</span>
                </div>
              </div>
            </div>

            {/* WebSocket Broker Card */}
            <div className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <span>⚡</span> WebSocket Connection Bus
                </h3>
                {getStatusBadge(health.websocket.status)}
              </div>
              <div className="bg-panel p-3 rounded text-xs font-mono space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted">Live Agent Sockets:</span>
                  <span className="text-active font-bold">{health.websocket.active_connections}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Sync Broadcast:</span>
                  <span className="text-ink">Enabled (FastAPI + AsyncIO)</span>
                </div>
              </div>
            </div>

            {/* Voice & Speech Card */}
            <div className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <span>🎙️</span> Voice Pipeline
                </h3>
                {getStatusBadge(health.voice.status)}
              </div>
              <div className="bg-panel p-3 rounded text-xs font-mono space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted">Engine:</span>
                  <span className="text-ink">{health.voice.engine}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Audio Synthesis:</span>
                  <span className="text-active">Ready</span>
                </div>
              </div>
            </div>
          </div>

          {/* Storage Telemetry */}
          {health.storage && (
            <div className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <span>💾</span> Host Disk / Storage Volume
                </h3>
                {getStatusBadge(health.storage.status)}
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-muted font-mono">
                  <span>
                    Available: {formatBytes(health.storage.free_bytes)}
                  </span>
                  <span>
                    Total: {formatBytes(health.storage.total_bytes)}
                  </span>
                </div>
                <div className="w-full bg-panel h-2.5 rounded-full overflow-hidden border border-border">
                  <div
                    className="bg-accent h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.max(
                          0,
                          ((health.storage.total_bytes - health.storage.free_bytes) /
                            (health.storage.total_bytes || 1)) *
                            100
                        )
                      )}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
