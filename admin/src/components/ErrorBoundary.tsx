import { Component, ErrorInfo, ReactNode } from "react";

// App-level safety net. Without it, ANY render error in a page — or a failed lazy
// chunk download (offline / deploy mid-session) — unmounts the whole React tree and
// leaves the admin staring at a blank white screen with no way back. This catches
// the error, shows a recoverable fallback, and (because App keys it by the current
// view) resets automatically when the admin navigates to another section.

interface Props {
  children: ReactNode;
  onReset?: () => void;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // FIX: FRONTEND - only log in dev (admin panel runs on the same origin as the
    // API in prod, so a stack trace in the console is a minor info leak).
    if (import.meta.env.DEV) {
      console.error("[admin] page crashed:", error, info.componentStack);
    }
  }

  private reset = (): void => {
    this.setState({ error: null });
    this.props.onReset?.();
  };

  render(): ReactNode {
    if (this.state.error) {
      const isChunkError = /loading chunk|dynamically imported module|failed to fetch/i.test(
        this.state.error.message,
      );
      return (
        <div className="error-boundary" role="alert">
          <span className="ms" style={{ fontSize: 40, color: "var(--danger)" }}>error</span>
          <h2 style={{ margin: "var(--sp-3) 0 var(--sp-1)" }}>
            {isChunkError ? "Не удалось загрузить раздел" : "Что-то пошло не так"}
          </h2>
          <p className="muted" style={{ maxWidth: 460, textAlign: "center" }}>
            {isChunkError
              ? "Похоже, приложение обновилось или пропала сеть. Обновите страницу, чтобы загрузить свежую версию."
              : "Раздел аварийно завершился. Можно вернуться и попробовать снова — остальная панель работает."}
          </p>
          <p className="code-key" style={{ margin: "var(--sp-2) 0", opacity: 0.7, maxWidth: 460, overflowWrap: "anywhere" }}>
            {this.state.error.message}
          </p>
          <div style={{ display: "flex", gap: "var(--sp-2)", marginTop: "var(--sp-2)" }}>
            <button className="btn" onClick={this.reset}>
              <span className="ms sm">refresh</span> Попробовать снова
            </button>
            <button className="btn ghost" onClick={() => window.location.reload()}>
              Обновить страницу
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
