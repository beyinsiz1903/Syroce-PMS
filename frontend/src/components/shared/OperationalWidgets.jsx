/**
 * Shared Severity Badge — Consistent severity rendering across all modules.
 */
import React from "react";

const SEVERITY_CONFIG = {
  critical: { bg: "bg-red-500/15", border: "border-red-500/30", text: "text-red-300", dot: "bg-red-400" },
  error: { bg: "bg-orange-500/15", border: "border-orange-500/30", text: "text-orange-300", dot: "bg-orange-400" },
  warning: { bg: "bg-amber-500/15", border: "border-amber-500/30", text: "text-amber-300", dot: "bg-amber-400" },
  info: { bg: "bg-blue-500/15", border: "border-blue-500/30", text: "text-blue-300", dot: "bg-blue-400" },
  success: { bg: "bg-emerald-500/15", border: "border-emerald-500/30", text: "text-emerald-300", dot: "bg-emerald-400" },
};

export function SeverityBadge({ severity = "info", label, showDot = true, className = "" }) {
  const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;
  const displayLabel = label || severity;

  return (
    <span
      data-testid={`severity-badge-${severity}`}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${config.bg} ${config.border} ${config.text} ${className}`}
    >
      {showDot && <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`} />}
      {displayLabel}
    </span>
  );
}

/**
 * Empty/Degraded State — Consistent empty state placeholder.
 */
export function EmptyState({ icon: Icon, title, description, action, className = "" }) {
  return (
    <div
      data-testid="empty-state"
      className={`flex flex-col items-center justify-center py-12 text-center ${className}`}
    >
      {Icon && <Icon className="w-10 h-10 text-zinc-600 mb-3" />}
      <p className="text-sm font-medium text-zinc-400 mb-1">{title || "No data"}</p>
      {description && <p className="text-xs text-zinc-600 max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/**
 * Degraded State — Shown when data is stale or partially available.
 */
export function DegradedState({ message, lastUpdated, onRetry, className = "" }) {
  return (
    <div
      data-testid="degraded-state"
      className={`bg-amber-500/5 border border-amber-600/20 rounded-lg p-3 flex items-center gap-3 ${className}`}
    >
      <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-amber-300">{message || "Data may be stale"}</p>
        {lastUpdated && (
          <p className="text-xs text-zinc-600 mt-0.5">Last update: {lastUpdated}</p>
        )}
      </div>
      {onRetry && (
        <button
          data-testid="degraded-retry-btn"
          onClick={onRetry}
          className="text-xs text-amber-400 hover:text-amber-300 underline flex-shrink-0"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * Network Error Recovery — Shown when an API call fails.
 */
export function NetworkError({ error, onRetry, className = "" }) {
  const message = error?.response?.status === 503
    ? "Service temporarily unavailable"
    : error?.response?.status === 429
    ? "Rate limited — try again shortly"
    : error?.message || "Network error";

  return (
    <div
      data-testid="network-error"
      className={`bg-red-500/5 border border-red-600/20 rounded-lg p-4 text-center ${className}`}
    >
      <p className="text-sm text-red-300 mb-2">{message}</p>
      {onRetry && (
        <button
          data-testid="network-error-retry-btn"
          onClick={onRetry}
          className="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export default SeverityBadge;
