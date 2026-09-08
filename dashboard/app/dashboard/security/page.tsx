"use client";

import { useState, useEffect } from "react";
import {
  api,
  PhishingCheckResponse,
  FraudCheckResponse,
  IPAuditResponse,
  SecurityStatsResponse,
  SecurityEventSummary,
  APIError,
} from "@/lib/api";

type Tab = "overview" | "phishing" | "fraud" | "ip";

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function SecurityCenterPage() {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<SecurityStatsResponse | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Phishing state
  const [phishingUrl, setPhishingUrl] = useState("");
  const [phishingContent, setPhishingContent] = useState("");
  const [phishingLoading, setPhishingLoading] = useState(false);
  const [phishingResult, setPhishingResult] = useState<PhishingCheckResponse | null>(null);

  // Fraud state
  const [fraudType, setFraudType] = useState("transfer");
  const [fraudAmount, setFraudAmount] = useState("");
  const [fraudRecipient, setFraudRecipient] = useState("");
  const [fraudMetadata, setFraudMetadata] = useState("");
  const [fraudLoading, setFraudLoading] = useState(false);
  const [fraudResult, setFraudResult] = useState<FraudCheckResponse | null>(null);

  // IP Audit state
  const [ipAddress, setIpAddress] = useState("");
  const [ipLoading, setIpLoading] = useState(false);
  const [ipResult, setIpResult] = useState<IPAuditResponse | null>(null);

  const loadStats = async () => {
    try {
      setLoadingStats(true);
      const data = await api.getSecurityStats();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load security statistics.");
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  const handlePhishingCheck = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phishingUrl && !phishingContent) return;

    try {
      setPhishingLoading(true);
      setError(null);
      const res = await api.checkPhishing({
        url: phishingUrl || undefined,
        content: phishingContent || undefined,
      });
      setPhishingResult(res);
      loadStats();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to analyze URL/content.");
    } finally {
      setPhishingLoading(false);
    }
  };

  const handleFraudCheck = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setFraudLoading(true);
      setError(null);

      let parsedMeta: Record<string, unknown> = {};
      if (fraudMetadata.trim()) {
        try {
          parsedMeta = JSON.parse(fraudMetadata);
        } catch {
          parsedMeta = { raw_notes: fraudMetadata };
        }
      }

      const res = await api.checkFraud({
        transaction_type: fraudType,
        amount: fraudAmount ? parseFloat(fraudAmount) : undefined,
        recipient: fraudRecipient || undefined,
        metadata: parsedMeta,
      });
      setFraudResult(res);
      loadStats();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to evaluate transaction risk.");
    } finally {
      setFraudLoading(false);
    }
  };

  const handleIPAudit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ipAddress.trim()) return;

    try {
      setIpLoading(true);
      setError(null);
      const res = await api.auditIP({ ip_address: ipAddress.trim() });
      setIpResult(res);
      loadStats();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to audit IP address.");
    } finally {
      setIpLoading(false);
    }
  };

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold font-display tracking-tight">Security Center</h1>
        <p className="text-muted text-sm mt-1">
          Proactive threat monitoring, URL anti-phishing defense, transaction fraud detection, and IP auditing.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-xs underline hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4">
          <p className="text-xs text-muted font-medium">Total Monitored Events</p>
          <p className="text-2xl font-display font-bold mt-2">
            {loadingStats ? "…" : stats?.total_events ?? 0}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-muted font-medium">High / Critical Threats</p>
          <p className={`text-2xl font-display font-bold mt-2 ${(stats?.high_risk_events ?? 0) > 0 ? "text-danger" : "text-ink"}`}>
            {loadingStats ? "…" : stats?.high_risk_events ?? 0}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-muted font-medium">Phishing Scans</p>
          <p className="text-2xl font-display font-bold mt-2">
            {loadingStats ? "…" : stats?.events_by_type?.phishing_detected ?? 0}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-muted font-medium">Fraud & Suspicious IP Alerts</p>
          <p className="text-2xl font-display font-bold mt-2 text-warning">
            {loadingStats
              ? "…"
              : (stats?.events_by_type?.fraud_attempt ?? 0) +
                (stats?.events_by_type?.suspicious_ip ?? 0)}
          </p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-border space-x-4">
        <button
          onClick={() => setActiveTab("overview")}
          className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "overview"
              ? "border-accent text-accent"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          Security Audit Feed
        </button>
        <button
          onClick={() => setActiveTab("phishing")}
          className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "phishing"
              ? "border-accent text-accent"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          Phishing & URL Scanner
        </button>
        <button
          onClick={() => setActiveTab("fraud")}
          className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "fraud"
              ? "border-accent text-accent"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          Fraud Risk Evaluator
        </button>
        <button
          onClick={() => setActiveTab("ip")}
          className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "ip"
              ? "border-accent text-accent"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          IP Threat Intelligence
        </button>
      </div>

      {/* Tab: Overview (Recent Audits) */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Live Security Audit Log</h2>
            <button onClick={loadStats} className="btn-secondary text-xs">
              Refresh Feed
            </button>
          </div>

          {stats?.recent_events && stats.recent_events.length > 0 ? (
            <div className="card overflow-hidden divide-y divide-border">
              {stats.recent_events.map((event: SecurityEventSummary) => (
                <div key={event.id} className="p-4 flex items-start justify-between gap-4">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded font-mono uppercase font-bold ${
                          event.risk_level === "CRITICAL"
                            ? "bg-danger text-white"
                            : event.risk_level === "HIGH"
                            ? "bg-danger/20 text-danger"
                            : event.risk_level === "MEDIUM"
                            ? "bg-warning/20 text-warning"
                            : "bg-active/20 text-active"
                        }`}
                      >
                        {event.risk_level}
                      </span>
                      <span className="font-mono text-xs text-muted uppercase">
                        {event.event_type.replace(/_/g, " ")}
                      </span>
                      {event.ip_address && (
                        <span className="text-xs font-mono text-muted bg-panel px-1.5 py-0.5 rounded border border-border">
                          {event.ip_address}
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-ink break-words">{event.description}</p>
                    {event.metadata && Object.keys(event.metadata).length > 0 && (
                      <div className="text-xs text-muted font-mono bg-panel/50 p-2 rounded border border-border mt-1">
                        {JSON.stringify(event.metadata)}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-muted shrink-0 text-right font-mono">
                    {formatTimestamp(event.created_at)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="card p-8 text-center text-muted text-sm">
              No security anomalies detected yet. The platform is actively protected.
            </div>
          )}
        </div>
      )}

      {/* Tab: Phishing Scanner */}
      {activeTab === "phishing" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <form onSubmit={handlePhishingCheck} className="card p-6 space-y-4">
            <h2 className="text-base font-semibold">Analyze URL / Web Content</h2>
            <p className="text-xs text-muted">
              Inspect suspicious domains, emails, links, and messages for credential harvesting, typosquatting, and malicious payloads.
            </p>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Target URL</label>
              <input
                type="text"
                placeholder="https://paypa1-secure-login.com"
                value={phishingUrl}
                onChange={(e) => setPhishingUrl(e.target.value)}
                className="input w-full text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Message Content / HTML Snippet (Optional)</label>
              <textarea
                placeholder="Urgent: Your account is locked! Click here immediately to verify..."
                rows={4}
                value={phishingContent}
                onChange={(e) => setPhishingContent(e.target.value)}
                className="input w-full text-sm font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={phishingLoading || (!phishingUrl && !phishingContent)}
              className="btn-primary w-full text-sm"
            >
              {phishingLoading ? "Analyzing threat indicators…" : "Run Phishing Diagnostic"}
            </button>
          </form>

          <div>
            {phishingResult ? (
              <div className="card p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <h3 className="font-semibold text-sm">Analysis Results</h3>
                  <span
                    className={`text-xs px-2.5 py-1 rounded font-mono font-bold uppercase ${
                      phishingResult.verdict === "MALICIOUS"
                        ? "bg-danger text-white"
                        : phishingResult.verdict === "SUSPICIOUS"
                        ? "bg-warning/20 text-warning"
                        : "bg-active/20 text-active"
                    }`}
                  >
                    {phishingResult.verdict}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-panel p-3 rounded border border-border">
                    <p className="text-xs text-muted">Confidence Score</p>
                    <p className="text-lg font-display font-bold mt-1">
                      {Math.round(phishingResult.confidence * 100)}%
                    </p>
                  </div>
                  <div className="bg-panel p-3 rounded border border-border">
                    <p className="text-xs text-muted">Risk Category</p>
                    <p className="text-lg font-display font-bold mt-1 uppercase text-xs">
                      {phishingResult.risk_level}
                    </p>
                  </div>
                </div>

                {phishingResult.detected_indicators && phishingResult.detected_indicators.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted mb-1.5">Detected Indicators</p>
                    <ul className="space-y-1">
                      {phishingResult.detected_indicators.map((ind, idx) => (
                        <li key={idx} className="text-xs text-danger flex items-center gap-1.5">
                          <span>⚠️</span> {ind}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {phishingResult.recommendations && phishingResult.recommendations.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted mb-1.5">Recommended Actions</p>
                    <ul className="space-y-1">
                      {phishingResult.recommendations.map((rec, idx) => (
                        <li key={idx} className="text-xs text-muted flex items-center gap-1.5">
                          <span>🛡️</span> {rec}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="card p-8 text-center text-muted text-sm h-full flex flex-col items-center justify-center border-dashed">
                Enter a target URL or message to execute instant threat heuristics.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Fraud Risk */}
      {activeTab === "fraud" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <form onSubmit={handleFraudCheck} className="card p-6 space-y-4">
            <h2 className="text-base font-semibold">Evaluate Transaction / Action Risk</h2>
            <p className="text-xs text-muted">
              Detect abnormal velocity, high-risk destination accounts, anomalous amounts, and prompt injection intent.
            </p>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Action / Transaction Type</label>
              <select
                value={fraudType}
                onChange={(e) => setFraudType(e.target.value)}
                className="input w-full text-sm"
              >
                <option value="transfer">Fund Transfer</option>
                <option value="payment">Card / Invoice Payment</option>
                <option value="api_key_generation">API Key Creation</option>
                <option value="system_command">Automated OS Command</option>
                <option value="data_export">Bulk Data Export</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Amount / Value (USD or Units)</label>
              <input
                type="number"
                step="any"
                placeholder="5000.00"
                value={fraudAmount}
                onChange={(e) => setFraudAmount(e.target.value)}
                className="input w-full text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Recipient / Target Identifier</label>
              <input
                type="text"
                placeholder="acct_83921938 or external-api-endpoint"
                value={fraudRecipient}
                onChange={(e) => setFraudRecipient(e.target.value)}
                className="input w-full text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">Context Metadata (JSON or text)</label>
              <textarea
                placeholder='{"ip": "185.220.101.5", "device_fingerprint": "xyz"}'
                rows={3}
                value={fraudMetadata}
                onChange={(e) => setFraudMetadata(e.target.value)}
                className="input w-full text-sm font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={fraudLoading}
              className="btn-primary w-full text-sm"
            >
              {fraudLoading ? "Assessing Risk Profile…" : "Run Fraud Detection"}
            </button>
          </form>

          <div>
            {fraudResult ? (
              <div className="card p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <h3 className="font-semibold text-sm">Risk Assessment Result</h3>
                  <span
                    className={`text-xs px-2.5 py-1 rounded font-mono font-bold uppercase ${
                      fraudResult.risk_level === "CRITICAL" || fraudResult.risk_level === "HIGH"
                        ? "bg-danger text-white"
                        : fraudResult.risk_level === "MEDIUM"
                        ? "bg-warning/20 text-warning"
                        : "bg-active/20 text-active"
                    }`}
                  >
                    {fraudResult.risk_level} RISK
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-panel p-3 rounded border border-border">
                    <p className="text-xs text-muted">Risk Score</p>
                    <p className="text-2xl font-display font-bold mt-1">
                      {fraudResult.risk_score} / 100
                    </p>
                  </div>
                  <div className="bg-panel p-3 rounded border border-border">
                    <p className="text-xs text-muted">System Recommendation</p>
                    <p className="text-sm font-display font-bold mt-2 uppercase text-accent">
                      {fraudResult.recommended_action}
                    </p>
                  </div>
                </div>

                {fraudResult.triggers && fraudResult.triggers.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted mb-1.5">Triggered Anomaly Rules</p>
                    <ul className="space-y-1">
                      {fraudResult.triggers.map((trigger, idx) => (
                        <li key={idx} className="text-xs text-warning flex items-center gap-1.5">
                          <span>⚠️</span> {trigger}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="card p-8 text-center text-muted text-sm h-full flex flex-col items-center justify-center border-dashed">
                Submit transaction parameters to evaluate anomalous behavioral patterns.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab: IP Threat Intelligence */}
      {activeTab === "ip" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <form onSubmit={handleIPAudit} className="card p-6 space-y-4">
            <h2 className="text-base font-semibold">IP Address Threat Lookup</h2>
            <p className="text-xs text-muted">
              Inspect suspicious IP addresses for proxy/Tor exits, botnet activity, geolocation anomalies, and known abusive subnets.
            </p>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">IP Address</label>
              <input
                type="text"
                placeholder="198.51.100.42"
                value={ipAddress}
                onChange={(e) => setIpAddress(e.target.value)}
                className="input w-full text-sm font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={ipLoading || !ipAddress.trim()}
              className="btn-primary w-full text-sm"
            >
              {ipLoading ? "Querying Threat DB…" : "Audit IP Reputation"}
            </button>
          </form>

          <div>
            {ipResult ? (
              <div className="card p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <div>
                    <h3 className="font-mono font-bold text-sm">{ipResult.ip_address}</h3>
                    <p className="text-xs text-muted">{ipResult.country_code} · {ipResult.asn || "Unknown ASN"}</p>
                  </div>
                  <span
                    className={`text-xs px-2.5 py-1 rounded font-mono font-bold uppercase ${
                      ipResult.is_known_threat
                        ? "bg-danger text-white"
                        : ipResult.is_datacenter || ipResult.is_tor || ipResult.is_vpn
                        ? "bg-warning/20 text-warning"
                        : "bg-active/20 text-active"
                    }`}
                  >
                    {ipResult.is_known_threat ? "THREAT DETECTED" : "REPUTATION CLEAN"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-panel p-3 rounded border border-border">
                    <p className="text-xs text-muted">Threat Score</p>
                    <p className="text-2xl font-display font-bold mt-1">
                      {ipResult.threat_score} / 100
                    </p>
                  </div>
                  <div className="bg-panel p-3 rounded border border-border">
                    <p className="text-xs text-muted">ISP / Organization</p>
                    <p className="text-sm font-semibold mt-2 truncate">
                      {ipResult.isp || "Private Network"}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className={`p-2 rounded border ${ipResult.is_vpn ? "bg-warning/10 border-warning text-warning font-bold" : "bg-panel border-border text-muted"}`}>
                    VPN: {ipResult.is_vpn ? "YES" : "NO"}
                  </div>
                  <div className={`p-2 rounded border ${ipResult.is_tor ? "bg-danger/10 border-danger text-danger font-bold" : "bg-panel border-border text-muted"}`}>
                    TOR: {ipResult.is_tor ? "YES" : "NO"}
                  </div>
                  <div className={`p-2 rounded border ${ipResult.is_datacenter ? "bg-warning/10 border-warning text-warning font-bold" : "bg-panel border-border text-muted"}`}>
                    HOSTING: {ipResult.is_datacenter ? "YES" : "NO"}
                  </div>
                </div>
              </div>
            ) : (
              <div className="card p-8 text-center text-muted text-sm h-full flex flex-col items-center justify-center border-dashed">
                Enter an IPv4 or IPv6 address to run live threat analysis.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
