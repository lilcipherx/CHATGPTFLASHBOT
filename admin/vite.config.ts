import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // Served by the Core API under /admin/ (same origin as /api/admin), so the
  // relative API calls in src/api.ts resolve correctly.
  base: "/admin/",
  plugins: [react()],
  // Dev: proxy API calls to the local backend so the relative `/api/admin/*`
  // requests in src/api.ts resolve without CORS / VITE_API_BASE wiring.
  server: { port: 5174, proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist" },
});
