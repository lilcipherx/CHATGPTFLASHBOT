import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

// FIX: AUDIT13-H5 - template the CSP connect-src with the API origin at BUILD time.
// The index.html ships connect-src 'self' (correct for the same-origin prod topology).
// When the Mini App is deployed on a DIFFERENT origin than the API (VITE_API_BASE set to
// an absolute URL), every /api fetch would be CSP-blocked while images still load —
// masking the cause. This plugin injects that origin into connect-src so a split-origin
// build is self-consistent; a same-origin build (VITE_API_BASE unset/relative) is untouched.
function cspApiOrigin(apiBase: string): Plugin {
  return {
    name: "csp-api-origin",
    transformIndexHtml(html) {
      if (!apiBase) return html;
      let origin = "";
      try {
        origin = new URL(apiBase).origin; // absolute → cross-origin
      } catch {
        return html; // relative base (same-origin) — nothing to add
      }
      return html.replace("connect-src 'self'", `connect-src 'self' ${origin}`);
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    // FIX: AUDIT13-MINIAPP-BASE - Caddy serves this SPA under /miniapp/ (handle
    // /miniapp/* + strip_prefix), so assets must be referenced as /miniapp/assets/*.
    // Without this, index.html shipped /assets/* (default base "/"), which fell through
    // Caddy's handle /* to the API → 404 → blank white screen. Mirrors admin's base.
    base: "/miniapp/",
    plugins: [react(), cspApiOrigin(env.VITE_API_BASE ?? "")],
    // Dev: proxy API calls to the local backend so the relative `/api/*` requests
    // in src/api/client.ts resolve without CORS / VITE_API_BASE wiring.
    server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
    build: { outDir: "dist" },
  };
});
