import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { applyRtl } from "./i18n";
// Self-hosted fonts (bundled) — no Google Fonts CDN, so text renders even where
// fonts.googleapis.com is blocked/slow instead of falling back to a system font.
import "@fontsource/space-grotesk/400.css";  // FIX: AUDIT-3 - add missing weight 400
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "./styles.css";
import { initTelegram } from "./theme";

initTelegram();
applyRtl();

const root = ReactDOM.createRoot(document.getElementById("root")!);
// FIX: AUDIT-LOW - removed the dead `fonts-loading` class toggle: it had no matching
// CSS rule (pure no-op) and nothing renders before paint() anyway, so it never hid
// anything. The anti-FOUT behaviour is the Promise.race gate below (capped at 1.2s).
const paint = () => {
  root.render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>,
  );
};

// Paint only once the bundled fonts are ready, so text doesn't first render in a
// fallback font and then reflow when Inter/Space Grotesk load. Capped at 1.2s so a
// font hiccup can't block the UI; self-hosted woff2 means the wait is a few ms.
Promise.race([
  Promise.allSettled([
    document.fonts.load("400 1rem Inter"),
    document.fonts.load("700 1rem 'Space Grotesk'"),
  ]),
  new Promise((resolve) => setTimeout(resolve, 1200)),
]).then(() => paint());
