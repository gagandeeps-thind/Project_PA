/* ───────────────────────────────────────────────────────────
 *  Error boundary – keeps one failing page from blanking the console
 * ─────────────────────────────────────────────────────────── */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Changing this (e.g. the page key) clears a caught error, so navigating away recovers. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/** A page chunk that fails to load (a deploy replaced it while the tab was open) or a render
 *  error shows a message with a reload button instead of an empty screen. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surfaced in the browser console for whoever is debugging; there is no client log sink.
    console.error("Admin page failed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    const stale = /dynamically imported module|Failed to fetch|Loading chunk/i.test(this.state.error.message);
    return (
      <div className="error-message" role="alert">
        <p>
          {stale
            ? "A new version of the console was deployed. Reload to continue."
            : "This page hit an unexpected error."}
        </p>
        <button className="btn-primary" type="button" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    );
  }
}
