import WebApp from "@twa-dev/sdk";

// Initialise the Telegram WebApp shell: expand, match header/background to theme,
// and enable closing confirmation. Safe to call once at startup.
// Fixed Higgsfield-style canvas (black) regardless of the user's Telegram theme.
const CANVAS = "#0a0a0b";

export function initTelegram(): void {
  try {
    WebApp.ready();
    WebApp.expand();
    WebApp.setHeaderColor(CANVAS);
    WebApp.setBackgroundColor(CANVAS);
    WebApp.enableClosingConfirmation();
  } catch {
    /* running outside Telegram (e.g. browser preview) — ignore */
  }
}

export function haptic(style: "light" | "medium" | "heavy" = "light"): void {
  try {
    WebApp.HapticFeedback.impactOccurred(style);
  } catch {
    /* ignore */
  }
}
