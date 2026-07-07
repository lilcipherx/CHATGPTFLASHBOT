import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Dev: proxy API calls to the local backend so the relative `/api/*` requests
  // in src/api/client.ts resolve without CORS / VITE_API_BASE wiring.
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist" },
});
