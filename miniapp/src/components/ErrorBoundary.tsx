import { Component, ErrorInfo, ReactNode } from "react";
import { t } from "../i18n";

// Last-resort safety net. Without it, any render error in a page/component unmounts
// the whole React tree and leaves the user on a blank canvas inside Telegram with no
// way out but to close the Mini App. This catches the error and offers a reload.

interface Props {
  children: ReactNode;
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
    // FIX: FRONTEND - only log to console in dev. In prod, console.error is still
    // visible to anyone opening DevTools, but we don't want to spam the console of
    // every user who hits a render error (and we don't want to leak stack traces).
    if (import.meta.env.DEV) {
      console.error("[miniapp] crashed:", error, info.componentStack);
    }
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="app-crash" role="alert">
          <div className="app-crash-emoji">😵‍💫</div>
          <p className="app-crash-msg">{t("app_crashed")}</p>
          <button className="btn" onClick={() => window.location.reload()}>
            {t("retry")}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
