/**
 * Module Error Boundary — Isolates failures per operational module.
 * Provides module-specific error recovery without taking down adjacent modules.
 */
import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export class ModuleErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error(`[ModuleError:${this.props.moduleName || "unknown"}]`, error, info);
  }

  render() {
    if (this.state.hasError) {
      const moduleName = this.props.moduleName || "Module";
      return (
        <div
          data-testid={`module-error-${moduleName.toLowerCase()}`}
          className="min-h-[200px] flex flex-col items-center justify-center bg-zinc-950/50 border border-red-900/30 rounded-lg p-6 m-2"
        >
          <AlertTriangle className="w-8 h-8 text-red-400 mb-3" />
          <p className="text-sm font-medium text-red-300 mb-1">{moduleName} Error</p>
          <p className="text-xs text-zinc-500 mb-4 max-w-xs text-center">
            {this.state.error?.message || "This module encountered an error."}
          </p>
          <button
            data-testid={`module-retry-${moduleName.toLowerCase()}`}
            onClick={() => this.setState({ hasError: false, error: null })}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700 transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ModuleErrorBoundary;
