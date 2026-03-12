/**
 * Audit Timeline Summary Card — Compact audit summary for dashboard embedding.
 * Fetches aggregated audit data from /api/audit/summary and renders severity breakdown.
 */
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Shield, Activity, AlertTriangle, Info } from "lucide-react";
import { SeverityBadge, DegradedState, NetworkError } from "./OperationalWidgets";

const PERIOD_OPTIONS = [
  { value: "1h", label: "1 Saat" },
  { value: "6h", label: "6 Saat" },
  { value: "24h", label: "24 Saat" },
  { value: "7d", label: "7 Gun" },
];

export function AuditTimelineSummaryCard({ className = "" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState("24h");

  const fetchSummary = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await axios.get(`/audit/summary?period=${period}`);
      setData(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  if (error) return <NetworkError error={error} onRetry={fetchSummary} className={className} />;

  if (loading && !data) {
    return (
      <div className={`bg-zinc-900/60 border border-zinc-800/50 rounded-lg p-4 animate-pulse ${className}`}>
        <div className="h-4 bg-zinc-800 rounded w-32 mb-3" />
        <div className="h-8 bg-zinc-800 rounded w-full" />
      </div>
    );
  }

  const severities = data?.by_severity || {};
  const topOps = Object.entries(data?.by_operation || {}).slice(0, 5);

  return (
    <div
      data-testid="audit-timeline-summary-card"
      className={`bg-zinc-900/60 border border-zinc-800/50 rounded-lg p-4 ${className}`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-medium text-zinc-200">Audit Summary</span>
        </div>
        <select
          data-testid="audit-period-select"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-300 rounded px-2 py-1"
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="text-2xl font-bold text-zinc-100 mb-3" data-testid="audit-total-events">
        {data?.total_events?.toLocaleString() || 0}
        <span className="text-xs font-normal text-zinc-500 ml-2">total events</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {severities.critical > 0 && <SeverityBadge severity="critical" label={`${severities.critical} critical`} />}
        {severities.error > 0 && <SeverityBadge severity="error" label={`${severities.error} error`} />}
        {severities.warning > 0 && <SeverityBadge severity="warning" label={`${severities.warning} warning`} />}
        {severities.info > 0 && <SeverityBadge severity="info" label={`${severities.info} info`} />}
      </div>

      {topOps.length > 0 && (
        <div className="border-t border-zinc-800/50 pt-2 mt-2">
          <p className="text-xs text-zinc-500 mb-1.5">Top Operations</p>
          {topOps.map(([op, count]) => (
            <div key={op} className="flex items-center justify-between py-0.5">
              <span className="text-xs text-zinc-400 truncate max-w-[150px]">{op}</span>
              <span className="text-xs text-zinc-500 font-mono">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default AuditTimelineSummaryCard;
