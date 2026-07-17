import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { App } from "./App";
// Self-hosted fonts — bundled into the build, NO Google Fonts CDN dependency. The
// admin used to pull Space Grotesk, Inter and the Material Symbols icon font from
// fonts.googleapis.com; where that CDN is blocked/unreachable (common in RU and on
// air-gapped servers) every icon rendered as its raw text name and all text fell back
// to a system font with different metrics — so sizes, spacing and layout looked broken
// everywhere. Bundling them makes the panel render identically with no internet.
// FIX: UI-1 - add Space Grotesk weight 400. Several rules use `font-family:
// var(--display)` with NO explicit weight (e.g. .sb-foot .who, .range-note), which
// renders at the inherited 400 — previously unavailable, so the browser synthesized
// or fell back to 500, making that text look subtly off. (Mini App already ships 400.)
import "@fontsource/space-grotesk/400.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "material-symbols/outlined.css";
import "./styles.css";

// Apply the saved colour theme before the first paint (default: dark, the original
// look). The sidebar toggle updates this + persists to localStorage.
document.documentElement.dataset.theme = localStorage.getItem("admin_theme") || "dark";

// HashRouter (not BrowserRouter): the admin SPA is served as static files (dev:
// FastAPI StaticFiles at /admin/, prod: Caddy on the admin subdomain). The hash is
// never sent to the server, so direct links / F5 / deep links always load
// index.html and the router resolves the route client-side — no server SPA fallback
// needed, and it's immune to the dev(/admin/) vs prod(root) base-path difference.
// Every page gets its own URL: /admin/#/users, /admin/#/payments, …
const root = ReactDOM.createRoot(document.getElementById("root")!);
const paint = () =>
  root.render(
    <React.StrictMode>
      <HashRouter>
        <App />
      </HashRouter>
    </React.StrictMode>,
  );

// Paint only AFTER the bundled fonts are ready, so the first frame already has the
// real text + icon glyphs. Otherwise the page renders in a fallback font (different
// metrics) and the Material Symbols icons occupy their ligature-name width, then
// everything reflows/snaps into place once the fonts load — the "иконки прыгают,
// потом встают на места" flash. Capped at 1.2s so a font hiccup can never block the
// UI. Fonts are self-hosted woff2 (same origin) so the wait is a few ms, ~0 when cached.
Promise.race([
  Promise.allSettled([
    document.fonts.load("400 1rem Inter"),
    document.fonts.load("700 1rem 'Space Grotesk'"),
    document.fonts.load("1rem 'Material Symbols Outlined'"),
  ]),
  new Promise((resolve) => setTimeout(resolve, 1200)),
]).then(paint);
