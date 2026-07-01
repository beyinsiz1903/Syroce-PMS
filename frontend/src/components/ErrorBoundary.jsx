import React from "react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Render-path chunk errors (a React.lazy import that resolved-but-invalid or
    // failed to load, rejecting DURING render) are caught here and NEVER fire the
    // window 'error'/'unhandledrejection' handlers in index.html, so the stale-
    // chunk self-heal cannot see them. Route them through the SAME one-shot reload
    // latch: if it heals (first time) the page reloads with fresh chunks and we
    // skip Sentry; if the latch is already spent (genuinely broken deploy) we fall
    // through and page it normally.
    try {
      const msg = error && (error.message || (typeof error === "string" ? error : ""));
      if (
        typeof window !== "undefined" &&
        typeof window.__syroceIsChunkError === "function" &&
        typeof window.__syroceChunkReloadOnce === "function" &&
        window.__syroceIsChunkError(msg)
      ) {
        const healing = window.__syroceChunkReloadOnce();
        if (healing) return; // reloading now — benign stale-chunk, do not capture
      }
    } catch (_) {
      /* fall through to normal capture */
    }

    console.error("[ErrorBoundary]", error, info);
    if (import.meta.env.VITE_SENTRY_DSN) {
      import("@sentry/react")
        .then((Sentry) => {
          Sentry.withScope((scope) => {
            scope.setExtras({ componentStack: info?.componentStack });
            Sentry.captureException(error);
          });
        })
        .catch(() => { /* Sentry yüklenemezse sessizce yut */ });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div data-testid="error-boundary-fallback" className="min-h-[40vh] flex flex-col items-center justify-center bg-zinc-950 text-zinc-100 p-8">
          <div className="bg-red-950/30 border border-red-800/40 rounded-lg p-6 max-w-md text-center">
            <p className="text-lg font-semibold text-red-300 mb-2">Something went wrong</p>
            <p className="text-sm text-zinc-400 mb-4">
              {this.state.error?.message || "An unexpected error occurred."}
            </p>
            <button
              data-testid="error-boundary-retry-btn"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-md text-sm border border-zinc-700"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
