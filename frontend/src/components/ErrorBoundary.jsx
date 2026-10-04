import React from "react";
import ProductState from "@/components/shared/ProductState";

const STALE_LAZY_ERROR_PARTS = [
  "Dynamically imported module is invalid",
  "Cannot read properties of undefined (reading 'default')",
  "._result.default",
];

function isKnownStaleLazyError(message) {
  return Boolean(
    message && STALE_LAZY_ERROR_PARTS.some((part) => message.includes(part))
  );
}

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
        typeof window.__syroceChunkReloadOnce === "function" &&
        ((typeof window.__syroceIsChunkError === "function" && window.__syroceIsChunkError(msg)) ||
          isKnownStaleLazyError(msg))
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

  isChunkError = () => {
    const error = this.state.error;
    const msg = error && (error.message || (typeof error === "string" ? error : ""));
    return Boolean(
      typeof window !== "undefined" &&
      ((typeof window.__syroceIsChunkError === "function" && window.__syroceIsChunkError(msg)) ||
        isKnownStaleLazyError(msg))
    );
  };

  handleRetry = () => {
    if (this.isChunkError()) {
      if (typeof window.__syroceForceFreshReload === "function") {
        window.__syroceForceFreshReload();
        return;
      }
      window.location.reload();
      return;
    }
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const chunkError = this.isChunkError();
      return (
        <div data-testid="error-boundary-fallback">
          <ProductState
            state="error"
            titleKey={chunkError ? "uiQuality.states.staleVersion.title" : undefined}
            titleDefaultValue={chunkError ? "Uygulamanın yeni sürümü yüklenemedi" : undefined}
            descriptionKey={chunkError ? "uiQuality.states.staleVersion.description" : undefined}
            descriptionDefaultValue={chunkError ? "Sayfadaki eski dosyalar güncel sürümle uyuşmuyor. Yenileme işlemi açık form ve seçimleri koruyamayabilir." : undefined}
            onRetry={this.handleRetry}
            retryLabelKey={chunkError ? "uiQuality.actions.loadLatestVersion" : "uiQuality.actions.retryAgain"}
            retryDefaultValue={chunkError ? "Güncel sürümü yükle" : "Tekrar dene"}
            showDashboardLink={false}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
